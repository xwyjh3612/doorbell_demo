# Capture ML307 internal logs using the vendor's verified DiagRecord CLI.
# This tool does not flash firmware or issue modem reset commands.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$CatStudioDirectory,
    [ValidateRange(5, 3600)]
    [int]$Seconds = 120,
    [ValidateRange(1, 1024)]
    [int]$MaxFileMb = 16,
    [ValidateRange(0, 31)]
    [int]$DeviceIndex = 0
)

$ErrorActionPreference = 'Stop'
$voiceProject = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$vendorRoot = (Resolve-Path -LiteralPath $CatStudioDirectory).Path
$vendorExec = Join-Path $vendorRoot 'Exec'
$recorder = Join-Path $vendorExec 'DiagRecord.exe'
if (-not (Test-Path -LiteralPath $recorder -PathType Leaf)) {
    throw 'Select the CATStudio root directory containing Exec/DiagRecord.exe.'
}
if (Get-Process -Name DiagRecord -ErrorAction SilentlyContinue) {
    throw 'DiagRecord is already running; finish that recording before starting another.'
}

$captureRoot = Join-Path $voiceProject 'build'
if (-not (Test-Path -LiteralPath $captureRoot)) {
    New-Item -ItemType Directory -Path $captureRoot | Out-Null
}
$captureDirectory = Join-Path $captureRoot ('ml307-diag-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
New-Item -ItemType Directory -Path $captureDirectory -ErrorAction Stop | Out-Null
$runnerLog = Join-Path $captureDirectory 'recorder.log'
$arguments = @("-dev$DeviceIndex", 'record', [string]$MaxFileMb, [string]($Seconds * 1000))
$started = Get-Date
$manifest = [ordered]@{
    product = 'voice-intercom'
    startedAt = $started.ToString('o')
    tool = $recorder
    arguments = $arguments
    decoding = 'raw capture; matching AP/CP database required'
    deviceVersionResponseObserved = $false
    files = @()
    success = $false
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $captureDirectory 'request.json') -Encoding UTF8
$captureError = $null

try {
    Push-Location -LiteralPath $captureDirectory
    try {
        # Keep direct invocation: a previous detached launch did not yield a
        # verifiable recording. A fresh working directory keeps generated XML
        # and launcher logs in the project build directory.
        & $recorder @arguments *> $runnerLog
        $manifest['exitCode'] = $LASTEXITCODE
    } finally {
        Pop-Location
    }

    $vendorPrefix = $vendorRoot.TrimEnd([char[]]'\/') + [IO.Path]::DirectorySeparatorChar
    $recordedPaths = @(Select-String -LiteralPath $runnerLog -Pattern '^Recording\s+\d+\.\s+(.+\.icl)\s*$' |
        ForEach-Object { $_.Matches[0].Groups[1].Value.Trim() } | Select-Object -Unique)
    # A nonempty ICL can contain only the PC's outgoing requests. File saving
    # alone does not establish that the module returned internal logs.
    $manifest.deviceVersionResponseObserved = [bool](Select-String -LiteralPath $runnerLog -Pattern 'Got CP version:')
    if ($recordedPaths.Count -eq 0) { throw 'Recorder did not report an ICL file. See recorder.log.' }

    foreach ($reportedPath in $recordedPaths) {
        $sourceIcl = [IO.Path]::GetFullPath($reportedPath)
        if (-not $sourceIcl.StartsWith($vendorPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Recorder reported a file outside the CATStudio directory; copy it manually after inspection.'
        }
        foreach ($sourceFile in @($sourceIcl, [IO.Path]::ChangeExtension($sourceIcl, '.ild'))) {
            if (-not (Test-Path -LiteralPath $sourceFile -PathType Leaf)) {
                if ([IO.Path]::GetExtension($sourceFile) -eq '.icl') { throw 'Reported ICL file is missing.' }
                continue
            }
            $destinationFile = Join-Path $captureDirectory ([IO.Path]::GetFileName($sourceFile))
            Copy-Item -LiteralPath $sourceFile -Destination $destinationFile
            $copiedFile = Get-Item -LiteralPath $destinationFile
            $manifest.files += [ordered]@{
                file = $copiedFile.Name
                source = $sourceFile
                bytes = $copiedFile.Length
                sha256 = (Get-FileHash -LiteralPath $destinationFile -Algorithm SHA256).Hash.ToLowerInvariant()
            }
        }
    }
    $iclFiles = @($manifest.files | Where-Object { $_.file -like '*.icl' })
    if ($manifest.exitCode -ne 0 -or $iclFiles.Count -eq 0 -or
        @($iclFiles | Where-Object { $_.bytes -eq 0 }).Count -gt 0) {
        throw 'Recording did not finish successfully with nonempty ICL files. See recorder.log.'
    }
    $manifest.success = $true
} catch {
    $captureError = $_
    $manifest['error'] = $_.Exception.Message
} finally {
    $completed = Get-Date
    $manifest['completedAt'] = $completed.ToString('o')
    $manifest['elapsedSeconds'] = ($completed - $started).TotalSeconds
    $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $captureDirectory 'manifest.json') -Encoding UTF8
    Write-Output ('Capture directory: ' + $captureDirectory)
    Write-Output ('Raw capture saved: ' + $manifest.success)
    Write-Output ('Module version response observed: ' + $manifest.deviceVersionResponseObserved)
}
if ($null -ne $captureError) { throw $captureError }
