# 외부 핑으로 Auto draw 정시 깨우기

## 왜 필요한가

GitHub `schedule`(cron)은 **수 시간 지연**될 수 있다.

| 회차 | 예정 | 실제 시작 | 지연 |
|------|------|-----------|------|
| 1247 (10/24) | 토 20:30 | 토 23:45 | **195분** |
| 1248 (10/31) | 토 20:30 | 일 01:14 | **284분** |

저녁에 cron만 촘촘히 넣어도, 큐가 밀리면 **전부 같이** 늦는다.  
레포 안 대책은 **낮에 자리 잡기 + workflow_dispatch 이어달리기**이고,  
더 확실한 방법은 **외부 스케줄러가 `repository_dispatch`로 정시에 깨우는 것**이다.

## 설정 (cron-job.org / EasyCron 등)

1. GitHub → Settings → Developer settings → Personal access token  
   - classic: `repo` + `workflow`  
   - 또는 fine-grained: Actions 쓰기 + Contents 읽기
2. 토큰을 스케줄러 비밀값에만 저장 (레포에 커밋 금지)
3. **토 20:35 KST** (또는 20:36~20:40)에 HTTP POST:

```http
POST https://api.github.com/repos/s73325475-cyber/lotto-data/dispatches
Accept: application/vnd.github+json
Authorization: Bearer <PAT>
Content-Type: application/json

{"event_type":"auto-draw-ping"}
```

4. (선택) 토 20:40, 20:50에 한 번씩 더 — 이미 성공이면 즉시 종료

`event_type` 은 워크플로의 `repository_dispatch.types: [auto-draw-ping]` 과 같아야 한다.

## curl 예

```bash
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer $LOTTTO_DATA_PAT" \
  https://api.github.com/repos/s73325475-cyber/lotto-data/dispatches \
  -d '{"event_type":"auto-draw-ping"}'
```

성공 시 HTTP **204**. Actions → Auto draw 에 `repository_dispatch` 실행이 생긴다.
