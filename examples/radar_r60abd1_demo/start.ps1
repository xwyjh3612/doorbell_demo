param(
    [string]$Port = 'COM13',
    [int]$MonitorPort = 18888,
    [int]$HttpPort = 18890,
    [string]$Python = 'F:\Espressif\python_env\idf5.4_py3.11_env\Scripts\python.exe'
)
$ErrorActionPreference = 'Stop'
$r60Workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$r60Script = Join-Path $PSScriptRoot 'demo.py'
$r60Metadata = Join-Path $r60Workspace 'build\r60abd1-demo-service.json'
if (Test-Path -LiteralPath $r60Metadata) {
    $r60Existing = Get-Content -LiteralPath $r60Metadata -Raw | ConvertFrom-Json
    $r60Process = Get-CimInstance Win32_Process -Filter "ProcessId = $($r60Existing.pid)"
    if ($r60Process -and $r60Process.Name -match '^python(w)?\.exe$' -and
        $r60Process.CommandLine.Contains($r60Script)) {
        Write-Output "60GHz demo 已运行：$($r60Existing.url)"
        return
    }
}
if (-not (Test-Path -LiteralPath $Python)) { throw "Python 未找到：$Python" }
& (Join-Path $r60Workspace 'examples\radar_monitor\start.ps1') -Port $Port -HttpPort $MonitorPort -Python $Python
# The collector may already use another HTTP port; use its actual recorded URL.
$r60Monitor = Get-Content (Join-Path $r60Workspace 'build\radar-monitor-service.json') -Raw | ConvertFrom-Json
$r60Output = Join-Path $r60Workspace ('build\r60abd1-demo-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $r60Output -Force | Out-Null
$r60Args = @(('"' + $r60Script + '"'), '--source', $r60Monitor.url, '--http-port', $HttpPort)
$r60Launched = Start-Process -FilePath $Python -ArgumentList $r60Args -WorkingDirectory $r60Workspace `
    -WindowStyle Hidden -RedirectStandardOutput (Join-Path $r60Output 'service.stdout.log') `
    -RedirectStandardError (Join-Path $r60Output 'service.stderr.log') -PassThru
try {
    $r60Ready = $false
    for ($r60Try = 0; $r60Try -lt 20; $r60Try++) {
        if ($r60Launched.HasExited) { throw 'demo 启动失败，请查看 service.stderr.log。' }
        try {
            $r60State = Invoke-RestMethod "http://127.0.0.1:$HttpPort/api/state" -TimeoutSec 1
            if ($r60State.model -like 'R60ABD1*') { $r60Ready = $true; break }
        } catch { }
        Start-Sleep -Milliseconds 250
    }
    if (-not $r60Ready) { throw 'demo 页面没有就绪，请查看 service.stderr.log。' }
    $r60Record = @{pid=$r60Launched.Id; script=$r60Script; output=$r60Output;
        url="http://127.0.0.1:$HttpPort"; source=$r60Monitor.url; started_at=(Get-Date -Format o)}
    $r60Record | ConvertTo-Json | Set-Content -LiteralPath $r60Metadata -Encoding UTF8
    Write-Output "60GHz demo 已启动：$($r60Record.url)"
    Write-Output "运行日志：$r60Output"
} catch {
    if (-not $r60Launched.HasExited) { Stop-Process -Id $r60Launched.Id }
    throw
}
