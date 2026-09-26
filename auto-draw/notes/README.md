# notes

실험 로그·스크린샷·curl 결과를 여기 남기세요.

## 2026-09-16

- Probe run: https://github.com/s73325475-cyber/lotto-data/actions/runs/35105446151
- 1241: 7,13,16,23,24,43 bonus 9
- 확인용 웹앱: `check-app/` — `python check-app/server.py` → http://127.0.0.1:8765
- `srchLtEpsd` 없이 API 호출 시 최신 회차 반환 확인
- 시안 이미지: Cursor assets `lotto-check-app-mockup.png`
- 당첨 이력 탭 + `check-app/data/history.json` 누적 저장 (회차 upsert)
- 최종 의도 문서화: Actions 자동조회 + 재시도 + API실패 Issue → 수동 Add lotto draw
- 합의: 2~3주 fetch-only 관찰 → 문제 없으면 cron 결과 apply(Add 경로) 연계. Fix/Add 유지
- cron 20:45 KST + history push rebase 보강 (230ebf6)

