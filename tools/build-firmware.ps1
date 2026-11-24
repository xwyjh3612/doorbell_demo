param(
    [ValidateSet('voice', 'voice-radar', 'voice-radar60', 'mainboard-v6', 'mainboard-v6-radar60')]
    [string]$Variant = 'voice'
)
$ErrorActionPreference = 'Stop'
$voiceWorkspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not $env:IDF_PATH) { throw '请先启用ESP-IDF环境（运行ESP-IDF的export.ps1）。' }
$voicePython = (Get-Command python -ErrorAction Stop).Source
$voiceIdf = Join-Path $env:IDF_PATH 'tools\idf.py'
$voiceConfigDir = Join-Path $voiceWorkspace 'build\firmware-profile'
$voiceConfig = Join-Path $voiceConfigDir 'sdkconfig'
$voiceOutput = Join-Path $voiceWorkspace 'outputs\firmware'
New-Item -ItemType Directory -Path $voiceConfigDir, $voiceOutput -Force | Out-Null
# Seed from the project's tested hardware configuration, without changing it.
# A single private build config allows incremental builds when switching variants.
if (-not (Test-Path -LiteralPath $voiceConfig)) {
    $voiceSeed = Join-Path $voiceWorkspace 'sdkconfig'
    if (-not (Test-Path -LiteralPath $voiceSeed)) {
        throw '请先按项目说明配置ESP32-S3硬件并生成根目录sdkconfig。'
    }
    Copy-Item -LiteralPath $voiceSeed -Destination $voiceConfig
}
$voiceLines = @(Get-Content -LiteralPath $voiceConfig -Encoding UTF8 |
    Where-Object { $_ -notmatch '^(CONFIG_VOICE_RADAR_(ENABLE|R60)=|# CONFIG_VOICE_RADAR_(ENABLE|R60) is not set|CONFIG_VOICE_POWER_MONITOR_ENABLE=|# CONFIG_VOICE_POWER_MONITOR_ENABLE is not set)' })
$voiceHasRadar = $Variant -in @('voice-radar','voice-radar60','mainboard-v6-radar60')
$voiceHasRadar60 = $Variant -in @('voice-radar60','mainboard-v6-radar60')
$voiceHasPower = $Variant -like 'mainboard-v6*'
$voiceLines += $(if ($voiceHasRadar) {
    'CONFIG_VOICE_RADAR_ENABLE=y'
} else { '# CONFIG_VOICE_RADAR_ENABLE is not set' })
$voiceLines += $(if ($voiceHasRadar60) { 'CONFIG_VOICE_RADAR_R60=y' }
    else { '# CONFIG_VOICE_RADAR_R60 is not set' })
$voiceLines += $(if ($voiceHasPower) { 'CONFIG_VOICE_POWER_MONITOR_ENABLE=y' }
    else { '# CONFIG_VOICE_POWER_MONITOR_ENABLE is not set' })
[IO.File]::WriteAllLines($voiceConfig, $voiceLines, [Text.UTF8Encoding]::new($false))
& $voicePython $voiceIdf -C $voiceWorkspace -B (Join-Path $voiceWorkspace 'build') `
    -D "SDKCONFIG=$($voiceConfig.Replace('\','/'))" build
if ($LASTEXITCODE -ne 0) { throw "固件编译失败：$Variant" }
# Verify compile exclusion and linked symbols, rather than trusting the flag alone.
& $voicePython (Join-Path $PSScriptRoot 'verify-firmware-variant.py') `
    --root $voiceWorkspace --variant $Variant
if ($LASTEXITCODE -ne 0) { throw "固件变体验证失败：$Variant" }
$voiceImage = Join-Path $voiceOutput ($Variant + '.bin')
Copy-Item -LiteralPath (Join-Path $voiceWorkspace 'build\doorbell_demo.bin') -Destination $voiceImage -Force
$voiceRecord = @{variant=$Variant; radar=$voiceHasRadar; radar60=$voiceHasRadar60; power_monitor=$voiceHasPower;
    size=(Get-Item -LiteralPath $voiceImage).Length;
    sha256=(Get-FileHash -LiteralPath $voiceImage -Algorithm SHA256).Hash.ToLower();
    built_at=(Get-Date -Format o); app_offset='0x10000';
    note='App image only. Verify device partitions and preserve NVS/OTA selection before flashing.'}
$voiceRecord | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $voiceOutput ($Variant + '.json')) -Encoding UTF8
Write-Output "已生成：$voiceImage"
