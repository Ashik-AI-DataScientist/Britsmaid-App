param([string]$LanAddress='192.168.29.55', [int]$Port=8766)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Set-Location $root
$python=Join-Path $root '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Install the documented Python preview dependencies in .venv first.' }
if (!(Test-Path -LiteralPath (Join-Path $root '.local-preview\web\index.html'))) { throw 'Build the web preview first; see docs/ANDROID_PREVIEW.md.' }
$env:BRITSMAID_PREVIEW_PRIVATE='1'
Write-Host 'Synthetic test backend only. Keep this PC awake; phone must use the same private Wi-Fi.'
Write-Host 'Never upload real guest IDs. Do not forward this port through the router.'
Write-Host "Phone/backend address: http://${LanAddress}:$Port"
Write-Host 'Random test passwords are generated on each restart in .local-preview\private-test-accounts.txt.'
Write-Host 'The current APK expects 192.168.29.55:8766. A different address needs a newly configured APK.'
& $python scripts/local_preview.py --lan-ip $LanAddress --port $Port
if ($LASTEXITCODE -ne 0) { throw "Preview stopped with code $LASTEXITCODE. A previous preview may still own the port." }
