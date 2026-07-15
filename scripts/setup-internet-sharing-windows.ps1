# Edge Sensing Workshop — Windows ICS setup + check
#
# Sets up Internet Connection Sharing from your Wi-Fi to the Jetson's cable,
# then checks every layer between them and names whatever is broken.
#
# Unlike the macOS script (which is read-only, because macOS has no supported
# CLI for Internet Sharing), this one configures ICS for you. Windows exposes a
# documented COM API (HNetCfg.HNetShare), and the step it automates — picking
# the right adapter — is the one students get wrong. The ICS dropdown lists
# adapters by name ("Ethernet 3"), and that name is a per-laptop artifact: it
# depends on how many NICs that machine has ever enumerated. Telling 30 students
# to "choose Ethernet 3" would be wrong on most of their laptops.
#
# So we find the adapter by what it IS, not what it is called: the only wired
# (802.3) adapter with link. That is brand-agnostic and works whether the
# student uses a USB dongle or a built-in LAN port.
#
# Usage (must be an ADMIN PowerShell — ICS and firewall rules both require it):
#     powershell -ExecutionPolicy Bypass -File scripts\setup-internet-sharing-windows.ps1
#     ... -CheckOnly     # diagnose without changing anything

[CmdletBinding()]
param(
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'

$JETSON_USER  = 'jetson'
$JETSON_NAME  = 'jetson-2gnano.mshome.net'  # ICS auto-registers DHCP client names
$SHARED_GW    = '192.168.137.1'             # ICS always uses this. Not configurable.
$RELAY_PORT   = 8000
$RELAY_RULE   = 'Workshop Relay 8000'

# ICSSHARINGTYPE
$ICS_PUBLIC  = 0   # the connection being shared FROM (Wi-Fi)
$ICS_PRIVATE = 1   # the connection being shared TO (the Jetson's cable)

function Write-Ok   { param($m) Write-Host "  [OK] $m"   -ForegroundColor Green }
function Write-Bad  { param($m) Write-Host "  [!!] $m"   -ForegroundColor Red }
function Write-Warn { param($m) Write-Host "  [ ~] $m"   -ForegroundColor Yellow }
function Write-Step { param($m) Write-Host "`n$m"        -ForegroundColor White }

# Print a fix block and stop. Everything after the first failure would be noise
# — each check depends on the ones before it.
function Stop-WithFix {
    param([string]$Fix)
    Write-Host "`nHOW TO FIX" -ForegroundColor Red
    Write-Host $Fix
    Write-Host "`nThen run this script again."
    exit 1
}

Write-Host "=== Jetson Internet Sharing setup (Windows) ===" -ForegroundColor White

# ---------------------------------------------------------------------------
Write-Step '0. Administrator rights'
# ---------------------------------------------------------------------------
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin -and -not $CheckOnly) {
    Write-Bad 'Not running as Administrator'
    Stop-WithFix @"
ICS and firewall rules both need admin rights.

Close this window, then: Start > type "PowerShell" > right-click
"Windows PowerShell" > Run as administrator. Re-run the script there.

To diagnose without admin (no changes made), use:
    ... -File scripts\setup-internet-sharing-windows.ps1 -CheckOnly
"@
}
if ($isAdmin) { Write-Ok 'Running as Administrator' }
else          { Write-Warn 'Not admin — running read-only (-CheckOnly)' }

# ---------------------------------------------------------------------------
Write-Step "1. Your laptop's own internet (Wi-Fi)"
# ---------------------------------------------------------------------------
$wifi = Get-NetAdapter -Physical | Where-Object {
    $_.Status -eq 'Up' -and $_.PhysicalMediaType -match 'Native 802.11'
} | Select-Object -First 1

if (-not $wifi) {
    Write-Bad 'No connected Wi-Fi adapter found'
    Stop-WithFix 'Connect to the lab Wi-Fi first. You cannot share internet you do not have.'
}
$wifiIp = (Get-NetIPAddress -InterfaceIndex $wifi.ifIndex -AddressFamily IPv4 `
    -ErrorAction SilentlyContinue | Select-Object -First 1).IPAddress
Write-Ok "Wi-Fi ($($wifi.Name)) connected, IP $wifiIp"

if (Test-Connection -ComputerName 1.1.1.1 -Count 1 -Quiet -ErrorAction SilentlyContinue) {
    Write-Ok 'Laptop has working internet'
} else {
    Write-Bad 'Laptop cannot reach the internet'
    Stop-WithFix @"
Your laptop itself is offline, so there is nothing to share. Connect to the
lab Wi-Fi and confirm you can browse before running this again.
"@
}

# ---------------------------------------------------------------------------
Write-Step '2. The Jetson cable (dongle OR built-in LAN port)'
# ---------------------------------------------------------------------------
# The Jetson's adapter is whichever wired adapter has link. A cabled, powered
# Jetson is what makes it 'Up'. -Physical already excludes Hyper-V, WSL, VPN
# and Wi-Fi Direct virtual adapters; the media type check excludes Wi-Fi and
# Bluetooth. What is left is real ethernet, whatever brand it happens to be.
$wired = @(Get-NetAdapter -Physical | Where-Object {
    $_.Status -eq 'Up' -and $_.PhysicalMediaType -eq '802.3'
})

if ($wired.Count -eq 0) {
    Write-Bad 'No wired adapter with link'
    Stop-WithFix @"
Nothing is plugged in, or the cable/adapter is dead. Check that:
  - your USB-ethernet dongle is seated (or you are using the laptop's LAN port)
  - the LAN cable runs from it to the Jetson's ethernet port
  - the Jetson is powered on (its ethernet port LEDs should be lit)

Give the Jetson ~40 seconds after power-on, then retry.
"@
}

if ($wired.Count -gt 1) {
    # Refusing beats guessing: sharing to the wrong adapter is what this whole
    # script exists to prevent.
    Write-Bad "Found $($wired.Count) wired adapters with link — cannot tell which is the Jetson"
    $wired | ForEach-Object { Write-Host "      - $($_.Name)  [$($_.InterfaceDescription)]" }
    Stop-WithFix @"
More than one ethernet connection is live (e.g. you are in a dock, or also
plugged into the wall network). Unplug everything wired EXCEPT the Jetson
cable, then run this again.
"@
}

$lan = $wired[0]
Write-Ok "Jetson cable is on '$($lan.Name)'  [$($lan.InterfaceDescription)]"

# ---------------------------------------------------------------------------
Write-Step '3. Internet Connection Sharing'
# ---------------------------------------------------------------------------
$svc = Get-Service -Name SharedAccess -ErrorAction SilentlyContinue
if (-not $svc) {
    Write-Bad 'The Internet Connection Sharing service does not exist'
    Stop-WithFix @"
This Windows install has no ICS service. On university-managed laptops this is
sometimes removed or disabled by group policy — see your instructor, you may
need a loaner machine.
"@
}
if ($svc.Status -ne 'Running' -and -not $CheckOnly) {
    Set-Service -Name SharedAccess -StartupType Manual -ErrorAction SilentlyContinue
    Start-Service -Name SharedAccess -ErrorAction SilentlyContinue
}

try {
    $share = New-Object -ComObject HNetCfg.HNetShare
} catch {
    Write-Bad 'Cannot talk to the ICS COM API'
    Stop-WithFix "HNetCfg.HNetShare is unavailable: $($_.Exception.Message)"
}

# Map every connection once: the COM objects are what we must act on.
$conns = @()
foreach ($c in $share.EnumEveryConnection) {
    $p = $share.NetConnectionProps($c)
    $conns += [PSCustomObject]@{
        Name   = $p.Name
        Guid   = $p.Guid
        Config = $share.INetSharingConfigurationForINetConnection($c)
    }
}
if ($conns.Count -eq 0) {
    Write-Bad 'ICS returned no connections'
    Stop-WithFix @"
The ICS COM API listed nothing. This usually means the script is not elevated.
Re-run it from an Administrator PowerShell.
"@
}

$wifiConn = $conns | Where-Object { $_.Name -eq $wifi.Name } | Select-Object -First 1
$lanConn  = $conns | Where-Object { $_.Name -eq $lan.Name  } | Select-Object -First 1

if (-not $wifiConn -or -not $lanConn) {
    Write-Bad 'Could not match adapters to ICS connections'
    Stop-WithFix "Expected to find '$($wifi.Name)' and '$($lan.Name)' in the ICS list."
}

$sharedOk = $wifiConn.Config.SharingEnabled -and
            $wifiConn.Config.SharingConnectionType -eq $ICS_PUBLIC -and
            $lanConn.Config.SharingEnabled -and
            $lanConn.Config.SharingConnectionType -eq $ICS_PRIVATE

if ($sharedOk) {
    Write-Ok "Sharing is ON: $($wifi.Name) -> $($lan.Name)"
} elseif ($CheckOnly) {
    Write-Bad "Sharing is not configured as $($wifi.Name) -> $($lan.Name)"
    Stop-WithFix 'Re-run this script as Administrator (without -CheckOnly) to configure it.'
} else {
    # Clear any existing sharing first. ICS allows exactly one shared pair, and
    # a stale target (a dock adapter, an unplugged built-in port) silently wins.
    foreach ($c in $conns) {
        if ($c.Config.SharingEnabled) {
            Write-Warn "Clearing old sharing on '$($c.Name)'"
            try { $c.Config.DisableSharing() } catch {
                Write-Warn "  could not clear '$($c.Name)': $($_.Exception.Message)"
            }
        }
    }
    try {
        $wifiConn.Config.EnableSharing($ICS_PUBLIC)
        $lanConn.Config.EnableSharing($ICS_PRIVATE)
    } catch {
        Write-Bad 'Failed to enable ICS'
        Stop-WithFix @"
$($_.Exception.Message)

University-managed laptops sometimes block ICS by group policy. If this keeps
failing, tell your instructor — you may need a loaner machine.
"@
    }
    Write-Ok "Sharing enabled: $($wifi.Name) -> $($lan.Name)"
}

# ICS puts its address directly on the adapter (no bridge, unlike macOS), so
# this is also our proof that ICS really started rather than half-started.
$gwOk = $false
foreach ($i in 1..10) {
    $addrs = (Get-NetIPAddress -InterfaceIndex $lan.ifIndex -AddressFamily IPv4 `
        -ErrorAction SilentlyContinue).IPAddress
    if ($addrs -contains $SHARED_GW) { $gwOk = $true; break }
    Start-Sleep -Seconds 2
}
if ($gwOk) {
    Write-Ok "Laptop is $SHARED_GW on '$($lan.Name)'"
} else {
    Write-Bad "'$($lan.Name)' never got $SHARED_GW"
    Stop-WithFix @"
ICS says it is on but did not configure the adapter. Toggle it off and on:

  Win+R > ncpa.cpl > right-click '$($wifi.Name)' > Properties > Sharing tab
  Untick the box > OK > reopen > tick it > choose '$($lan.Name)' > OK
"@
}

# ---------------------------------------------------------------------------
Write-Step '4. Relay port (the Jetson must reach YOUR laptop)'
# ---------------------------------------------------------------------------
# Windows blocks inbound connections by default and the ICS adapter lands in
# the Public profile, so without this rule the Jetson's uploads are dropped
# with no error on either side. Verified on hardware: blocked before, open
# after. This has no macOS equivalent.
$rule = Get-NetFirewallRule -DisplayName $RELAY_RULE -ErrorAction SilentlyContinue
if ($rule) {
    Write-Ok "Firewall rule '$RELAY_RULE' exists"
} elseif ($CheckOnly) {
    Write-Warn "Firewall rule '$RELAY_RULE' missing — the Jetson's uploads will be dropped"
} else {
    New-NetFirewallRule -DisplayName $RELAY_RULE -Direction Inbound -Action Allow `
        -Protocol TCP -LocalPort $RELAY_PORT -Profile Any | Out-Null
    Write-Ok "Firewall rule '$RELAY_RULE' created (TCP $RELAY_PORT inbound)"
}

# ---------------------------------------------------------------------------
Write-Step '5. Jetson picked up an address'
# ---------------------------------------------------------------------------
# ICS runs a DHCP server and auto-registers each client's hostname under
# mshome.net, so the name tracks the lease. This matters: ICS hands out a
# DIFFERENT address on each renew, so no fixed IP can be printed in a handout.
$jip = $null
foreach ($i in 1..20) {
    $r = Resolve-DnsName -Name $JETSON_NAME -ErrorAction SilentlyContinue |
         Where-Object { $_.IPAddress } | Select-Object -First 1
    if ($r) { $jip = $r.IPAddress; break }
    Start-Sleep -Seconds 3
}

if (-not $jip) {
    Write-Bad "$JETSON_NAME did not resolve — no Jetson lease"
    Stop-WithFix @"
Your laptop is sharing, but the Jetson never asked for an address. Usually:
  - the Jetson is still booting (give it ~40s after power-on, then retry)
  - the Jetson is not powered on
  - the cable is loose at the Jetson end

If it stays broken, the Jetson's eth0 may not be on DHCP. That is a Jetson-side
fix — see docs/09-internet-sharing-setup.md > 'Jetson-side config'.
"@
}
Write-Ok "$JETSON_NAME resolves to $jip"

# ---------------------------------------------------------------------------
Write-Step '6. Reaching the Jetson'
# ---------------------------------------------------------------------------
if (Test-Connection -ComputerName $jip -Count 2 -Quiet -ErrorAction SilentlyContinue) {
    Write-Ok "Jetson answers at $jip"
} else {
    Write-Bad "Jetson has a lease but does not respond at $jip"
    Stop-WithFix @"
The lease may be stale (from a previous boot). Power-cycle the Jetson, wait
~40 seconds, and run this again.
"@
}

$ssh = Test-NetConnection -ComputerName $jip -Port 22 -WarningAction SilentlyContinue
if ($ssh.TcpTestSucceeded) {
    Write-Ok 'SSH port is open'
} else {
    Write-Bad 'SSH port 22 is closed on the Jetson'
    Stop-WithFix @"
The Jetson is reachable but not accepting SSH. Its sshd may not be running.
This needs a monitor or serial console on the Jetson itself.
"@
}

# ---------------------------------------------------------------------------
Write-Host "`n=== ALL CHECKS PASSED ===" -ForegroundColor Green
Write-Host "`nConnect to your Jetson with:`n"
Write-Host "    ssh $JETSON_USER@$JETSON_NAME" -ForegroundColor White
Write-Host "    (or: ssh $JETSON_USER@$jip)`n"
Write-Host "Verify the Jetson has internet, once you are logged in:`n"
Write-Host "    ping -c2 8.8.8.8      # routing"
Write-Host "    ping -c2 google.com   # DNS`n"
Write-Host "The Jetson finds this laptop automatically as its default gateway:"
Write-Host "    ip route | awk '/^default/{print `$3}'   ->  $SHARED_GW`n"
Write-Host "Note: ICS often turns itself off after sleep or reboot." -ForegroundColor Yellow
Write-Host "If the Jetson loses internet later, re-run this script first."
