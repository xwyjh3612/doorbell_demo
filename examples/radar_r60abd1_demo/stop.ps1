$ErrorActionPreference = 'Stop'
$r60Workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$r60Script = Join-Path $PSScriptRoot 'demo.py'
$r60Metadata = Join-Path $r60Workspace 'build\r60abd1-demo-service.json'
if (-not (Test-Path -LiteralPath $r60Metadata)) { Write-Output '没有 60GHz demo 服务记录。'; return }
$r60Record = Get-Content -LiteralPath $r60Metadata -Raw | ConvertFrom-Json
$r60Process = Get-CimInstance Win32_Process -Filter "ProcessId = $($r60Record.pid)"
if (-not $r60Process) { Write-Output '60GHz demo 已停止。'; return }
if ($r60Process.Name -notmatch '^python(w)?\.exe$' -or -not $r60Process.CommandLine.Contains($r60Script)) {
    throw '进程身份不符，未停止任何进程。'
}
Stop-Process -Id $r60Record.pid
Write-Output '60GHz demo 已停止；原有串口采集服务继续记录。'
