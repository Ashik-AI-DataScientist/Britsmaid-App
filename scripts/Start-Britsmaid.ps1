param([switch]$CheckOnly, [switch]$SelfTest)
$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectPath '.venv\Scripts\python.exe'
$serverPath = Join-Path $PSScriptRoot 'local_preview.py'
$previewDirectory = Join-Path $projectPath '.local-preview'

function Get-PhoneAddress {
    $candidates = @(Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } | Sort-Object @{Expression={ if ($_.InterfaceAlias -match 'Wi-Fi|Wireless|WLAN' -or $_.InterfaceDescription -match 'Wireless|Wi-Fi|802.11') {0} else {1} }}, @{Expression={$_.NetIPv4Interface.InterfaceMetric}})
    foreach ($network in $candidates) {
        foreach ($item in $network.IPv4Address) {
            $ip = [Net.IPAddress]::Parse($item.IPAddress).GetAddressBytes()
            if ($ip[0] -eq 10 -or ($ip[0] -eq 192 -and $ip[1] -eq 168) -or ($ip[0] -eq 172 -and $ip[1] -ge 16 -and $ip[1] -le 31)) { return $item.IPAddress }
        }
    }
    return ''
}

function Stop-Preview {
    $listeners = @(Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue)
    foreach ($serverId in @($listeners.OwningProcess | Select-Object -Unique)) {
        if (!$serverId) { continue }
        $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$serverId"
        # Stop only this workspace's Python demo, never an unrelated service.
        if ($processInfo.CommandLine -notlike '*scripts/local_preview.py*' -and $processInfo.CommandLine -notlike "*$serverPath*") { throw 'Port 8765 is being used by another app. Close that app and try again.' }
        $owned = $processInfo.CommandLine -like "*$projectPath*"
        $ancestor = $processInfo
        for ($level = 0; !$owned -and $level -lt 3 -and $ancestor.ParentProcessId; $level++) {
            $ancestor = Get-CimInstance Win32_Process -Filter "ProcessId=$($ancestor.ParentProcessId)"
            if (!$ancestor) { break }
            $owned = $ancestor.CommandLine -like "*$pythonPath*" -or $ancestor.CommandLine -like "*$serverPath*"
        }
        if (!$owned) { throw 'Another preview is using port 8765. Close its window, then open Start Britsmaid again.' }
        Stop-Process -Id $serverId -ErrorAction SilentlyContinue
    }
}

if (!(Test-Path -LiteralPath $pythonPath) -or !(Test-Path -LiteralPath (Join-Path $previewDirectory 'web\index.html'))) { throw 'The preview files are missing. Ask to rebuild the Britsmaid preview.' }
if ($CheckOnly) {
    $currentAddress = Get-PhoneAddress
    Write-Output "PC: http://127.0.0.1:8765/"
    Write-Output "Phone: $(if ($currentAddress) { 'http://' + $currentAddress + ':8765/' } else { 'Connect to Wi-Fi first' })"
    exit 0
}

try { $Host.UI.RawUI.WindowTitle = 'Britsmaid - Local testing' } catch { }
$mutex = New-Object Threading.Mutex($false, 'Local\BritsmaidLocalPreviewLauncher')
if (!$mutex.WaitOne(0)) { Write-Host 'Britsmaid is already running. Use its open window for the phone link.'; Start-Sleep -Seconds 4; exit }
$lastAddress = $null
$openedBrowser = $false
$child = $null
try {
    while ($true) {
        $address = Get-PhoneAddress
        if ($null -eq $lastAddress -or $address -ne $lastAddress -or ($child -and $child.HasExited)) {
            Stop-Preview
            $serverArguments = @('"' + $serverPath + '"')
            if ($address) { $serverArguments += @('--lan-ip', $address) }
            $child = Start-Process -FilePath $pythonPath -ArgumentList $serverArguments -WorkingDirectory $projectPath -WindowStyle Hidden -RedirectStandardOutput (Join-Path $previewDirectory 'server.log') -RedirectStandardError (Join-Path $previewDirectory 'server-error.log') -PassThru
            $child.Id | Set-Content (Join-Path $previewDirectory 'server.pid')
            $lastAddress = $address
            try { Clear-Host } catch { }
            Write-Host 'BRITSMAID - LOCAL TESTING' -ForegroundColor Cyan
            Write-Host "`nOn this PC: http://127.0.0.1:8765/"
            if ($address) { Write-Host "`nENTER THIS ON YOUR PHONE: http://${address}:8765/" -ForegroundColor Green } else { Write-Host "`nConnect your PC to Wi-Fi to get a phone link." -ForegroundColor Yellow }
            Write-Host "`nPhone and PC must be on the same Wi-Fi. New devices can use the link above."
            Write-Host 'This window watches for network changes and updates the link automatically.'
            Write-Host 'Changing networks restarts the demo and resets sample data.'
            Write-Host "`nAdmin email: admin@example.com    Password: Preview@2026"
            Write-Host 'Use dummy IDs only. Some public/guest Wi-Fi networks block device connections.'
            Write-Host "`nKeep this window open. Press Ctrl+C to stop."
            if (!$openedBrowser) {
                $ready = $false
                for ($attempt = 0; $attempt -lt 20; $attempt++) {
                    try { $health = Invoke-RestMethod 'http://127.0.0.1:8765/preview-health' -TimeoutSec 2; if ($health.mode -eq 'local-demo') { $ready = $true; break } } catch { Start-Sleep -Milliseconds 500 }
                }
                if (!$ready) { throw 'The preview could not start. Details are in .local-preview/server-error.log.' }
                if ($SelfTest) { Write-Output 'PASS: launcher started the local demo successfully.'; break }
                Start-Process 'http://127.0.0.1:8765/'
                $openedBrowser = $true
            }
        }
        Start-Sleep -Seconds 5
    }
} catch { Write-Host "`nCould not start Britsmaid: $($_.Exception.Message)" -ForegroundColor Red; if ($SelfTest) { throw }; Read-Host 'Press Enter to close' }
finally {
    if ($child) { Stop-Preview }
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
