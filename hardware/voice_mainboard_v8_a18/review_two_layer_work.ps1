param([switch]$Export3D, [string]$Board)
$ErrorActionPreference = 'Stop'
$cadRoot = Split-Path -Parent $PSCommandPath
$repoRoot = (Resolve-Path (Join-Path $cadRoot '..\..')).Path
if ($Board) {
    $board = (Resolve-Path -LiteralPath $Board).Path
} else {
    $board = Join-Path $cadRoot 'two_layer_work\voice_mainboard_a18_2layer.kicad_pcb'
}
$schematic = [System.IO.Path]::ChangeExtension($board, '.kicad_sch')
$exports = Join-Path (Split-Path -Parent $board) 'exports'
$cli = Join-Path $repoRoot 'build\cad-tools\kicad\bin\kicad-cli.exe'
$python = Join-Path $repoRoot 'build\cad-tools\kicad\bin\python.exe'
$env:A18_AUDIT_BOARD = $board
$env:A18_REPAIR_BOARD = $board
$env:A18_AUDIT_READ_ONLY = '1'
$env:KICAD9_3DMODEL_DIR = Join-Path $repoRoot 'build\cad-tools\kicad\share\kicad\3dmodels'
& $cli sch export netlist --format kicadxml --output (Join-Path $exports 'netlist.xml') $schematic
if ($LASTEXITCODE -ne 0) { throw 'Netlist export failed' }
& $cli sch erc --format json --output (Join-Path $exports 'erc.json') $schematic
if ($LASTEXITCODE -ne 0) { throw 'ERC execution failed' }
& $cli pcb drc --format json --schematic-parity --output (Join-Path $exports 'review-drc.json') $board
if ($LASTEXITCODE -ne 0) { throw 'DRC execution failed' }
foreach ($script in @('audit_electrical.py','audit_controls.py','audit_copper_paths.py','audit_power_widths.py','inventory_two_layer_models.py')) {
    & $python (Join-Path $cadRoot $script)
    if ($LASTEXITCODE -ne 0) { throw "Review failed: $script" }
}
$design = Get-Content -LiteralPath (Join-Path (Split-Path -Parent $board) 'design.json') -Raw | ConvertFrom-Json
if ('C75' -in $design.parts.ref -and 'C76' -in $design.parts.ref) {
    & $python (Join-Path $cadRoot 'audit_vbat_storage.py')
    if ($LASTEXITCODE -ne 0) { throw 'VBAT storage review failed' }
}
if ($Export3D) {
    & $cli pcb export step --force --board-only --cut-vias-in-body --output (Join-Path $exports 'voice-mainboard-board-only.step') $board *> (Join-Path $exports 'step-board-export.log')
    if ($LASTEXITCODE -ne 0) { throw 'Board STEP export failed' }
    & $cli pcb export step --force --subst-models --no-dnp --output (Join-Path $exports 'voice-mainboard-models.step') $board *> (Join-Path $exports 'step-models-export.log')
    if ($LASTEXITCODE -ne 0) { throw 'Component STEP export failed' }
}
& 'F:\Espressif\python_env\idf5.4_py3.11_env\Scripts\python.exe' (Join-Path $cadRoot 'render_review.py')
if ($LASTEXITCODE -ne 0) { throw 'Render failed' }
& $python (Join-Path $cadRoot 'create_review.py')
if ($LASTEXITCODE -ne 0) { throw 'Review page generation failed' }
& $python (Join-Path $cadRoot 'write_two_layer_review_notes.py')
if ($LASTEXITCODE -ne 0) { throw 'Review notes generation failed' }
if ((Split-Path -Leaf (Split-Path -Parent $board)) -eq 'power_relayout_candidate') {
    & $python (Join-Path $cadRoot 'create_comparison_review.py')
    if ($LASTEXITCODE -ne 0) { throw 'Comparison entry generation failed' }
}
Write-Output 'Published the exact current two-layer review; manufacturing status remains unreleased.'
