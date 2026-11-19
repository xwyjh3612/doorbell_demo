param(
    [switch]$Rebuild
)

$ErrorActionPreference = 'Stop'
$jarPath = Join-Path $PSScriptRoot 'target\demo-0.0.1-SNAPSHOT.jar'

Push-Location -LiteralPath $PSScriptRoot
try {
    if ($Rebuild -or -not (Test-Path -LiteralPath $jarPath)) {
        $mavenCommand = Get-Command mvn -ErrorAction Stop
        & $mavenCommand.Source '-DskipTests' 'package'
        if ($LASTEXITCODE -ne 0) {
            throw 'Maven build failed; the test server was not started.'
        }
    }

    $javaCommand = Get-Command java -ErrorAction Stop
    Write-Host 'Test page: http://localhost:8080/index2.html'
    Write-Host 'WebSocket: ws://localhost:8080/signaling'
    Write-Host 'Keep this terminal open. Press Ctrl+C to stop the server.'
    & $javaCommand.Source '-jar' $jarPath
    if ($LASTEXITCODE -ne 0) {
        throw 'The test server exited with an error. Check the startup log above.'
    }
}
finally {
    Pop-Location
}
