#!/usr/bin/env python3
"""Auto-draw 조회 전용 러너 (엑셀/Pages/FCM/add_draw/fix_draw 호출 금지).

- manifest.latestDrawNo+1 을 5분 간격으로 조회
- 성공 시 Step Summary + fetch_history 누적 후 종료
- 미발표가 상한까지면 skip 성공
- API 오류가 상한까지면 exit 3 (워크플로에서 Issue)

종료 코드:
  0  번호 확보 또는 미발표 skip
  3  API/파싱 실패 (알림 대상)
  4  설정 오류
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://www.dhlottery.co.kr/lt645/selectPstLt645Info.do"
KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    return datetime.now(KST)


def fetch_draw(draw_no: int | None = None, timeout: int = 20) -> dict | None:
    ts = int(time.time() * 1000)
    if draw_no is None:
        url = f"{API}?_={ts}"
    else:
        url = f"{API}?srchLtEpsd={draw_no}&_={ts}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; lotto-data-auto-draw/1.0)",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://www.dhlottery.co.kr/",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    items = (payload.get("data") or {}).get("list") or []
    if not items:
        return None
    row = items[0]
    win6 = [int(row[f"tm{i}WnNo"]) for i in range(1, 7)]
    bonus = int(row["bnsWnNo"])
    epsd = int(row["ltEpsd"])
    ymd = str(row.get("ltRflYmd") or "")
    date = f"{ymd[0:4]}.{ymd[4:6]}.{ymd[6:8]}" if len(ymd) == 8 else ymd
    if len(win6) != 6 or any(n < 1 or n > 45 for n in win6):
        raise ValueError(f"번호 범위 오류: {win6}")
    if len(set(win6)) != 6:
        raise ValueError(f"번호 중복: {win6}")
    if bonus < 1 or bonus > 45 or bonus in win6:
        raise ValueError(f"보너스 오류: {bonus} / {win6}")
    return {
        "drawNo": epsd,
        "win6": win6,
        "bonus": bonus,
        "date": date,
        "numbers": ",".join(str(n) for n in win6),
    }


def read_latest_draw_no(manifest: Path) -> int:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return int(data["latestDrawNo"])


def load_history(path: Path) -> list[dict]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        items = raw.get("items") or []
    elif isinstance(raw, list):
        items = raw
    else:
        items = []
    return [x for x in items if isinstance(x, dict) and "drawNo" in x]


def save_history(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updatedAt": now_kst().isoformat(timespec="seconds"),
        "note": "auto-draw 조회 검증용 누적 이력 (Pages/FCM/엑셀과 무관)",
        "items": items,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_history_md(md_path: Path, items: list[dict]) -> None:
    lines = [
        "# Auto-draw 조회 이력 (검증용)",
        "",
        "> 이 파일은 **조회 확인용**입니다. 앱/Pages 데이터(`draws_v3.json`)와 별개이며,",
        "> 수동 **Add lotto draw** / **Fix lotto draw** 워크플로를 대체하지 않습니다.",
        "",
        f"업데이트: {now_kst().isoformat(timespec='seconds')}",
        "",
        "| 회차 | 날짜 | 번호 | 보너스 | 조회시각(KST) |",
        "|------|------|------|--------|----------------|",
    ]
    for it in items:
        win = ", ".join(str(n) for n in it.get("win6") or [])
        lines.append(
            f"| {it.get('drawNo')} | {it.get('date', '')} | {win} | "
            f"{it.get('bonus', '')} | {it.get('fetchedAt', '')} |"
        )
    lines.append("")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines), encoding="utf-8")


def upsert_history(path: Path, md_path: Path, draw: dict, attempts: int) -> list[dict]:
    items = load_history(path)
    entry = {
        "drawNo": int(draw["drawNo"]),
        "win6": list(draw["win6"]),
        "bonus": int(draw["bonus"]),
        "date": draw.get("date") or "",
        "fetchedAt": now_kst().isoformat(timespec="seconds"),
        "attempts": attempts,
        "source": "dhlottery",
    }
    replaced = False
    for i, old in enumerate(items):
        if int(old.get("drawNo", -1)) == entry["drawNo"]:
            items[i] = entry
            replaced = True
            break
    if not replaced:
        items.append(entry)
    items.sort(key=lambda x: int(x.get("drawNo", 0)), reverse=True)
    save_history(path, items)
    write_history_md(md_path, items)
    return items


def write_step_summary(text: str) -> None:
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary:
        try:
            print(text)
        except UnicodeEncodeError:
            print(text.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
                sys.stdout.encoding or "utf-8", errors="replace"
            ))
        return
    with open(summary, "a", encoding="utf-8") as f:
        f.write(text)
        if not text.endswith("\n"):
            f.write("\n")


def main() -> int:
    p = argparse.ArgumentParser(description="Auto-draw fetch-only runner")
    p.add_argument("--manifest", type=Path, default=Path("manifest.json"))
    p.add_argument(
        "--history",
        type=Path,
        default=Path("auto-draw/data/fetch_history.json"),
    )
    p.add_argument(
        "--history-md",
        type=Path,
        default=Path("auto-draw/data/FETCH_HISTORY.md"),
    )
    p.add_argument("--interval-minutes", type=int, default=5)
    p.add_argument("--max-attempts", type=int, default=26)
    p.add_argument(
        "--once",
        action="store_true",
        help="재시도 없이 1회만 (로컬/수동 디버그)",
    )
    args = p.parse_args()

    if not args.manifest.is_file():
        print(f"ERROR manifest 없음: {args.manifest}", file=sys.stderr)
        return 4

    latest = read_latest_draw_no(args.manifest)
    target = latest + 1
    max_attempts = 1 if args.once else max(1, args.max_attempts)
    interval = max(1, args.interval_minutes)

    print(f"manifest.latestDrawNo={latest} → target={target}")
    print(f"interval={interval}m max_attempts={max_attempts} (apply=OFF)")

    write_step_summary(
        "\n".join(
            [
                "## Auto draw - fetch only (apply OFF)",
                "",
                f"- target: **{target}** (manifest latest={latest})",
                f"- interval: {interval}m / max {max_attempts}",
                "- Does **not** call Add/Fix/Pages/FCM.",
                "",
            ]
        )
    )

    last_error: str | None = None
    for attempt in range(1, max_attempts + 1):
        print(f"=== attempt {attempt}/{max_attempts} @ {now_kst().isoformat(timespec='seconds')} ===")
        try:
            draw = fetch_draw(target)
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
            TypeError,
        ) as exc:
            last_error = str(exc)
            print(f"ERROR fetch: {exc}", file=sys.stderr)
            write_step_summary(f"- 시도 {attempt}: API/파싱 오류 — `{exc}`\n")
            if attempt < max_attempts:
                time.sleep(interval * 60)
            continue

        if draw is None:
            print(f"NOT_PUBLISHED target={target}")
            write_step_summary(f"- 시도 {attempt}: 미발표 (target={target})\n")
            if attempt < max_attempts:
                time.sleep(interval * 60)
            continue

        if int(draw["drawNo"]) != int(target):
            last_error = f"draw mismatch want={target} got={draw['drawNo']}"
            print(f"ERROR {last_error}", file=sys.stderr)
            write_step_summary(f"- 시도 {attempt}: {last_error}\n")
            if attempt < max_attempts:
                time.sleep(interval * 60)
            continue

        items = upsert_history(args.history, args.history_md, draw, attempt)
        nums = ", ".join(str(n) for n in draw["win6"])
        print(
            f"OK draw={draw['drawNo']} date={draw['date']} "
            f"win6={draw['win6']} bonus={draw['bonus']}"
        )
        write_step_summary(
            "\n".join(
                [
                    f"### 성공 (시도 {attempt})",
                    "",
                    f"| 회차 | 날짜 | 번호 | 보너스 |",
                    f"|------|------|------|--------|",
                    f"| **{draw['drawNo']}** | {draw['date']} | `{nums}` | **{draw['bonus']}** |",
                    "",
                    f"누적 이력: **{len(items)}**건 → `auto-draw/data/FETCH_HISTORY.md`",
                    "",
                    "**다음:** 번호가 맞으면 모바일에서 기존 **Add lotto draw**로 반영하세요.",
                    "",
                ]
            )
        )
        # GitHub Actions output
        out = os.environ.get("GITHUB_OUTPUT")
        if out:
            with open(out, "a", encoding="utf-8") as f:
                f.write("outcome=ready\n")
                f.write(f"draw_no={draw['drawNo']}\n")
                f.write(f"numbers={draw['numbers']}\n")
                f.write(f"bonus={draw['bonus']}\n")
                f.write("history_updated=true\n")
        return 0

    if last_error:
        write_step_summary(
            "\n".join(
                [
                    "### Failed - API/parse",
                    "",
                    f"마지막 오류: `{last_error}`",
                    "",
                    "폴백: Actions → **Add lotto draw** (또는 **Fix lotto draw**)",
                    "",
                ]
            )
        )
        out = os.environ.get("GITHUB_OUTPUT")
        if out:
            with open(out, "a", encoding="utf-8") as f:
                f.write("outcome=api_error\n")
                f.write(f"error={last_error}\n")
        return 3

    write_step_summary(
        "\n".join(
            [
                "### Skip - not published yet",
                "",
                f"목표 회차 **{target}** 가 상한까지 발표되지 않았습니다. (성공 종료)",
                "",
            ]
        )
    )
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write("outcome=not_published\n")
            f.write(f"target={target}\n")
            f.write("history_updated=false\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
