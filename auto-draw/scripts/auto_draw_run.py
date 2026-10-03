#!/usr/bin/env python3
"""Auto-draw 조회 전용 러너 (엑셀/Pages/FCM/add_draw/fix_draw 호출 금지).

GitHub 예약 실행은 수 시간 지연되거나 누락될 수 있으므로 "정시 시작"에 의존하지 않는다.
토요일 이른 시각부터 여러 번 시작을 시도하고, 시작된 실행은
  - 추첨 전이면 20:35(KST)까지 대기
  - 이후 5분 간격 조회, 성공 시 이력 기록
  - 실행 시간 예산(기본 5.5시간)이 다 되면 relay=true 를 내보내 워크플로가 자신을 다시 호출
하는 방식으로 성공 또는 마감(일요일 12:00 KST)까지 이어간다.

출력(outcome):
  ready             번호 확보·기록
  already_recorded  이미 이력에 있음
  relay_waiting     추첨 전 대기 중 예산 소진 → 이어달리기
  relay_polling     조회 중 예산 소진 → 이어달리기
  api_error         API/파싱 오류 1시간 지속 → 알림 + 이어달리기
  deadline_missed   마감까지 미발표 → 알림
  once_*            --once 디버그 결과
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
from datetime import time as dtime
from pathlib import Path

API = "https://www.dhlottery.co.kr/lt645/selectPstLt645Info.do"
KST = timezone(timedelta(hours=9))
FIRST_DRAW_DATE = date(2002, 12, 7)  # 1회 추첨일 (토)
POLL_START = dtime(20, 35)  # 추첨 방송 이후부터 조회
DEADLINE_DAYS, DEADLINE_TIME = 1, dtime(12, 0)  # 추첨 다음날 12:00 KST
ERROR_ALERT_COUNT = 12  # 5분 간격 기준 약 1시간 연속 오류


def now_kst() -> datetime:
    return datetime.now(KST)


def expected_draw_no(today: date | None = None) -> int:
    """가장 최근 토요일(오늘 포함)의 회차 번호."""
    today = today or now_kst().date()
    last_sat = today - timedelta(days=(today.weekday() - 5) % 7)
    return (last_sat - FIRST_DRAW_DATE).days // 7 + 1


def draw_saturday(draw_no: int) -> date:
    return FIRST_DRAW_DATE + timedelta(days=7 * (draw_no - 1))


def schedule_delay_minutes(cron: str, now_utc: datetime) -> int | None:
    """'M H * * D' 형식 cron 의 직전 예정 시각 대비 실제 시작 지연(분)."""
    parts = cron.split()
    if len(parts) != 5:
        return None
    try:
        minute, hour, dow = int(parts[0]), int(parts[1]), int(parts[4])
    except ValueError:
        return None
    py_dow = (dow - 1) % 7  # cron 0=일 → python 6=일
    for back in range(0, 8):
        day = (now_utc - timedelta(days=back)).date()
        if day.weekday() != py_dow:
            continue
        slot = datetime.combine(day, dtime(hour, minute), timezone.utc)
        if slot <= now_utc:
            return int((now_utc - slot).total_seconds() // 60)
    return None


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
    if epsd != draw_no:
        raise ValueError(f"회차 불일치: 요청 {draw_no}, 응답 {epsd}")
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


def load_manual_draws(draws_url: str, draws_path: Path) -> list:
    """앱이 실제로 받는 Pages 데이터 우선, 실패 시 체크아웃된 파일."""
    try:
        sep = "&" if "?" in draws_url else "?"
        with urllib.request.urlopen(f"{draws_url}{sep}_={int(time.time())}", timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        if not draws_path.is_file():
            return []
        data = json.loads(draws_path.read_text(encoding="utf-8"))
    items = data.get("draws") if isinstance(data, dict) else data
    return items or []


def compare_manual(draw: dict, manual_items: list) -> str:
    manual = next(
        (it for it in manual_items if isinstance(it, dict) and int(it.get("drawNo", -1)) == draw["drawNo"]),
        None,
    )
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
        "> 실행 시작·실패 기록은 이슈 **[auto-draw] 실행 이력** 에 남습니다.",
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


def upsert_history(path: Path, md_path: Path, draw: dict, attempts: int, manual_match: str) -> int:
    items = [it for it in load_history(path) if int(it.get("drawNo", -1)) != draw["drawNo"]]
    items.append(
        {
            "drawNo": int(draw["drawNo"]),
            "win6": list(draw["win6"]),
            "bonus": int(draw["bonus"]),
            "date": draw.get("date") or "",
            "fetchedAt": now_kst().isoformat(timespec="seconds"),
            "attempts": attempts,
            "manualMatch": manual_match,
            "source": "dhlottery",
        }
    )
    items.sort(key=lambda x: int(x.get("drawNo", 0)), reverse=True)
    save_history(path, items)
    write_history_md(md_path, items)
    return len(items)


def write_step_summary(text: str) -> None:
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary:
        enc = sys.stdout.encoding or "utf-8"
        print(text.encode(enc, errors="replace").decode(enc, errors="replace"))
        return
    with open(summary, "a", encoding="utf-8") as f:
        f.write(text if text.endswith("\n") else text + "\n")


def write_outputs(**values: object) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    pairs = {k: str(v).replace("\n", " ") for k, v in values.items()}
    print("OUTPUTS " + " ".join(f"{k}={v}" for k, v in pairs.items()))
    if not out:
        return
    with open(out, "a", encoding="utf-8") as f:
        for k, v in pairs.items():
            f.write(f"{k}={v}\n")


def trigger_info() -> tuple[str, str]:
    event = os.environ.get("TRIGGER_EVENT", "local")
    hop = os.environ.get("RELAY_HOP", "0") or "0"
    cron = os.environ.get("TRIGGER_SCHEDULE", "")
    if event == "schedule" and cron:
        delay = schedule_delay_minutes(cron, datetime.now(timezone.utc))
        label = f"예약 실행 (`{cron}` UTC, 지연 {delay}분)" if delay is not None else f"예약 실행 (`{cron}`)"
    elif event == "workflow_dispatch" and hop != "0":
        label = f"이어달리기 {hop}번째"
    elif event == "workflow_dispatch":
        label = "수동 실행"
    else:
        label = event
    return label, hop


def main() -> int:
    p = argparse.ArgumentParser(description="Auto-draw fetch-only runner")
    p.add_argument("--draw-no", type=int, default=None, help="목표 회차 (기본: 최근 토요일 회차)")
    p.add_argument("--draws-url", default="https://s73325475-cyber.github.io/lotto-data/draws_v3.json")
    p.add_argument("--draws", type=Path, default=Path("draws_v3.json"))
    p.add_argument("--history", type=Path, default=Path("auto-draw/data/fetch_history.json"))
    p.add_argument("--history-md", type=Path, default=Path("auto-draw/data/FETCH_HISTORY.md"))
    p.add_argument("--interval-minutes", type=int, default=5)
    p.add_argument("--budget-minutes", type=int, default=330, help="이 실행의 최대 사용 시간 (job 제한 6시간 미만)")
    p.add_argument("--once", action="store_true", help="대기·재시도 없이 1회만 조회 (디버그)")
    p.add_argument("--check-only", action="store_true", help="목표 회차·기록 여부만 출력")
    args = p.parse_args()

    started = time.monotonic()
    budget = max(5, args.budget_minutes) * 60
    interval = max(1, args.interval_minutes) * 60
    target = args.draw_no or expected_draw_no()
    sat = draw_saturday(target)
    poll_start = datetime.combine(sat, POLL_START, KST)
    deadline = datetime.combine(sat + timedelta(days=DEADLINE_DAYS), DEADLINE_TIME, KST)
    recorded = any(int(it.get("drawNo", -1)) == target for it in load_history(args.history))
    trigger, hop = trigger_info()

    if args.check_only:
        write_outputs(target=target, recorded=str(recorded).lower(), trigger=trigger)
        return 0

    write_step_summary(
        "\n".join(
            [
                "## Auto draw - fetch only (apply OFF)",
                "",
                f"- 대상 회차: **{target}** ({sat.isoformat()} 추첨)",
                f"- 시작: {now_kst().strftime('%m/%d %H:%M')} KST · {trigger}",
                f"- 조회 시작 {POLL_START.strftime('%H:%M')} / 마감 {deadline.strftime('%m/%d %H:%M')} KST",
                "- Add/Fix/Pages/FCM 을 호출하지 않습니다.",
                "",
            ]
        )
    )

    if recorded and args.draw_no is None:
        write_step_summary(f"### 이미 기록됨\n\n회차 **{target}** 는 이력에 이미 있습니다.\n")
        write_outputs(outcome="already_recorded", target=target, relay="false", history_updated="false", trigger=trigger)
        return 0

    def remaining() -> float:
        return budget - (time.monotonic() - started)

    attempt = 0
    consecutive_errors = 0
    last_error = ""
    while True:
        now = now_kst()
        if not args.once and now < poll_start:
            wait = (poll_start - now).total_seconds()
            if wait > remaining() - 60:
                time.sleep(max(0, remaining() - 60))
                write_step_summary(f"- 추첨 전 대기 중 실행 시간 소진 → 이어달리기\n")
                write_outputs(outcome="relay_waiting", target=target, relay="true", history_updated="false", trigger=trigger)
                return 0
            print(f"waiting {int(wait // 60)}m until {poll_start.isoformat()}")
            time.sleep(wait)
            continue

        attempt += 1
        print(f"=== attempt {attempt} @ {now_kst().isoformat(timespec='seconds')} target={target} ===")
        try:
            draw = fetch_draw(target)
            consecutive_errors = 0
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            draw = None
            consecutive_errors += 1
            last_error = str(exc)
            print(f"ERROR fetch: {exc}", file=sys.stderr)

        if draw is not None:
            manual = compare_manual(draw, load_manual_draws(args.draws_url, args.draws))
            total = upsert_history(args.history, args.history_md, draw, attempt, manual)
            nums = ", ".join(str(n) for n in draw["win6"])
            print(f"OK draw={draw['drawNo']} win6={draw['win6']} bonus={draw['bonus']} manual={manual}")
            write_step_summary(
                "\n".join(
                    [
                        f"### 성공 (시도 {attempt})",
                        "",
                        "| 회차 | 날짜 | 번호 | 보너스 | 수동 입력 대조 |",
                        "|------|------|------|--------|----------------|",
                        f"| **{draw['drawNo']}** | {draw['date']} | `{nums}` | **{draw['bonus']}** | {manual} |",
                        "",
                        f"누적 이력: **{total}**건 → `auto-draw/data/FETCH_HISTORY.md`",
                        "",
                    ]
                )
            )
            write_outputs(
                outcome="ready", target=target, relay="false", history_updated="true",
                draw_no=draw["drawNo"], draw_date=draw["date"], numbers=nums, bonus=draw["bonus"],
                manual_match=manual, attempts=attempt, trigger=trigger,
            )
            return 0

        if args.once:
            outcome = "once_error" if consecutive_errors else "once_not_published"
            write_step_summary(f"- 1회 조회 결과: {outcome} {last_error}\n")
            write_outputs(outcome=outcome, target=target, relay="false", history_updated="false", error=last_error, trigger=trigger)
            return 0

        if now_kst() >= deadline:
            write_step_summary(f"### 마감\n\n{deadline.strftime('%m/%d %H:%M')} KST 까지 회차 {target} 를 가져오지 못했습니다. 마지막 오류: `{last_error or '미발표'}`\n")
            write_outputs(outcome="deadline_missed", target=target, relay="false", history_updated="false", error=last_error or "not_published", attempts=attempt, trigger=trigger)
            return 0

        if consecutive_errors >= ERROR_ALERT_COUNT:
            write_step_summary(f"### API 오류 지속\n\n{consecutive_errors}회 연속 오류: `{last_error}` → 알림 후 이어달리기\n")
            write_outputs(outcome="api_error", target=target, relay="true", history_updated="false", error=last_error, attempts=attempt, trigger=trigger)
            return 0

        if remaining() < interval + 60:
            write_step_summary(f"- 조회 {attempt}회, 아직 미발표 · 실행 시간 소진 → 이어달리기\n")
            write_outputs(outcome="relay_polling", target=target, relay="true", history_updated="false", attempts=attempt, trigger=trigger)
            return 0

        print(f"{'error' if consecutive_errors else 'not published'}; sleep {interval // 60}m")
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
