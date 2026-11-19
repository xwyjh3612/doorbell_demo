$ErrorActionPreference = 'Stop'
$radarWorkspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$radarMetadata = Join-Path $radarWorkspace 'build\radar-monitor-service.json'
if (-not (Test-Path -LiteralPath $radarMetadata)) {
    Write-Output '没有采集服务记录。'
    return
}
$radarRecord = Get-Content -LiteralPath $radarMetadata -Raw | ConvertFrom-Json
$radarProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $($radarRecord.pid)"
if (-not $radarProcess) { Write-Output '采集服务已停止。'; return }
if ($radarProcess.Name -notmatch '^python(w)?\.exe$' -or
    $radarProcess.CommandLine -notmatch 'radar_monitor[\\/]monitor\.py') {
    throw '进程身份与采集服务不符，未停止任何进程。'
}
Stop-Process -Id $radarRecord.pid
Write-Output "采集已停止，日志保留在：$($radarRecord.output)"
