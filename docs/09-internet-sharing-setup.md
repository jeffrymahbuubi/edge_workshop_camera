# 09 — Internet Sharing: Laptop → Jetson (macOS + Windows done)

> **What this solves.** The Jetson has **no Wi-Fi** and the lab Wi-Fi uses
> **client isolation** (devices can't talk to each other). So the only link
> between a student's laptop and their Jetson is the **LAN cable**, and the only
> way the Jetson reaches the internet is the laptop **sharing** its Wi-Fi down
> that cable. Students install libraries live during the workshop, so this is on
> the critical path — not a nice-to-have.
>
> **Status**: macOS **done and verified on hardware** (2026-07-15).
> Windows **done and verified on hardware** (2026-07-15) — see [Windows](#windows).

---

## TL;DR — the student flow (macOS)

1. Connect to lab Wi-Fi.
2. Plug USB-ethernet adapter into the Mac, LAN cable to the Jetson, power on the Jetson.
3. **System Settings → General → Sharing → Internet Sharing**: share **from Wi-Fi**, **to** your USB adapter. Toggle **ON**.
4. Run `bash scripts/setup-internet-sharing-macos.sh` — it checks every layer and names whatever is broken.
5. `ssh jetson@jetson-2gnano.local`

That's it. Nothing to configure on the Jetson, and no IP addresses to type.

## TL;DR — the student flow (Windows)

1. Connect to lab Wi-Fi.
2. Plug the USB-ethernet dongle (**or** use the laptop's built-in LAN port), LAN cable to the Jetson, power on the Jetson.
3. Open **PowerShell as Administrator** and run:
   `powershell -ExecutionPolicy Bypass -File scripts\setup-internet-sharing-windows.ps1`
   It enables ICS on the right adapter, adds the relay firewall rule, and checks every layer.
4. `ssh jetson@jetson-2gnano.mshome.net`

Shorter than macOS, because the Windows script *configures* sharing rather than
guiding you to a toggle — see [Why the Windows script writes](#why-the-windows-script-writes-and-the-macos-one-doesnt).

> **Windows uses `.mshome.net`, not `.local`.** Different name, same idea. See
> [Names](#names-mshomenet-not-local).

---

## The one idea that makes this work

**The Jetson is a DHCP client, not a fixed IP.** This is the whole design, and
it's worth understanding because the obvious alternative is a trap.

Every OS hardcodes a *different* subnet for internet sharing, and **each one only
routes traffic (NAT) for its own subnet**:

| Student's laptop | Sharing feature | Laptop becomes | Jetson gets | Gateway |
|---|---|---|---|---|
| **macOS** | Internet Sharing | `192.168.2.1/24` | `192.168.2.x` | `192.168.2.1` |
| **Windows** | ICS | `192.168.137.1/24` | `192.168.137.x` | `192.168.137.1` |
| **Linux** | NM "Shared to other computers" | `10.42.0.1/24` | `10.42.0.x` | `10.42.0.1` |

None of these are configurable. So a Jetson pinned to any static IP works on
**exactly one** host OS and fails silently on the others — no error, just a device
that can't be reached. A DHCP client lands in the right subnet automatically,
whatever the student brought to class.

**Two corollaries fall out of this, and both are useful:**

- **The relay is always the Jetson's default gateway.** Whatever OS is sharing,
  the machine sharing *is* the gateway. So the workshop code can find the laptop
  with `ip route | awk '/^default/{print $3}'` and no student ever types an IP.
  Worth baking into `mode2_edge.py` as the `RELAY_HOST` default.
- **Students need zero laptop network config.** No manual IPs, no subnet masks,
  no service ordering. Just the sharing toggle.

---

## macOS: what actually happens when you flip the toggle

This surprised us during setup and is worth knowing before you debug anything.

**macOS does not configure the shared adapter.** It creates a **new interface
called `bridge100`**, enslaves the ethernet adapter into it (the adapter goes
`PROMISC` and **loses its own IP**), puts `192.168.2.1/24` on the *bridge*, and
runs `bootpd` (DHCP) plus NAT there.

So when debugging: **`ifconfig en12` shows no IP and that is correct.** Look at
`ifconfig bridge100`. Checking the adapter is the natural first move and it will
mislead you.

`bridge100` is created on demand and **destroyed when sharing is toggled off**.
Anything you add to it (an alias, say) is volatile by nature.

---

## Verified working state

Captured on the dev Mac + Jetson after a reboot, so this is what "correct" looks like:

```
# Mac
bridge100: inet 192.168.2.1 netmask 0xffffff00
           member: en12
/var/db/dhcpd_leases:  name=jetson-2gNANO  ip_address=192.168.2.2

# Jetson
eth0     inet 192.168.2.2/24      <- real DHCP lease from the Mac
default via 192.168.2.1 dev eth0  <- gateway learned automatically
ping 8.8.8.8   -> OK             (routing)
ping google.com -> OK            (DNS)
```

---

## The scripts

| Platform | Script | Behaviour |
|---|---|---|
| macOS | `scripts/setup-internet-sharing-macos.sh` | **Read-only** — checks and guides |
| Windows | `scripts/setup-internet-sharing-windows.ps1` | **Configures ICS**, then checks (admin) |

Both check the same layers in dependency order and stop at the first failure.
They differ in whether they *write*, for a reason —
see [Why the Windows script writes](#why-the-windows-script-writes-and-the-macos-one-doesnt).

### macOS

`scripts/setup-internet-sharing-macos.sh` — **read-only**. It changes no network
settings; it checks each layer in dependency order and stops at the first failure
with a specific fix, because every later check depends on the earlier ones.

| Check | What it proves |
|---|---|
| 1. Wi-Fi + internet | You have a connection to share at all |
| 2. Adapter has link | Cable/adapter/Jetson-power are fine |
| 3. `bridge100` + `192.168.2.1` + correct member | Sharing is ON *and pointed at the right adapter* |
| 4. Lease in `/var/db/dhcpd_leases` | The Jetson booted, linked up, and asked for an IP |
| 5. Ping + mDNS + port 22 | The Jetson is actually reachable and sshd is up |

**Why it doesn't enable sharing for you.** macOS has **no supported CLI** for
Internet Sharing. The unofficial route (writing `com.apple.nat.plist` and poking
`launchctl`) is undocumented, needs `sudo`, and Apple has broken it between
releases. A script that half-enables sharing on 30 laptops is worse than a GUI
click — so the script guides you to the toggle and then *proves the result*.

---

## Troubleshooting

### "Plugging in the cable kills my Wi-Fi"

This was the original bug on the dev Mac and it's worth recording, though
**students should never hit it** (the cause is fixed in the Jetson image).

It was **not** an IP conflict. The Jetson was running `isc-dhcp-server`, whose
`/etc/dhcp/dhcpd.conf` contained `option routers 192.168.1.100` — the Jetson
advertising *itself* as a gateway. The Mac's adapter was on DHCP, accepted it, and
because the USB adapter outranked Wi-Fi in the service order, macOS made the
Jetson the **primary default route**. All internet traffic went into a box that
doesn't forward. Wi-Fi stayed connected the whole time; it just wasn't being used.

Diagnose with:
```bash
route -n get default | grep -E 'gateway|interface'   # should name your Wi-Fi
netstat -rn -f inet | grep '^default'                # two defaults = trouble
```

Fixes, in order of preference:
1. **Jetson-side (the real fix):** `sudo systemctl disable --now isc-dhcp-server`
2. **Mac-side:** set the adapter to Manual IP with the **Router field left blank**
   (System Settings → Network → *adapter* → Details → TCP/IP). No router = no
   default route = nothing to hijack. The GUI is more reliable here than
   `networksetup -setmanual … ""`.
3. **Belt-and-braces:** Network → **⋯** → Set Service Order → drag Wi-Fi to top.

### "Internet Sharing is on but the Jetson has no internet"

Almost certainly the **Jetson is not in `192.168.2.x`**. Confirmed on hardware:
macOS **NATs only for `192.168.2.0/24`**. A Jetson at, say, `192.168.1.100` can be
made *reachable* (add `sudo ifconfig bridge100 alias 192.168.1.2 255.255.255.0` —
it pings at 1.6ms) but it gets **no internet**, because macOS refuses to translate
an off-scope source. Check on the Jetson:

```bash
ip -4 addr show eth0    # want 192.168.2.x
ip route                # want: default via 192.168.2.1
```

> **Note on a tempting shortcut.** Adding a secondary IP to the *host* so it can
> reach a static Jetson **works on Windows ICS** (it's persistent in the adapter
> config there) but **does not work on macOS** — it restores reachability but not
> internet, and `bridge100` is destroyed on every toggle so the alias can't
> persist and has no GUI path. Don't build the workshop on it.

### "`.local` is slow or hangs"

The Jetson advertises **every** address it has. If it holds an extra address the
student's laptop can't reach, SSH tries that first and stalls before falling back.
Use the IP from the script's output. See [Before cloning](#before-cloning-the-student-image).

On **Windows**, `.local` didn't resolve at all rather than hanging — use
`jetson-2gnano.mshome.net`. See [Names](#names-mshomenet-not-local).

### "It worked, now it doesn't"

macOS Internet Sharing **often turns itself off after sleep or reboot.** Re-run
the script; it's the first thing to check.

---

## Jetson-side config (reference — already done in the image)

`eth0` is managed by **ifupdown** (`/etc/network/interfaces`), **not**
NetworkManager — `nmcli` shows only `docker0` and Wi-Fi profiles, so `nmcli`
commands for eth0 will appear to succeed and do nothing.

```
auto eth0
iface eth0 inet dhcp

auto eth0:1
iface eth0:1 inet static
address 192.168.1.100
netmask 255.255.255.0
```

- `eth0:1` is a **separate stanza on purpose** so it comes up even if the DHCP
  lease fails. It is the fallback path for reaching the Jetson with no sharing.
- The old `gateway 192.168.1.1` was **removed** — nothing ever existed at that
  address, so the Jetson had never had a working default route.
- `/etc/dhcp/dhclient.conf`: `timeout 300` → **`15`**, so a boot with no sharing
  doesn't stall for five minutes.
- `isc-dhcp-server` is **disabled**. This is mandatory: with `eth0` on DHCP the
  Jetson's own `dhclient` would race its own `dhcpd`. It also bound *every*
  interface (`INTERFACESv4=""`), so it would become a **rogue DHCP server on the
  lab Wi-Fi** if the Jetson ever joined it.
- `avahi-daemon` provides `jetson-2gnano.local`. Already installed and active.
- Hostname is `jetson-2gNANO` (mDNS lowercases it). Misleading — it's a 4GB board;
  the name is inherited from the SEA/AprilTag 2GB image. Kept deliberately.

### Before cloning the student image

**Wipe the DHCP lease database.** Found on hardware (2026-07-15) and it would
have hit **every student**:

```bash
sudo rm -f /var/lib/dhcp/dhclient*.leases
```

`dhclient` keeps every lease it has ever taken. When it can't reach a DHCP server
before `timeout` (15s), it **falls back to a stored lease and applies its
`option routers`** — so a Jetson that had ever been on the dev Mac installs
`default via 192.168.2.1` on a *Windows* student's laptop. Nothing is at that
address, and all internet traffic dies there.

The symptom is the nastiest kind, because everything you'd naturally check looks
fine:

```
ssh                      -> works
ping 192.168.137.1       -> works        (gateway is directly connected)
ping google.com          -> RESOLVES     (ICS DNS proxy is directly connected)
ping 8.8.8.8             -> 100% loss    <- only this reveals it
ip route                 -> default via 192.168.2.1   <- the tell
```

DNS working while routing is dead is the fingerprint: both the gateway and the
DNS proxy are on-link, so neither needs the default route. **Check `ip route`
before anything else.**

This is a boot-order landmine, not just a stale-image problem: it triggers
whenever a Jetson boots *before* sharing is switched on — which is the normal
student sequence. Wiping the lease DB removes the fallback, so `dhclient` simply
waits and then takes the correct lease once ICS appears. Verified: after wiping
and rebooting, the Jetson came up with the right gateway unaided.

**Remove the `eth0:1` stanza.** Avahi advertises *both* `192.168.1.100` and the
DHCP address. On the dev Mac that's harmless (it holds a `192.168.1.2` alias), but
a **Windows student is on `192.168.137.x` and cannot reach `192.168.1.100`** — so
`ssh jetson@jetson-2gnano.local` would hang on the unreachable address before
falling back. Thirty students, every connection.

The trade-off, accepted deliberately: without the fallback, a student whose
sharing fails has **no network path to their Jetson** — they'd need a monitor or
serial console. Keep `eth0:1` on the **dev unit only**.

---

## Windows

Verified end-to-end on hardware (2026-07-15): Windows 11 Pro 22631, ASIX USB
dongle, Jetson 4GB. The DHCP-client design held — **the Jetson needed no change
for Windows**, which is the whole payoff of not pinning a static IP.

Confirmed as predicted: ICS forces `192.168.137.1/24` (registry `ScopeAddress`,
not configurable); it puts that IP **directly on the adapter**, no bridge, so
`ipconfig` shows what you'd expect; and it needs local admin.

Four things we got wrong or didn't know, each of which would have cost class time.

### `192.168.137.1` is not `192.168.1.37`

Easy to misread, and it inverts the whole mental model. The third octet is
**137**. `192.168.137.0/24` and `192.168.1.0/24` are unrelated subnets, so ICS is
exactly as off-scope from the Jetson's `192.168.1.100` fallback as macOS's
`192.168.2.1` was. There is no "Windows is closer so it needs less setup"
shortcut — that intuition is a misreading.

### Adapter names are per-laptop and must never be hardcoded

**This is the one that would have broken a handout.** The ICS dropdown lists
adapters by **name** (`Ethernet 3`), and that name is a local artifact: Windows
numbers `Ethernet`, `Ethernet 2`, `Ethernet 3`… incrementally per machine,
counting every NIC instance it has ever enumerated. The same dongle appears as:

| Student's laptop | Likely name |
|---|---|
| No built-in NIC (most ultrabooks) | `Ethernet` |
| Has a built-in NIC (our dev laptop) | `Ethernet 2` / `Ethernet 3` |
| Has docked or used other adapters | `Ethernet 4`, `5`, … |

It isn't even stable on one laptop: the number binds to the **USB port**, so
moving the dongle can produce a new name. "Choose Ethernet 3" would be wrong for
most of the class.

**Identify the adapter by what it is, not what it's called** — the only wired
(`802.3`) adapter with link. A cabled, powered Jetson is what makes it `Up`:

```powershell
Get-NetAdapter -Physical | Where-Object { $_.Status -eq 'Up' -and $_.PhysicalMediaType -eq '802.3' }
```

This is brand-agnostic and covers **both** a USB dongle and a built-in LAN port,
so it needs no assumption about what students bring. `-Physical` already excludes
Hyper-V, WSL, VPN and Wi-Fi Direct adapters; the media type excludes Wi-Fi
(`Native 802.11`) and Bluetooth. The script refuses to act if this matches
anything other than exactly one adapter — a docked student with a second live
ethernet is ambiguous, and guessing there recreates the very bug this prevents.

### Names: `.mshome.net`, not `.local`

`jetson-2gnano.local` **did not resolve** on the test laptop — `ssh`, `ping`, and
`Resolve-DnsName` all failed outright. Don't put `.local` in the Windows handout.

Use **`jetson-2gnano.mshome.net`** instead. ICS runs a DNS proxy that
auto-registers each DHCP client's hostname under `mshome.net`, and the Jetson
already sends its hostname (`send host-name = gethostname();` in
`dhclient.conf`). So this works with **zero setup on either side** and is the
direct Windows equivalent of `.local`. Verified: resolves, pings, and SSHs.

> **Caveat, honestly.** The dev laptop runs **Tailscale**, which installs an NRPT
> policy hijacking `.` (all DNS) to `100.100.100.100`. That is a plausible cause
> of the `.local` failure, so a clean student laptop *might* resolve `.local`
> fine. We didn't isolate it, because `mshome.net` works regardless and sidesteps
> the question entirely. If you ever need `.local` on Windows, suspect a VPN
> client first.

**Using a name is mandatory, not a convenience.** ICS hands out a *different*
address on each renew — we observed `.31` → `.225` → `.73` across three renews on
one Jetson. No fixed IP can go in a handout.

### The relay firewall rule is real — verified blocked, then open

The doc's prediction was exactly right. With a listener up on `0.0.0.0:8000` and
no rule, the Jetson's connection **times out silently** — nothing in any log, no
error on either end. The ICS adapter lands in the **Public** firewall profile,
whose default inbound action is Block.

The documented command works verbatim (returns `Ok.`, creates an `Any`-profile
inbound allow):

```
netsh advfirewall firewall add rule name="Workshop Relay 8000" dir=in action=allow protocol=TCP localport=8000
```

After it: the Jetson connects and the relay replies. The script does this for
you. Full path verified — the Jetson discovers the relay as its default gateway
(`ip route | awk '/^default/{print $3}'` → `192.168.137.1`), connects, and the
listener logs the inbound connection.

### Why the Windows script writes, and the macOS one doesn't

`scripts/setup-internet-sharing-windows.ps1` **configures ICS**, unlike its
read-only macOS counterpart. That inconsistency is deliberate.

The macOS script is read-only because macOS has **no supported CLI** for Internet
Sharing — the unofficial route breaks between releases. Windows has a
**documented COM API** (`HNetCfg.HNetShare`), so automating it is supported
rather than a hack.

More importantly, the step being automated — **picking the right adapter** — is
the one students get wrong, because the dropdown shows exactly the unstable name
described above. Here, scripting removes a failure mode rather than adding one.

Requires an **Administrator PowerShell** (both ICS and firewall rules do). Pass
`-CheckOnly` to diagnose without changing anything — though note the ICS COM API
returns nothing unelevated, so `-CheckOnly` still needs admin to see past step 2.

Verified against a deliberately broken machine (ICS enabled but pointed at a
disconnected built-in `Ethernet` — the exact bug we hit): the script cleared the
stale sharing, repointed to the live adapter, created the firewall rule, and the
Jetson had internet again, all in one run.

### GUI equivalent

If you'd rather click, or the script fails:

1. `Win+R` → **`ncpa.cpl`**
2. Right-click **Wi-Fi** → **Properties** → **Sharing** tab
3. Tick *"Allow other network users to connect…"*
4. **Home networking connection** → pick your Jetson's adapter. It's the one
   whose grey subtitle names your dongle, or that appears/disappears when you
   unplug it. **Do not** trust the `Ethernet N` number.
5. **OK**

The Sharing tab lives on the adapter you share *from* (Wi-Fi); the dropdown picks
the destination. That's macOS's "share from / to" split across one panel.

To repoint an existing share, untick → **OK** → reopen → re-tick → choose the
right adapter. Note the dropdown shows only names, never descriptions — which is
the trap.

### Reaching a Jetson with no sharing (dev unit only)

The Jetson's `eth0:1` fallback (`192.168.1.100`) is off-scope for ICS, so Windows
needs an address on that subnet to reach it:

```powershell
New-NetIPAddress -InterfaceAlias "Ethernet 3" -IPAddress 192.168.1.50 -PrefixLength 24
```

**No gateway on purpose** — that's what stops the Jetson hijacking the default
route (see ["Plugging in the cable kills my Wi-Fi"](#plugging-in-the-cable-kills-my-wi-fi)).

Confirmed: this **coexists with ICS's `192.168.137.1` on the same adapter** and
persists across reboots, which the doc predicted and macOS cannot do. Useful as a
lifeline while debugging. **Note ICS wipes it when you enable sharing**, so re-add
it afterwards if you want the fallback. Students shouldn't need this — the
`eth0:1` stanza is removed from their image.

**Open risk, no workaround.** University-managed Windows laptops sometimes
**disable ICS by group policy**. Untested — the dev laptop is unmanaged. With live
installs on the critical path, an affected student is stuck. Still needs a
fallback plan (a spare Mac? a pre-baked image?) decided before the workshop.
