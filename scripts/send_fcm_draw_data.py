#!/usr/bin/env python3
"""Pages 배포 후 FCM data-only ping → 앱이 sync·보관함 대조·로컬 알림.

환경 변수:
  FIREBASE_SERVICE_ACCOUNT_JSON  서비스 계정 JSON 문자열(또는 파일 경로)
  FIREBASE_PROJECT_ID            (선택) 미설정 시 JSON의 project_id 사용

인자:
  --draw-no 1341   data.drawNo (선택)
  --dry-run        요청 본문만 출력
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


SCOPES = ("https://www.googleapis.com/auth/firebase.messaging",)


def _load_service_account(raw: str) -> dict:
    raw = raw.strip()
    if not raw:
        raise SystemExit("FIREBASE_SERVICE_ACCOUNT_JSON 이 비어 있습니다.")
    if raw.startswith("{"):
        return json.loads(raw)
    path = os.path.expanduser(raw)
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    raise SystemExit(
        "FIREBASE_SERVICE_ACCOUNT_JSON 은 JSON 문자열 또는 파일 경로여야 합니다."
    )


def _access_token(sa: dict) -> str:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account
    except ImportError as e:
        raise SystemExit(
            "google-auth 가 필요합니다: pip install google-auth"
        ) from e

    creds = service_account.Credentials.from_service_account_info(
        sa, scopes=SCOPES
    )
    creds.refresh(Request())
    if not creds.token:
        raise SystemExit("FCM 액세스 토큰을 받지 못했습니다.")
    return creds.token


def send_draw_data_ready(
    *,
    project_id: str,
    token: str,
    draw_no: str | None,
    dry_run: bool,
) -> None:
    data = {"type": "draw_data_ready"}
    if draw_no:
        data["drawNo"] = str(draw_no)

    body = {
        "message": {
            "topic": "draw_data",
            "data": data,
            "android": {"priority": "high"},
        }
    }
    url = (
        f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
    )
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")

    if dry_run:
        print(url)
        print(json.dumps(body, ensure_ascii=False, indent=2))
        return

    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            print(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"FCM 전송 실패 HTTP {e.code}: {err}") from e


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draw-no", default="", help="회차 (선택)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--allow-missing-secret",
        action="store_true",
        help="시크릿 없으면 0으로 종료(배포 파이프라인용)",
    )
    args = parser.parse_args()

    raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        msg = "FIREBASE_SERVICE_ACCOUNT_JSON missing - skip FCM"
        if args.allow_missing_secret:
            print(f"::warning::{msg}")
            return
        raise SystemExit(msg)

    sa = _load_service_account(raw)
    project_id = (
        os.environ.get("FIREBASE_PROJECT_ID", "").strip()
        or sa.get("project_id")
        or ""
    )
    if not project_id:
        raise SystemExit("FIREBASE_PROJECT_ID / service account project_id 없음")

    if args.dry_run:
        send_draw_data_ready(
            project_id=project_id,
            token="DRY_RUN",
            draw_no=args.draw_no or None,
            dry_run=True,
        )
        return

    token = _access_token(sa)
    send_draw_data_ready(
        project_id=project_id,
        token=token,
        draw_no=args.draw_no or None,
        dry_run=False,
    )
    print(f"FCM draw_data ping OK (drawNo={args.draw_no or '-'})")


if __name__ == "__main__":
    main()
