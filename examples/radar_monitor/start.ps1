param(
    [string]$Port = 'COM13',
    [int]$HttpPort = 18888,
    [string]$Python = 'F:\Espressif\python_env\idf5.4_py3.11_env\Scripts\python.exe'
)
$ErrorActionPreference = 'Stop'
$radarWorkspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$radarScript = Join-Path $PSScriptRoot 'monitor.py'
$radarMetadata = Join-Path $radarWorkspace 'build\radar-monitor-service.json'
if (Test-Path -LiteralPath $radarMetadata) {
    $radarExisting = Get-Content -LiteralPath $radarMetadata -Raw | ConvertFrom-Json
    $radarProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $($radarExisting.pid)"
    if ($radarProcess -and $radarProcess.Name -match '^python(w)?\.exe$' -and
        $radarProcess.CommandLine -match 'radar_monitor[\\/]monitor\.py') {
        Write-Output "采集已运行：$($radarExisting.url)"
        Write-Output "日志目录：$($radarExisting.output)"
        return
    }
}
$radarOutput = Join-Path $radarWorkspace ('build\radar-monitor-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $radarOutput -Force | Out-Null
if (-not (Test-Path -LiteralPath $Python)) { throw "Python未找到：$Python" }
# Quote paths containing spaces for Windows process argument parsing.
$radarQuotedScript = '"' + $radarScript + '"'
$radarQuotedOutput = '"' + $radarOutput + '"'
$radarArgs = @($radarQuotedScript, '--port', $Port,
               '--http-port', $HttpPort, '--output', $radarQuotedOutput)
$radarLaunched = Start-Process -FilePath $Python -ArgumentList $radarArgs `
    -WorkingDirectory $radarWorkspace -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $radarOutput 'service.stdout.log') `
    -RedirectStandardError (Join-Path $radarOutput 'service.stderr.log') -PassThru
$radarRecord = @{pid=$radarLaunched.Id; output=$radarOutput; script=$radarScript;
    url="http://127.0.0.1:$HttpPort"; started_at=(Get-Date -Format o)}
$radarRecord | ConvertTo-Json | Set-Content -LiteralPath $radarMetadata
Write-Output "采集已启动：$($radarRecord.url)"
Write-Output "日志目录：$radarOutput"
Write-Output '若页面未打开，查看该目录的service.stderr.log。'
