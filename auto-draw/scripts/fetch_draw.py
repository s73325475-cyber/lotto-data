#!/usr/bin/env python3
"""동행복권 회차 조회 (실험용).

프로덕션 `.github` / `add_draw.py` 를 호출하지 않습니다.
로컬·초안 워크플로에서만 사용하세요.

종료 코드:
  0  성공 (번호 확보) 또는 --allow-empty 로 미발표 skip
  2  미발표 (list 비어 있음) — 재시도 대상
  3  API/파싱 오류 — 개발자 알림 대상
  4  인자/설정 오류
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://www.dhlottery.co.kr/lt645/selectPstLt645Info.do"


def fetch_draw(draw_no: int | None = None, timeout: int = 20) -> dict | None:
    """회차 조회. draw_no=None 이면 API 기본(보통 최신). 미발표면 None."""
    ts = int(time.time() * 1000)
    if draw_no is None:
        url = f"{API}?_={ts}"
    else:
        url = f"{API}?srchLtEpsd={draw_no}&_={ts}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; lotto-data-auto-draw-draft/1.0)",
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


def main() -> int:
    p = argparse.ArgumentParser(description="Fetch dhlottery draw (draft / dry-run)")
    p.add_argument("--draw-no", type=int, default=None, help="조회 회차 (없으면 API 기본)")
    p.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="있으면 latestDrawNo+1 을 목표 회차로 사용",
    )
    p.add_argument(
        "--allow-empty",
        action="store_true",
        help="미발표 시 exit 0 (cron skip 성공용)",
    )
    p.add_argument("--json-out", type=Path, default=None, help="결과 JSON 저장 경로")
    args = p.parse_args()

    target = args.draw_no
    if args.manifest is not None:
        if not args.manifest.is_file():
            print(f"ERROR manifest 없음: {args.manifest}", file=sys.stderr)
            return 4
        latest = read_latest_draw_no(args.manifest)
        target = latest + 1
        print(f"manifest.latestDrawNo={latest} → target={target}")

    try:
        draw = fetch_draw(target)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR fetch failed: {exc}", file=sys.stderr)
        err = {"ok": False, "reason": "fetch_error", "message": str(exc), "target": target}
        if args.json_out:
            args.json_out.write_text(json.dumps(err, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 3

    if draw is None:
        msg = f"NOT_PUBLISHED target={target}"
        print(msg)
        empty = {"ok": False, "reason": "not_published", "target": target}
        if args.json_out:
            args.json_out.write_text(json.dumps(empty, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0 if args.allow_empty else 2

    if target is not None and int(draw["drawNo"]) != int(target):
        print(
            f"ERROR draw mismatch want={target} got={draw['drawNo']}",
            file=sys.stderr,
        )
        return 3

    out = {"ok": True, "draw": draw}
    print(
        f"OK draw={draw['drawNo']} date={draw['date']} "
        f"win6={draw['win6']} bonus={draw['bonus']}"
    )
    if args.json_out:
        args.json_out.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
