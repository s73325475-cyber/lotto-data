param([string]$ScriptPath)
$log = "C:\lotto-data\auto-draw\logs\ping_{0:yyyyMMdd_HHmmss}.log" -f (Get-Date)
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ScriptPath *>> $log
