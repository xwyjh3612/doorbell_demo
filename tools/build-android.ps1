param(
    [string]$JavaHome = $env:JAVA_HOME,
    [string]$SdkHome = $env:ANDROID_HOME,
    [string]$GradleHome
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path $PSScriptRoot -Parent
if (-not $JavaHome -or -not (Test-Path -LiteralPath (Join-Path $JavaHome 'bin/java.exe'))) {
    throw '请通过 -JavaHome 指定 JDK 17 或以上的目录。'
}
if (-not $SdkHome -or -not (Test-Path -LiteralPath (Join-Path $SdkHome 'platforms/android-35/android.jar'))) {
    throw '请通过 -SdkHome 指定已安装 Android SDK 35 的目录。'
}
$env:JAVA_HOME = $JavaHome
$env:PATH = "$(Join-Path $JavaHome 'bin');$env:PATH"
$sdkValue = $SdkHome.Replace('\', '/')
Set-Content -LiteralPath (Join-Path $taskRoot 'android/local.properties') -Value "sdk.dir=$sdkValue" -Encoding utf8
if ($GradleHome) { $gradle = Join-Path $GradleHome 'bin/gradle.bat' }
else { $gradle = Join-Path $taskRoot 'android/gradlew.bat' }
& $gradle -p (Join-Path $taskRoot 'android') assembleDebug testDebugUnitTest lintDebug --console=plain
if ($LASTEXITCODE -ne 0) { throw 'Android 构建或检查失败。' }
$destination = Join-Path $taskRoot 'outputs/android'
New-Item -ItemType Directory -Path $destination -Force | Out-Null
$apk = Join-Path $destination 'voice-intercom-demo.apk'
Copy-Item -LiteralPath (Join-Path $taskRoot 'android/app/build/outputs/apk/debug/app-debug.apk') -Destination $apk -Force
Get-FileHash -LiteralPath $apk -Algorithm SHA256
Write-Host "演示 APK：$apk"
