#!/bin/bash
# Edge Sensing Workshop — macOS Internet Sharing check
#
# Checks every layer between your Mac's Wi-Fi and the Jetson, and tells you
# exactly which one is broken. It does NOT change your network settings.
#
# Enabling Internet Sharing itself is a GUI toggle: macOS has no supported CLI
# for it, and the unofficial route (writing com.apple.nat.plist + launchctl)
# breaks between releases. So this script guides you to the toggle, then proves
# the result actually works.
#
# Usage:  bash scripts/setup-internet-sharing-macos.sh

set -uo pipefail

JETSON_USER="jetson"
JETSON_MDNS="jetson-2gnano.local"
SHARED_GW="192.168.2.1"          # macOS Internet Sharing always uses this
LEASES="/var/db/dhcpd_leases"

if [ -t 1 ]; then
  R=$'\033[31m'; G=$'\033[32m'; Y=$'\033[33m'; B=$'\033[1m'; N=$'\033[0m'
else
  R=""; G=""; Y=""; B=""; N=""
fi

ok()   { printf "  %s✓%s %s\n" "$G" "$N" "$1"; }
bad()  { printf "  %s✗%s %s\n" "$R" "$N" "$1"; }
warn() { printf "  %s!%s %s\n" "$Y" "$N" "$1"; }
step() { printf "\n%s%s%s\n" "$B" "$1" "$N"; }

# Print a fix block and stop. Everything after the first failure would be
# noise — each check depends on the ones before it.
die() {
  printf "\n%s%sHOW TO FIX%s\n" "$B" "$R" "$N"
  printf "%s\n" "$1"
  printf "\nThen run this script again.\n"
  exit 1
}

printf "%s=== Jetson Internet Sharing check (macOS) ===%s\n" "$B" "$N"

# ---------------------------------------------------------------------------
step "1. Your Mac's own internet (Wi-Fi)"
# ---------------------------------------------------------------------------
WIFI_DEV=$(networksetup -listallhardwareports 2>/dev/null \
  | awk '/Hardware Port: Wi-Fi/{getline; print $2}')
[ -z "$WIFI_DEV" ] && WIFI_DEV="en0"

if ! ifconfig "$WIFI_DEV" 2>/dev/null | grep -q "status: active"; then
  bad "Wi-Fi ($WIFI_DEV) is not connected"
  die "Connect to the lab Wi-Fi first. You cannot share internet you don't have."
fi
WIFI_IP=$(ipconfig getifaddr "$WIFI_DEV" 2>/dev/null)
ok "Wi-Fi ($WIFI_DEV) connected, IP $WIFI_IP"

if ping -c1 -t3 1.1.1.1 >/dev/null 2>&1; then
  ok "Mac has working internet"
else
  bad "Mac cannot reach the internet"
  die "Your Mac itself is offline, so there is nothing to share.

If this started the moment you plugged in the Jetson cable, your ethernet
adapter has hijacked the default route. Check with:
    route -n get default | grep -E 'gateway|interface'
The interface should be your Wi-Fi ($WIFI_DEV). If it names your USB adapter,
see docs/09-internet-sharing-setup.md > 'Cable kills my Wi-Fi'."
fi

# ---------------------------------------------------------------------------
step "2. USB ethernet adapter + cable"
# ---------------------------------------------------------------------------
LAN_DEV=""
for i in $(ifconfig -l | tr ' ' '\n' | grep -E '^en[0-9]+$'); do
  [ "$i" = "$WIFI_DEV" ] && continue
  if ifconfig "$i" 2>/dev/null | grep -q "status: active"; then LAN_DEV="$i"; break; fi
done

if [ -z "$LAN_DEV" ]; then
  bad "No active ethernet adapter found"
  die "Nothing is plugged in, or the cable/adapter is dead. Check that:
  - the USB-ethernet adapter is seated in your Mac
  - the LAN cable runs from it to the Jetson's ethernet port
  - the Jetson is powered on (its ethernet port LEDs should be lit)

If the adapter is plugged in but not listed, it may need a driver. Check:
    networksetup -listallhardwareports"
fi
LAN_NAME=$(networksetup -listallhardwareports 2>/dev/null \
  | awk -v d="$LAN_DEV" '/Hardware Port:/{p=$0} $0 ~ "Device: "d"$" {sub(/Hardware Port: /,"",p); print p}')
ok "Adapter $LAN_DEV (${LAN_NAME:-unknown}) has link"

# ---------------------------------------------------------------------------
step "3. Internet Sharing enabled"
# ---------------------------------------------------------------------------
# When sharing is on, macOS creates bridge100, enslaves the ethernet adapter
# into it, and puts 192.168.2.1 on the BRIDGE — not on the adapter. Checking
# the adapter's own IP is misleading; it deliberately has none.
if ! ifconfig bridge100 >/dev/null 2>&1; then
  bad "Internet Sharing is OFF (bridge100 does not exist)"
  die "Turn it on:

  System Settings > General > Sharing > Internet Sharing
    Share your connection from:  ${B}Wi-Fi${N}
    To computers using:          ${B}${LAN_NAME:-$LAN_DEV}${N}   <- tick this box
  Then switch Internet Sharing ON and confirm the prompt.

The toggle must be ON (blue), not just configured."
fi

if ! ifconfig bridge100 2>/dev/null | grep -q "inet $SHARED_GW"; then
  bad "bridge100 exists but has no $SHARED_GW address"
  die "Internet Sharing is half-started. Toggle it OFF, wait 5 seconds, then ON
again in System Settings > General > Sharing."
fi
ok "Internet Sharing is ON, Mac is $SHARED_GW"

if ifconfig bridge100 2>/dev/null | grep -q "member: $LAN_DEV"; then
  ok "Sharing to $LAN_DEV (the Jetson's cable)"
else
  bad "Sharing is ON but not to $LAN_DEV"
  die "You are sharing to the wrong adapter. In System Settings > General >
Sharing > Internet Sharing, tick ${B}${LAN_NAME:-$LAN_DEV}${N} under
'To computers using', and untick the others."
fi

# ---------------------------------------------------------------------------
step "4. Jetson picked up an address"
# ---------------------------------------------------------------------------
# The Jetson is a DHCP client. Your Mac's bootpd records every lease it hands
# out here, so this proves the Jetson booted, linked up, and asked for an IP.
JIP=""
for _ in $(seq 1 15); do
  if [ -r "$LEASES" ]; then
    # Reset per record: a lease entry without an ip_address would otherwise
    # leak the previous device's IP and point students at the wrong machine.
    JIP=$(awk '/^{/{ip="";n=""} /ip_address=/{ip=$0} /name=/{n=$0} /^}/{if (n ~ /jetson/ && ip != "") {sub(/.*ip_address=/,"",ip); print ip; exit}}' "$LEASES" 2>/dev/null)
  fi
  [ -n "$JIP" ] && break
  sleep 2
done

if [ -z "$JIP" ]; then
  bad "No Jetson DHCP lease found in $LEASES"
  die "Your Mac is sharing, but the Jetson never asked for an address. Usually:
  - the Jetson is still booting (give it ~40s after power-on, then retry)
  - the Jetson is not powered on
  - the cable is loose at the Jetson end

If it stays broken, the Jetson's eth0 may not be set to DHCP. That is a
Jetson-side fix — see docs/09-internet-sharing-setup.md > 'Jetson-side config'."
fi
ok "Jetson has lease $JIP"

# ---------------------------------------------------------------------------
step "5. Reaching the Jetson"
# ---------------------------------------------------------------------------
if ping -c2 -t3 "$JIP" >/dev/null 2>&1; then
  ok "Jetson answers at $JIP"
else
  bad "Jetson has a lease but does not respond at $JIP"
  die "The lease may be stale (from a previous boot). Toggle Internet Sharing
OFF and ON, wait for the Jetson to re-request, then retry."
fi

MDNS_IP=$(dscacheutil -q host -a name "$JETSON_MDNS" 2>/dev/null \
  | awk '/^ip_address:/{print $2; exit}')
if [ -n "$MDNS_IP" ]; then
  ok "$JETSON_MDNS resolves to $MDNS_IP"
  if [ "$MDNS_IP" != "$JIP" ]; then
    warn "…but that is not the DHCP address ($JIP)."
    warn "The Jetson is advertising an extra address. SSH may pause before"
    warn "falling back. Use $JIP directly if $JETSON_MDNS feels slow."
  fi
else
  warn "$JETSON_MDNS did not resolve — use the IP $JIP instead"
  warn "(mDNS is a convenience only; everything works without it)"
fi

if nc -z -G3 "$JIP" 22 >/dev/null 2>&1; then
  ok "SSH port is open"
else
  bad "SSH port 22 is closed on the Jetson"
  die "The Jetson is reachable but not accepting SSH. Its sshd may not be
running. This needs a monitor or serial console on the Jetson itself."
fi

# ---------------------------------------------------------------------------
step "6. Relay reachability (the Jetson must reach YOUR laptop)"
# ---------------------------------------------------------------------------
# The workshop's Jetson uploads to a relay running on this Mac. The Jetson
# finds it as its default gateway, which is always $SHARED_GW.
if command -v pfctl >/dev/null 2>&1 && sudo -n pfctl -s info >/dev/null 2>&1; then
  ok "NAT active (Jetson's internet flows through this Mac)"
else
  printf "  %s·%s Relay address for the Jetson: %s%s%s\n" "$Y" "$N" "$B" "$SHARED_GW" "$N"
  printf "  %s·%s The Jetson finds this automatically as its default gateway:\n" "$Y" "$N"
  printf "      ip route | awk '/^default/{print \$3}'\n"
fi

# ---------------------------------------------------------------------------
printf "\n%s%s=== ALL CHECKS PASSED ===%s\n" "$B" "$G" "$N"
printf "\nConnect to your Jetson with:\n\n"
printf "    %sssh %s@%s%s        (or: ssh %s@%s)\n\n" "$B" "$JETSON_USER" "$JETSON_MDNS" "$N" "$JETSON_USER" "$JIP"
printf "Verify the Jetson has internet, once you are logged in:\n\n"
printf "    ping -c2 8.8.8.8      # routing\n"
printf "    ping -c2 google.com   # DNS\n\n"
printf "%sNote:%s Internet Sharing often turns itself off after sleep or reboot.\n" "$Y" "$N"
printf "If the Jetson loses internet later, re-run this script first.\n"
