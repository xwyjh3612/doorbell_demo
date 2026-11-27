param(
    [int]$HttpPort = 18891,
    [switch]$NoBrowser,
    [string]$Python = 'F:\Espressif\python_env\idf5.4_py3.11_env\Scripts\python.exe'
)
$ErrorActionPreference = 'Stop'
$viewerWorkspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$viewerMetadata = Join-Path $viewerWorkspace 'build\ttl-viewer-service.json'
$viewerUrl = "http://127.0.0.1:$HttpPort"
# Reuse the existing collector; never open COM13 for a second reader.
$callCollector = $null
foreach ($bridgePort in @(18892, 18889)) {
    try {
        $state = Invoke-RestMethod -Uri "http://127.0.0.1:$bridgePort/" -TimeoutSec 1
        # An unplugged bridge will reconnect on its own. Old bridges could die
        # on unplug and still serve stale lines, so check the new status field.
        if ($null -ne $state.connected -and $null -ne $state.lines -and $state.port) {
            $callCollector = $state.port
            break
        }
    } catch {}
}
if ($callCollector) {
    Write-Output "复用语音对讲串口采集：$callCollector"
} else {
    & (Join-Path $viewerWorkspace 'examples\radar_monitor\start.ps1') -Python $Python
}
$viewerReady = $false
try {
    $viewerResponse = Invoke-RestMethod -Uri "$viewerUrl/api/state" -TimeoutSec 2
    $viewerReady = $null -ne $viewerResponse.epoch
} catch {}
if (-not $viewerReady) {
    if (-not (Test-Path -LiteralPath $Python)) { throw "Python未找到：$Python" }
    $viewerScript = Join-Path $PSScriptRoot 'server.py'
    $viewerArgs = @(('"' + $viewerScript + '"'), '--http-port', $HttpPort)
    $viewerProcess = Start-Process -FilePath $Python -ArgumentList $viewerArgs `
        -WorkingDirectory $viewerWorkspace -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $viewerWorkspace 'build\ttl-viewer.stdout.log') `
        -RedirectStandardError (Join-Path $viewerWorkspace 'build\ttl-viewer.stderr.log') -PassThru
    @{pid=$viewerProcess.Id; url=$viewerUrl; script=$viewerScript; started_at=(Get-Date -Format o)} |
        ConvertTo-Json | Set-Content -LiteralPath $viewerMetadata
    for ($viewerAttempt = 0; $viewerAttempt -lt 20; $viewerAttempt++) {
        try {
            $viewerResponse = Invoke-RestMethod -Uri "$viewerUrl/api/state" -TimeoutSec 1
            if ($null -ne $viewerResponse.epoch) { $viewerReady = $true; break }
        } catch { Start-Sleep -Milliseconds 250 }
    }
    if (-not $viewerReady) { throw '日志工具启动失败，请查看 build\ttl-viewer.stderr.log' }
}
if (-not $NoBrowser) { Start-Process $viewerUrl }
Write-Output "TTL实时日志：$viewerUrl"
Write-Output '关闭网页不会停止串口记录。日志文件路径在页面顶部。'
