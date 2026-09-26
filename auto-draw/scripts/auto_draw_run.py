#!/usr/bin/env python3
"""Auto-draw 조회 전용 러너 (엑셀/Pages/FCM/add_draw/fix_draw 호출 금지).

- 목표 회차 = 가장 최근 토요일(KST) 회차 (날짜로 계산, Add 실행 여부와 무관)
- 이미 이력에 있으면 즉시 skip (백업 cron 중복 실행 대비)
- 5분 간격 조회, 성공 시 Step Summary + fetch_history 누적 후 종료
- draws_v3.json 에 같은 회차가 있으면 수동 입력과 번호 대조
- 미발표가 상한까지면 skip 성공
- API 오류가 상한까지면 exit 3 (워크플로에서 Issue)

종료 코드:
  0  번호 확보 / 이미 기록됨 / 미발표 skip
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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

API = "https://www.dhlottery.co.kr/lt645/selectPstLt645Info.do"
KST = timezone(timedelta(hours=9))
FIRST_DRAW_DATE = date(2002, 12, 7)  # 1회 추첨일 (토)


def now_kst() -> datetime:
    return datetime.now(KST)


def expected_draw_no(today: date | None = None) -> int:
    """가장 최근 토요일(오늘 포함)의 회차 번호."""
    today = today or now_kst().date()
    last_sat = today - timedelta(days=(today.weekday() - 5) % 7)
    return (last_sat - FIRST_DRAW_DATE).days // 7 + 1


def fetch_draw(draw_no: int, timeout: int = 20) -> dict | None:
    ts = int(time.time() * 1000)
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
    draw_date = f"{ymd[0:4]}.{ymd[4:6]}.{ymd[6:8]}" if len(ymd) == 8 else ymd
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
        "date": draw_date,
        "numbers": ",".join(str(n) for n in win6),
    }


def find_manual_draw(draws_path: Path, draw_no: int) -> dict | None:
    if not draws_path.is_file():
        return None
    data = json.loads(draws_path.read_text(encoding="utf-8"))
    items = data.get("draws") if isinstance(data, dict) else data
    for it in items or []:
        if isinstance(it, dict) and int(it.get("drawNo", -1)) == draw_no:
            return it
    return None


def compare_manual(draw: dict, manual: dict | None) -> str:
    if manual is None:
        return "미입력"
    same = sorted(manual.get("win6") or []) == sorted(draw["win6"]) and int(
        manual.get("bonus", -1)
    ) == int(draw["bonus"])
    return "일치" if same else "불일치"


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
        "> `수동 입력 대조`: 조회 시점에 Add로 들어간 번호와 비교한 결과 (미입력 = 아직 Add 전)",
        "",
        f"업데이트: {now_kst().isoformat(timespec='seconds')}",
        "",
        "| 회차 | 날짜 | 번호 | 보너스 | 조회시각(KST) | 수동 입력 대조 |",
        "|------|------|------|--------|----------------|----------------|",
    ]
    for it in items:
        win = ", ".join(str(n) for n in it.get("win6") or [])
        lines.append(
            f"| {it.get('drawNo')} | {it.get('date', '')} | {win} | "
            f"{it.get('bonus', '')} | {it.get('fetchedAt', '')} | {it.get('manualMatch', '-')} |"
        )
    lines.append("")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines), encoding="utf-8")


def upsert_history(
    path: Path, md_path: Path, draw: dict, attempts: int, manual_match: str
) -> list[dict]:
    items = load_history(path)
    entry = {
        "drawNo": int(draw["drawNo"]),
        "win6": list(draw["win6"]),
        "bonus": int(draw["bonus"]),
        "date": draw.get("date") or "",
        "fetchedAt": now_kst().isoformat(timespec="seconds"),
        "attempts": attempts,
        "manualMatch": manual_match,
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
            enc = sys.stdout.encoding or "utf-8"
            print(text.encode(enc, errors="replace").decode(enc, errors="replace"))
        return
    with open(summary, "a", encoding="utf-8") as f:
        f.write(text)
        if not text.endswith("\n"):
            f.write("\n")


def write_outputs(**values: str) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if not out:
        return
    with open(out, "a", encoding="utf-8") as f:
        for k, v in values.items():
            f.write(f"{k}={v}\n")


def main() -> int:
    p = argparse.ArgumentParser(description="Auto-draw fetch-only runner")
    p.add_argument("--draw-no", type=int, default=None, help="목표 회차 수동 지정 (기본: 최근 토요일 회차)")
    p.add_argument("--draws", type=Path, default=Path("draws_v3.json"))
    p.add_argument("--history", type=Path, default=Path("auto-draw/data/fetch_history.json"))
    p.add_argument("--history-md", type=Path, default=Path("auto-draw/data/FETCH_HISTORY.md"))
    p.add_argument("--interval-minutes", type=int, default=5)
    p.add_argument("--max-attempts", type=int, default=48)
    p.add_argument("--once", action="store_true", help="재시도 없이 1회만 (디버그)")
    args = p.parse_args()

    target = args.draw_no or expected_draw_no()
    max_attempts = 1 if args.once else max(1, args.max_attempts)
    interval = max(1, args.interval_minutes)

    print(f"target={target} interval={interval}m max_attempts={max_attempts} (apply=OFF)")
    write_step_summary(
        "\n".join(
            [
                "## Auto draw - fetch only (apply OFF)",
                "",
                f"- target: **{target}** (최근 토요일 회차)",
                f"- interval: {interval}m / max {max_attempts}",
                "- Does **not** call Add/Fix/Pages/FCM.",
                "",
            ]
        )
    )

    if args.draw_no is None and any(
        int(it.get("drawNo", -1)) == target for it in load_history(args.history)
    ):
        print(f"ALREADY_RECORDED target={target}")
        write_step_summary(f"### 이미 기록됨\n\n회차 **{target}** 는 이력에 이미 있습니다. (성공 종료)\n")
        write_outputs(outcome="already_recorded", target=str(target), history_updated="false")
        return 0

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
            last_error = None
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

        manual_match = compare_manual(draw, find_manual_draw(args.draws, target))
        items = upsert_history(args.history, args.history_md, draw, attempt, manual_match)
        nums = ", ".join(str(n) for n in draw["win6"])
        print(
            f"OK draw={draw['drawNo']} date={draw['date']} "
            f"win6={draw['win6']} bonus={draw['bonus']} manual={manual_match}"
        )
        write_step_summary(
            "\n".join(
                [
                    f"### 성공 (시도 {attempt})",
                    "",
                    "| 회차 | 날짜 | 번호 | 보너스 | 수동 입력 대조 |",
                    "|------|------|------|--------|----------------|",
                    f"| **{draw['drawNo']}** | {draw['date']} | `{nums}` | **{draw['bonus']}** | {manual_match} |",
                    "",
                    f"누적 이력: **{len(items)}**건 → `auto-draw/data/FETCH_HISTORY.md`",
                    "",
                    "**다음:** 수동 입력이 `미입력`이면 **Add lotto draw**, `불일치`면 **Fix lotto draw**로 확인하세요.",
                    "",
                ]
            )
        )
        write_outputs(
            outcome="ready",
            draw_no=str(draw["drawNo"]),
            numbers=draw["numbers"],
            bonus=str(draw["bonus"]),
            manual_match=manual_match,
            history_updated="true",
        )
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
        write_outputs(outcome="api_error", error=last_error)
        return 3

    write_step_summary(
        "\n".join(
            [
                "### Skip - not published yet",
                "",
                f"목표 회차 **{target}** 가 상한까지 발표되지 않았습니다. (성공 종료, 다음 백업 cron이 이어서 조회)",
                "",
            ]
        )
    )
    write_outputs(outcome="not_published", target=str(target), history_updated="false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
