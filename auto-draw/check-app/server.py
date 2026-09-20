#!/usr/bin/env python3
"""로또 확인 앱 — 로컬 서버 + 동행복권 최신 회차 프록시 + 당첨 이력."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DATA = ROOT / "data"
HISTORY_FILE = DATA / "history.json"
KST = timezone(timedelta(hours=9))
API = "https://www.dhlottery.co.kr/lt645/selectPstLt645Info.do"
PORT = 8765


def now_kst() -> datetime:
    return datetime.now(KST)


def in_auto_window(dt: datetime | None = None) -> bool:
    """토요일 20:45(KST) 이후 ~ 일요일 자정까지 자동 조회 구간."""
    dt = dt or now_kst()
    if dt.weekday() == 5:  # Saturday
        return (dt.hour, dt.minute) >= (20, 45)
    if dt.weekday() == 6:  # Sunday — 아직 최신 확인용으로 허용
        return True
    return False


def fetch_latest_draw() -> dict:
    ts = int(time.time() * 1000)
    url = f"{API}?_={ts}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; lotto-check-app/1.0)",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://www.dhlottery.co.kr/",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    items = (payload.get("data") or {}).get("list") or []
    if not items:
        raise ValueError("최신 회차 목록이 비어 있습니다.")
    row = items[0]
    win6 = [int(row[f"tm{i}WnNo"]) for i in range(1, 7)]
    bonus = int(row["bnsWnNo"])
    draw_no = int(row["ltEpsd"])
    ymd = str(row.get("ltRflYmd") or "")
    date = f"{ymd[0:4]}.{ymd[4:6]}.{ymd[6:8]}" if len(ymd) == 8 else ymd
    return {
        "drawNo": draw_no,
        "win6": win6,
        "bonus": bonus,
        "date": date,
        "source": "dhlottery",
        "fetchedAt": now_kst().isoformat(timespec="seconds"),
    }


def load_history() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, dict):
        items = data.get("items") or []
    elif isinstance(data, list):
        items = data
    else:
        items = []
    return [x for x in items if isinstance(x, dict) and "drawNo" in x]


def save_history(items: list[dict]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    payload = {
        "updatedAt": now_kst().isoformat(timespec="seconds"),
        "items": items,
    }
    HISTORY_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def upsert_history(draw: dict) -> list[dict]:
    items = load_history()
    draw_no = int(draw["drawNo"])
    entry = {
        "drawNo": draw_no,
        "win6": list(draw["win6"]),
        "bonus": int(draw["bonus"]),
        "date": draw.get("date") or "",
        "fetchedAt": draw.get("fetchedAt") or now_kst().isoformat(timespec="seconds"),
    }
    replaced = False
    for i, old in enumerate(items):
        if int(old.get("drawNo", -1)) == draw_no:
            items[i] = entry
            replaced = True
            break
    if not replaced:
        items.append(entry)
    items.sort(key=lambda x: int(x.get("drawNo", 0)), reverse=True)
    save_history(items)
    return items


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        print(f"[{self.log_date_time_string()}] {args[0]}")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            self._json(
                {
                    "nowKst": now_kst().isoformat(timespec="seconds"),
                    "weekday": now_kst().weekday(),
                    "inAutoWindow": in_auto_window(),
                    "autoHint": "토요일 20:45(KST) 이후 자동 조회",
                    "historyCount": len(load_history()),
                }
            )
            return
        if parsed.path == "/api/history":
            items = load_history()
            self._json({"ok": True, "count": len(items), "items": items})
            return
        if parsed.path == "/api/latest":
            qs = parse_qs(parsed.query)
            force = qs.get("force", ["0"])[0] in ("1", "true", "yes")
            if not force and not in_auto_window():
                self._json(
                    {
                        "ok": False,
                        "reason": "waiting",
                        "message": "토요일 20:45 이후에 자동으로 조회합니다.",
                        "nowKst": now_kst().isoformat(timespec="seconds"),
                        "inAutoWindow": False,
                    },
                    status=200,
                )
                return
            try:
                draw = fetch_latest_draw()
                history = upsert_history(draw)
                self._json(
                    {
                        "ok": True,
                        "inAutoWindow": in_auto_window(),
                        "draw": draw,
                        "historyCount": len(history),
                    }
                )
            except (urllib.error.URLError, urllib.error.HTTPError, ValueError, KeyError) as exc:
                self._json(
                    {
                        "ok": False,
                        "reason": "fetch_error",
                        "message": str(exc),
                        "inAutoWindow": in_auto_window(),
                    },
                    status=502,
                )
            return
        if parsed.path in ("/", ""):
            self.path = "/index.html"
        return super().do_GET()

    def _json(self, body: dict, status: int = 200) -> None:
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    if not HISTORY_FILE.exists():
        save_history([])
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"로또 확인 앱: http://127.0.0.1:{PORT}")
    print(f"이력 파일: {HISTORY_FILE}")
    print("중지: Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료")
        server.server_close()


if __name__ == "__main__":
    main()
