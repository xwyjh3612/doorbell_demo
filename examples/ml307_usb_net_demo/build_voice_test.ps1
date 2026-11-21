param([ValidateSet('rndis','ecm')][string]$Transport='rndis')
$ErrorActionPreference='Stop'
$voiceUsbRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
if(-not $env:IDF_PATH){throw '先启用ESP-IDF5.4.3；本脚本仅编译隔离实验，不刷机。'}
Push-Location -LiteralPath $voiceUsbRoot
try{
 & python (Join-Path $PSScriptRoot 'prepare_voice_test.py')
 if($LASTEXITCODE -ne 0){throw '隔离语音实验准备失败'}
 $voiceUsbCopy=Join-Path $voiceUsbRoot 'build\voice-usb-evaluation-recovery'
 $voiceUsbManaged=Join-Path $voiceUsbCopy 'managed_components'
 if(-not (Test-Path -LiteralPath $voiceUsbManaged)){
  Copy-Item -LiteralPath (Join-Path $voiceUsbRoot 'managed_components') -Destination $voiceUsbManaged -Recurse
  Copy-Item -LiteralPath (Join-Path $voiceUsbRoot 'dependencies.lock') -Destination (Join-Path $voiceUsbCopy 'dependencies.lock')
 }
 $voiceUsbOutput=Join-Path $voiceUsbCopy ('build-'+$Transport)
 New-Item -ItemType Directory -Path $voiceUsbOutput -Force|Out-Null
 $voiceUsbConfig=Join-Path $voiceUsbOutput 'sdkconfig'
 $voiceUsbLines=@(Get-Content -LiteralPath (Join-Path $voiceUsbCopy 'usb-rndis-defaults') -Encoding UTF8|Where-Object {$_ -notmatch '^(CONFIG_VOICE_TEST_ECM=|# CONFIG_VOICE_TEST_ECM is not set)'})
 $voiceUsbLines+=if($Transport -eq 'ecm'){'CONFIG_VOICE_TEST_ECM=y'}else{'# CONFIG_VOICE_TEST_ECM is not set'}
 [IO.File]::WriteAllLines($voiceUsbConfig,$voiceUsbLines,[Text.UTF8Encoding]::new($false))
 & python (Join-Path $env:IDF_PATH 'tools\idf.py') -C $voiceUsbCopy -B $voiceUsbOutput -D "SDKCONFIG=$voiceUsbConfig" build
 if($LASTEXITCODE -ne 0){throw '隔离USB语音固件编译失败'}
 $voiceUsbImage=Join-Path $voiceUsbOutput 'doorbell_demo.bin'
 $voiceUsbBaseline=Get-Content -LiteralPath (Join-Path $voiceUsbCopy 'baseline.json') -Raw | ConvertFrom-Json
 @{transport=$Transport;image_size=(Get-Item -LiteralPath $voiceUsbImage).Length;
   sha256=(Get-FileHash -LiteralPath $voiceUsbImage -Algorithm SHA256).Hash.ToLower();built_at=(Get-Date -Format o);
   baseline_commit=$voiceUsbBaseline.baseline_commit;flashed=$false;call_tested=$false;
   mqtt_lifetime_recovery_fix_included=$true;
   official_protocol_changed=$false;at_mqtt_retained=$true;latest_packet_mailbox_retained=$true;
   note='Experimental app image only. AT MQTT lifetime and deferred-callback fixes included; USB recovery and calls unverified. Preserve partition/OTA/NVS before flashing.'}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $voiceUsbOutput 'test-manifest.json') -Encoding UTF8
 Write-Output "编译通过，未刷机/未验收：$voiceUsbImage"
}finally{Pop-Location}
