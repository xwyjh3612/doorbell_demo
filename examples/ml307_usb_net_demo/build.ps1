param(
 [ValidateSet('rndis','ecm')][string]$Transport='rndis',
 [switch]$AllowModeChange
)
$ErrorActionPreference='Stop'
$usbTestRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
if(-not $env:IDF_PATH){throw '先启用ESP-IDF 5.4.3环境；此脚本只构建，不刷机。'}
$usbSource=Join-Path $usbTestRoot 'build\esp-iot-solution-cellular'
$usbCommit='f721a40c032f6168844fe3bd321bc182e2593348'
if(-not (Test-Path -LiteralPath (Join-Path $usbSource '.git'))){
 & git clone --filter=blob:none --no-checkout https://github.com/espressif/esp-iot-solution.git $usbSource
 if($LASTEXITCODE -ne 0){throw '官方驱动克隆失败'}
 & git -C $usbSource sparse-checkout set components/usb/iot_usbh_rndis components/usb/iot_usbh_ecm components/usb/iot_usbh_cdc components/iot_eth
 if($LASTEXITCODE -ne 0){throw '稀疏检出失败'}
 & git -C $usbSource checkout --detach $usbCommit
 if($LASTEXITCODE -ne 0){throw '官方驱动固定版本检出失败'}
}
$actualCommit=(& git -C $usbSource rev-parse HEAD).Trim()
if($actualCommit -ne $usbCommit){throw "驱动版本不匹配：$actualCommit"}
$usbSuffix=if($AllowModeChange){'-configure'}else{''}
$usbBuild=Join-Path $usbTestRoot ('build\ml307-usb-net-'+$Transport+$usbSuffix)
New-Item -ItemType Directory -Path $usbBuild -Force|Out-Null
$usbConfig=Join-Path $usbBuild 'sdkconfig'
if(Test-Path -LiteralPath $usbConfig){$usbLines=@(Get-Content -LiteralPath $usbConfig -Encoding UTF8)}
else{$usbLines=@(Get-Content -LiteralPath (Join-Path $PSScriptRoot 'sdkconfig.defaults') -Encoding UTF8)}
$usbLines=@($usbLines|Where-Object {$_ -notmatch '^(CONFIG_VOICE_TEST_(ECM|AUTO_MODE_CHANGE)=|# CONFIG_VOICE_TEST_(ECM|AUTO_MODE_CHANGE) is not set)'})
$usbLines+=if($Transport -eq 'ecm'){'CONFIG_VOICE_TEST_ECM=y'}else{'# CONFIG_VOICE_TEST_ECM is not set'}
$usbLines+=if($AllowModeChange){'CONFIG_VOICE_TEST_AUTO_MODE_CHANGE=y'}else{'# CONFIG_VOICE_TEST_AUTO_MODE_CHANGE is not set'}
[IO.File]::WriteAllLines($usbConfig,$usbLines,[Text.UTF8Encoding]::new($false))
& python (Join-Path $env:IDF_PATH 'tools\idf.py') -C $PSScriptRoot -B $usbBuild -D "SDKCONFIG=$usbConfig" -D 'IDF_TARGET=esp32s3' build
if($LASTEXITCODE -ne 0){throw 'USB网络探针编译失败'}
$usbImage=Join-Path $usbBuild 'voice_ml307_usb_net_demo.bin'
@{transport=$Transport;allow_persistent_mode_change=[bool]$AllowModeChange;built_at=(Get-Date -Format o);driver_commit=$usbCommit;
 image_sha256=(Get-FileHash -LiteralPath $usbImage -Algorithm SHA256).Hash.ToLower();image_size=(Get-Item -LiteralPath $usbImage).Length;
 flashed=$false;network_tested=$false;voice_call_tested=$false;note='Independent app image only. Preserve existing partition/NVS/OTA before any test flashing.'}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $usbBuild 'test-manifest.json') -Encoding UTF8
Write-Output "已构建，未刷机：$usbImage"
