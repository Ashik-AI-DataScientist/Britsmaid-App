# Run from the repository root. Does not deploy, build, sign or expose a server.
param([Parameter(Mandatory=$true)][string]$BackendUrl)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Set-Location $root
$url=[Uri]$BackendUrl
if (-not $url.IsAbsoluteUri) { throw 'Use a complete backend URL' }
$env:EXPO_PUBLIC_BACKEND_URL=$BackendUrl.TrimEnd('/')
$env:BRITSMAID_PREVIEW_LAN=if ($url.Scheme -eq 'http') {'1'} else {'0'}
$commit=(& git rev-parse HEAD).Trim()
$dirty=((& git status --porcelain --untracked-files=normal) -join "`n")
if ($dirty) { throw 'Commit the reviewed source before preparing the build.' }
$source=@{commit=$commit;branch=(& git branch --show-current).Trim();preparedAt=[DateTime]::UtcNow.ToString('o')}
$source | ConvertTo-Json | Set-Content -Encoding utf8 frontend/preview-source.json
Push-Location frontend
try {
  & pnpm exec expo config --type public
  if ($LASTEXITCODE -ne 0) { throw 'Invalid build configuration' }
  Write-Host 'Source recorded. EAS login and project linking must be completed in this terminal.'
  Write-Host 'Run: pnpm dlx eas-cli login'
  Write-Host 'Run: pnpm dlx eas-cli init (use your existing project if available)'
  Write-Host 'Then: pnpm dlx eas-cli build --platform android --profile preview-lan (HTTP LAN) or --profile preview (HTTPS)'
} finally { Pop-Location }
