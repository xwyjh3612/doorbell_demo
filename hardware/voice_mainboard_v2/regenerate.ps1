$ErrorActionPreference='Stop'
$pcbWorkspace=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$pcbPython=Join-Path $pcbWorkspace 'build\cad-tools\kicad\bin\python.exe'
$pcbCli=Join-Path $pcbWorkspace 'build\cad-tools\kicad\bin\kicad-cli.exe'
Push-Location -LiteralPath $pcbWorkspace
try {
 & $pcbPython (Join-Path $PSScriptRoot 'generate_design.py')
 if($LASTEXITCODE -ne 0){throw 'PCB generation failed'}
 & $pcbPython (Join-Path $PSScriptRoot 'generate_schematic.py')
 if($LASTEXITCODE -ne 0){throw 'Schematic generation failed'}
 if(-not(Test-Path -LiteralPath (Join-Path $PSScriptRoot 'routing\review-copper.json'))){
  & $pcbPython (Join-Path $PSScriptRoot 'route_review.py')
  if($LASTEXITCODE -ne 0){throw 'Partial signal routing failed'}
 }
 & $pcbPython (Join-Path $PSScriptRoot 'restore_review_routes.py')
 if($LASTEXITCODE -ne 0){throw 'Saved review routing restoration failed'}
 & $pcbPython (Join-Path $PSScriptRoot 'apply_stackup.py')
 if($LASTEXITCODE -ne 0){throw 'Stackup recording failed'}
 $sch=Join-Path $PSScriptRoot 'voice_mainboard_v2.kicad_sch'
 $brd=Join-Path $PSScriptRoot 'voice_mainboard_v2.kicad_pcb'
 & $pcbCli sch export netlist --format kicadxml -o (Join-Path $PSScriptRoot 'exports\voice_mainboard_v2.net.xml') $sch
 if($LASTEXITCODE -ne 0){throw 'Netlist export failed'}
 & $pcbCli sch erc --format json -o (Join-Path $PSScriptRoot 'exports\erc.json') $sch
 if($LASTEXITCODE -ne 0){throw 'ERC execution failed'}
 & $pcbCli pcb drc --format json -o (Join-Path $PSScriptRoot 'exports\placement-drc.json') $brd
 if($LASTEXITCODE -ne 0){throw 'DRC execution failed'}
 & $pcbPython (Join-Path $PSScriptRoot 'verify_design.py')
 if($LASTEXITCODE -ne 0){throw 'Draft verification failed'}
 & 'F:\Espressif\python_env\idf5.4_py3.11_env\Scripts\python.exe' (Join-Path $PSScriptRoot 'simulate_power.py')
 if($LASTEXITCODE -ne 0){throw 'RC simulation failed'}
 & 'F:\Espressif\python_env\idf5.4_py3.11_env\Scripts\python.exe' (Join-Path $PSScriptRoot 'simulate_functions.py')
 if($LASTEXITCODE -ne 0){throw 'Functional simulation report generation failed'}
 & 'F:\Espressif\python_env\idf5.4_py3.11_env\Scripts\python.exe' (Join-Path $PSScriptRoot 'check_power_contract.py')
 if($LASTEXITCODE -ne 0){throw 'Power contract verification failed'}
 & $pcbPython (Join-Path $PSScriptRoot 'generate_review_assets.py')
 if($LASTEXITCODE -ne 0){throw 'Review generation failed'}
 & $pcbCli sch export svg -o (Join-Path $PSScriptRoot 'exports\schematic') $sch
 if($LASTEXITCODE -ne 0){throw 'Schematic SVG export failed'}
 $exportedSvg=Join-Path $PSScriptRoot 'exports\schematic\voice_mainboard_v2.svg'
 $svgLines=[IO.File]::ReadAllLines($exportedSvg,[Text.Encoding]::UTF8)|ForEach-Object {$_.TrimEnd()}
 [IO.File]::WriteAllText($exportedSvg,($svgLines -join "`n")+"`n",[Text.UTF8Encoding]::new($false))
 & 'F:\nodejs\nvm\v22.16.0\node.exe' (Join-Path $PSScriptRoot 'render_exports.mjs')
 if($LASTEXITCODE -ne 0){throw 'PNG preview rendering failed'}
} finally {Pop-Location}
