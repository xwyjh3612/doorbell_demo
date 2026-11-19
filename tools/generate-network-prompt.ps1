param(
    [string]$Ffmpeg = 'F:/ffmpeg/bin/ffmpeg.exe',
    [string]$Voice = 'Microsoft Huihui Desktop'
)
$ErrorActionPreference = 'Stop'
$promptRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$promptDir = Join-Path $promptRoot 'build/call-tones'
New-Item -ItemType Directory -Path $promptDir -Force | Out-Null
$promptWav = Join-Path $promptDir 'network-success.wav'
$promptAac = Join-Path $promptRoot 'main/join.aac'
Add-Type -AssemblyName System.Speech
$promptSpeaker = [System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
    $promptSpeaker.SelectVoice($Voice)
    $promptSpeaker.Rate = -1
    $promptSpeaker.Volume = 100
    $promptFormat = [System.Speech.AudioFormat.SpeechAudioFormatInfo]::new(
        16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
        [System.Speech.AudioFormat.AudioChannel]::Mono)
    $promptSpeaker.SetOutputToWaveFile($promptWav, $promptFormat)
    $promptSpeaker.Speak('联网成功')
} finally { $promptSpeaker.Dispose() }
& $Ffmpeg -hide_banner -loglevel error -y -i $promptWav -map_metadata -1 -af volume=5dB `
    -c:a aac -profile:a aac_low -ar 16000 -ac 1 -b:a 32k -f adts $promptAac
if ($LASTEXITCODE -ne 0) { throw '联网提示音编码失败。' }
$promptRecord = @{text='联网成功'; file='join.aac'; voice=$Voice; gain_db=5;
    sample_rate=16000; channels=1; size=(Get-Item -LiteralPath $promptAac).Length;
    sha256=(Get-FileHash -LiteralPath $promptAac -Algorithm SHA256).Hash.ToLower()}
$promptRecord | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $promptRoot 'main/network-prompt.json') -Encoding utf8
Write-Output "已生成联网成功提示音，试听文件：$promptWav"
