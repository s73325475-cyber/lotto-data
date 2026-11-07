# Auto draw 외부 핑 — 이 PC의 gh 로그인으로 repository_dispatch 호출
# (별도 PAT 없이 동작. 클라우드 크론에는 PAT가 필요함)
$ErrorActionPreference = "Stop"
$repo = "s73325475-cyber/lotto-data"
$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
try {
  gh api "repos/$repo/dispatches" -f event_type="auto-draw-ping" | Out-Null
  Write-Output "[$ts] OK auto-draw-ping → $repo"
  exit 0
} catch {
  Write-Output "[$ts] FAIL $($_.Exception.Message)"
  exit 1
}
