# Agent 지시 — auto-draw 작업실

당신은 `C:\lotto-data\auto-draw`에서 **동행복권 자동 회차 반영**을 검토·구현하는 Agent입니다.

## 범위

- **기본: `C:\lotto-data\auto-draw`만**  
- 프로덕션 `.github/workflows/` / `scripts/add_draw.py` 는 **사용자 승인 없이 수정·추가하지 말 것**  
- 앱 `C:\lotto_wizard`는 읽기만 (스키마/수신 확인용). 앱 기능 변경은 요청 있을 때만.

## 원칙

1. 기존 수동 `Add lotto draw` / Pages / FCM을 깨지 말 것 (`add-draw.yml` 편집 금지)  
2. 자동화는 **이 폴더에 DRAFT로** 두고, 검증 후 **새 파일 추가**로만 메인에 연결  
3. 이미 latest면 cron이 **빨간 실패가 아니라 skip 성공**이어야 함  
4. 번호 오탐 방지: 교차검증 또는 dry-run 기간을 둘 것  
5. API 실패 시 개발자 알림 → 수동 Add lotto draw 폴백

## 첫 작업 제안

1. `docs/PLAN.md`를 읽고 보완  
2. `scripts/fetch_draw.py` 초안 (회차 조회 → win6+bonus 출력, dry-run)  
3. 로컬에서 1241 조회 재현  
4. `auto-draw.yml` 초안 (아직 기본 브랜치 자동 반영 금지 옵션 가능)  
5. README / notes에 실험 결과 기록

## 금지

- 검증 없이 프로덕션 Pages에 가짜 회차 커밋  
- FCM을 불필요하게 실사용자에게 반복 발송  
- `google-services` / Firebase 서비스 계정 JSON을 repo에 커밋  
- **현 단계에서** `.github/workflows/` 수정·추가 (특히 `add-draw.yml`)
