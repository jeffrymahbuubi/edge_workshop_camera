# 10 — Internet Sharing: findings, gotchas & design rationale

Companion to [`09-internet-sharing-setup.md`](09-internet-sharing-setup.md),
which is the steps. **This file is the *why*.** Everything here was found on
hardware or is explicitly marked as unverified.

Read it when a step in 09 breaks, when something looks arbitrary and you're
tempted to "simplify" it, or before changing any address in either file. Most of
what's below is here because it cost real time to discover, and several items look
exactly like harmless cleanups until they aren't.

---

## The one idea that makes this work

**The Jetson is pinned to `192.168.137.100`, and that pins the workshop to
Windows.** This is the whole design. It is a *trade*, not a free win, so it is
worth knowing exactly what was bought and what was sold.

Every OS hardcodes a *different* subnet for internet sharing, and **each one only
routes traffic (NAT) for its own subnet**:

| Student's laptop | Sharing feature | Laptop becomes | Jetson must be in | Gateway |
|---|---|---|---|---|
| **macOS** | Internet Sharing | `192.168.2.1/24` | `192.168.2.x` | `192.168.2.1` |
| **Windows** | ICS | `192.168.137.1/24` | `192.168.137.x` | `192.168.137.1` |
| **Linux** | NM "Shared to other computers" | `10.42.0.1/24` | `10.42.0.x` | `10.42.0.1` |

None of these are configurable — **and that cuts both ways.** It means a static
Jetson works on **exactly one** host OS and fails silently on the others. It also
means that *within* a single OS, the subnet and gateway are **guaranteed
constants**, so a static address there is perfectly predictable.

Because the workshop is **Windows-only**, the second half is the one that matters.
`192.168.137.1` is always the laptop and `192.168.137.100` is always the Jetson,
on every student's machine, with no lease and no name lookup.

**What the static design buys:**

- **One address that can go in the handout.** Under DHCP no fixed IP could be
  printed: ICS hands out a *different* address on each renew — observed `.31` →
  `.225` → `.73` on one Jetson across three renews.
- **No name resolution anywhere in the path.** No `.local`/mDNS, no `mshome.net`,
  no DNS proxy — and so no exposure to a VPN client hijacking DNS (see
  [the Tailscale caveat](#names-mshomenet-not-local-dhcp-design-only)).
- **The stale-lease landmine becomes impossible rather than merely fixed.**
  `dhclient` never runs, so it can never fall back to a stored lease and install
  a dead default gateway.

**What it costs — the whole price, stated plainly:**

- **macOS and Linux students are locked out.** Not degraded: unreachable. No
  laptop-side script can repair it; the Jetson has to be re-imaged.
- **The Jetson is no longer portable.** On any other network its fixed address
  almost certainly doesn't fit.

**One corollary survives unchanged and is still useful:** whatever is sharing *is*
the gateway, so workshop code can still find the laptop with
`ip route | awk '/^default/{print $3}'` and no student types the relay's address.
Worth baking into `mode2_edge.py` as the `RELAY_HOST` default.

---

## The rejected alternative: DHCP

Kept because the reasoning is still correct, and because **this is what to revert
to the moment a non-Windows laptop needs supporting.** It was verified on hardware
on macOS *and* Windows (2026-07-15) — it works; it just doesn't give a fixed IP.

The design was: `eth0` on DHCP, so the Jetson lands in whatever subnet the host's
sharing feature dictates, and students reach it **by name** —
`jetson-2gnano.mshome.net` on Windows, `jetson-2gnano.local` on macOS. One image,
any laptop, nothing to configure on the Jetson.

To go back: set `eth0` to `inet dhcp` in `/etc/network/interfaces`, and **wipe the
lease database** — that second step is not optional, for the reason below.

```
auto eth0
iface eth0 inet dhcp
```

### The landmine that DHCP carries, and why it bit us

`dhclient` keeps **every lease it has ever taken**. When it can't reach a DHCP
server before `timeout`, it **falls back to a stored lease and applies that
lease's `option routers`**. So a Jetson that had ever been on the dev Mac would
install `default via 192.168.2.1` on a *Windows* student's laptop. Nothing is at
that address, and all internet traffic dies there.

This is a **boot-order landmine, not just a stale-image problem**: it triggers
whenever a Jetson boots *before* sharing is switched on — which is the normal
student sequence. It is also the nastiest kind of failure, because everything you
would naturally check looks fine:

```
ssh                      -> works
ping 192.168.137.1       -> works        (gateway is directly connected)
ping google.com          -> RESOLVES     (ICS DNS proxy is directly connected)
ping 8.8.8.8             -> 100% loss    <- only this reveals it
ip route                 -> default via 192.168.2.1   <- the tell
```

DNS working while routing is dead is the fingerprint: the gateway and the DNS
proxy are both on-link, so neither needs the default route. **Check `ip route`
before anything else.**

The fix, which must run before cloning any DHCP image:

```bash
sudo rm -f /var/lib/dhcp/dhclient*.leases
```

Verified: after wiping and rebooting, the Jetson came up with the right gateway
unaided. Wiping removes the fallback, so `dhclient` simply waits and then takes
the correct lease once sharing appears.

> **This bug is what set off the 2026-07-16 redesign — and it's worth being honest
> about the causality.** It was **never an addressing problem**; it was a
> `dhclient` problem. The static design kills it as a side effect (no `dhclient`,
> no stored leases), but wiping the leases would have fixed it just as well *while
> keeping macOS support*. The static design was chosen for the **fixed IP**, not
> as a bug fix. Don't let this section be read as "DHCP was broken."

### Other DHCP-era image settings

- `/etc/dhcp/dhclient.conf`: `timeout 300` → **`15`**, so a boot with no sharing
  doesn't stall for five minutes. Now inert (nothing runs it), left in place so a
  revert starts from the fixed value.
- `avahi-daemon` provides `jetson-2gnano.local`. Unused on the Windows static path
  now that students type the IP, but harmless and still handy on the dev bench.
- The Jetson already sends its hostname (`send host-name = gethostname();`), which
  is what made `mshome.net` registration work with zero setup.

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

Windows ICS is the opposite: it puts `192.168.137.1` **directly on the adapter**,
no bridge, so `ipconfig` shows what you'd expect.

---

## What "correct" looks like

### Windows + static — the current design

**Captured on hardware after a real reboot, 2026-07-16.** Both halves verified.

```
# Laptop (Windows, ICS on)
Ethernet 3:  192.168.137.1/24          <- ICS puts it straight on the adapter

# Jetson
eth0     inet 192.168.137.100/24       <- static, and the ONLY address on eth0
default via 192.168.137.1 dev eth0 onlink   <- hardcoded, NOT learned
pgrep dhclient  -> nothing             <- dhclient must never run
ping 8.8.8.8    -> 0% loss, 8.371ms    (routing)
ping google.com -> 0% loss             (DNS)
systemd-resolve --status -> DNS Servers: 192.168.137.1
```

### The DNS stack on this image is not what it looks like

Worth knowing before you "fix" a working box.

The image runs **systemd-resolved** *and* **resolvconf** (1.79). `/etc/resolv.conf`
is a symlink to `/run/resolvconf/resolv.conf`. What lands in it depends on how
`eth0` is configured, which is genuinely surprising:

| Jetson config | `/etc/resolv.conf` contains | Why |
|---|---|---|
| **DHCP** | `nameserver 127.0.0.53` **only** | `dhclient` feeds systemd-resolved directly; resolvconf's libc output only carries the stub |
| **static + `dns-nameservers`** | `nameserver 192.168.137.1` **and** `127.0.0.53` | ifupdown's resolvconf hook writes the nameserver into resolvconf's libc list, ahead of the stub |

So under the current design `192.168.137.1` **does** appear in `resolv.conf`, and
the `127.0.0.53` stub line appearing next to it is **not a fault**. Under DHCP its
absence was also not a fault. In both cases the authoritative check is:

```bash
systemd-resolve --status | grep "DNS Servers"    # -> 192.168.137.1
getent hosts google.com                          # the real test
```

`dns-nameservers` was the open risk before this was tested — it only works if
`resolvconf` is wired up, and it is (`/sbin/resolvconf`, package
`resolvconf 1.79ubuntu10.18.04.3`, hook `/etc/resolvconf/update.d/libc`). Confirmed
working.

### macOS + DHCP — historical

Captured on the dev Mac + Jetson after a reboot (2026-07-15), under
[the DHCP design](#the-rejected-alternative-dhcp). The reference for what a
reverted image should look like:

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

This is also why any laptop-side alias you add for debugging must have **no
gateway**.

### "Internet Sharing is on but the Jetson has no internet"

Almost certainly the **Jetson is not in the host's subnet**. Confirmed on
hardware: macOS **NATs only for `192.168.2.0/24`**. A Jetson at, say,
`192.168.1.100` can be made *reachable* (add
`sudo ifconfig bridge100 alias 192.168.1.2 255.255.255.0` — it pings at 1.6ms) but
it gets **no internet**, because macOS refuses to translate an off-scope source.

Check on the Jetson:

```bash
ip -4 addr show eth0    # want the host's subnet
ip route                # want: default via <the host>
```

> **Note on a tempting shortcut, with an honest gap.** Adding a secondary IP to
> the *host* so it can reach an off-scope Jetson restores **reachability** on
> Windows ICS, and it's persistent in the adapter config there — unlike macOS,
> where `bridge100` is destroyed on every toggle, so the alias can't persist and
> has no GUI path.
>
> **Whether it also restores *internet* on Windows is UNTESTED.** macOS provably
> refuses to NAT an off-scope source (above). Nobody has measured whether ICS
> behaves the same way. Do not read the sentence above as "the shortcut works on
> Windows" — it buys reachability, and the NAT question is open. If it ever
> matters, the experiment is: give the laptop `192.168.1.50/24`, point the
> Jetson's default route at it, and see whether `ping 8.8.8.8` survives.
>
> Related: a snippet doing exactly this (`netsh interface ip add address …` plus
> `ip route add default via …`) circulates and looks like a complete solution. It
> **is not** — it contains no NAT step at all. On a clean laptop it buys SSH and
> zero internet.

### "`.local` is slow or hangs" (DHCP design only)

> Not applicable to the current static image, which puts no name in the path.

The Jetson advertises **every** address it has. If it holds an extra address the
student's laptop can't reach, SSH tries that first and stalls before falling back.
This is precisely why the DHCP design had to drop the `eth0:1` alias.

On **Windows**, `.local` didn't resolve at all rather than hanging — use
`jetson-2gnano.mshome.net`. See [Names](#names-mshomenet-not-local-dhcp-design-only).

### "It worked, now it doesn't"

Internet Sharing (both OSes) **often turns itself off after sleep or reboot.**
Re-run the script; it's the first thing to check, and it's the single most common
failure.

---

## Windows findings

Verified end-to-end on hardware (2026-07-15, re-verified 2026-07-16): Windows 11
Pro 22631, ASIX USB dongle, Jetson 4GB.

Confirmed as predicted: ICS forces `192.168.137.1/24` (registry `ScopeAddress`,
not configurable); it needs local admin. That the subnet and gateway are **not
configurable** is exactly what makes the static `192.168.137.100` safe to print in
a handout.

Everything in this section is **laptop-side and holds under both designs** — none
of it depends on whether the Jetson runs DHCP or a static address.

Five things we got wrong or didn't know, each of which would have cost class time.

### `192.168.137.1` is not `192.168.1.37`

Easy to misread, and it inverts the whole mental model. The third octet is
**137**. `192.168.137.0/24` and `192.168.1.0/24` are unrelated subnets — so the
old `192.168.1.100` fallback was exactly as off-scope from ICS as it was from
macOS's `192.168.2.1`. There was never a "Windows is closer so it needs less
setup" shortcut; that intuition is purely a misreading of the digits.

This is also why the static address is `192.168.137.100` and **not**
`192.168.1.100`, which is the obvious-looking choice. A second reason to avoid
`192.168.1.0/24`: it is the most common consumer-router subnet in existence, so a
student whose own Wi-Fi is on it would get a live subnet conflict.

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

### Names: `.mshome.net`, not `.local` (DHCP design only)

> **Not used by the current image**, which has a static IP and needs no name at
> all. Kept because it is the correct answer *if* you revert to
> [DHCP](#the-rejected-alternative-dhcp) — and because the Tailscale caveat below
> is worth knowing regardless.

`jetson-2gnano.local` **did not resolve** on the test laptop — `ssh`, `ping`, and
`Resolve-DnsName` all failed outright. Don't put `.local` in a Windows handout.

Use **`jetson-2gnano.mshome.net`** instead. ICS runs a DNS proxy that
auto-registers each DHCP client's hostname under `mshome.net`, and the Jetson
already sends its hostname. So this works with **zero setup on either side** and
is the direct Windows equivalent of `.local`. Verified: resolves, pings, and SSHs.

> **Caveat, honestly.** The dev laptop runs **Tailscale**, which installs an NRPT
> policy hijacking `.` (all DNS) to `100.100.100.100`. That is a plausible cause
> of the `.local` failure, so a clean student laptop *might* resolve `.local`
> fine. We didn't isolate it, because `mshome.net` works regardless and sidesteps
> the question entirely. If you ever need `.local` on Windows, suspect a VPN
> client first.

**Under DHCP, using a name is mandatory, not a convenience.** ICS hands out a
*different* address on each renew — observed `.31` → `.225` → `.73` across three
renews on one Jetson, all confirmed as the same board by its MAC in the ARP table.
**This is the single fact that motivated the static redesign**: no fixed IP could
be printed in a handout, so the choice was a name or nothing.

### ICS can be "on" and still not working

Found on hardware 2026-07-16, and it would have stranded students.

ICS's sharing flags and ICS's *address* are separate state. Editing the shared
adapter's IPv4 settings by hand — setting a static address, or ticking **"Obtain
an IP address automatically"** — **strips `192.168.137.1` while leaving
`SharingEnabled` true**. ICS never notices and never re-applies it, so the adapter
falls back to an APIPA `169.254.x.x` and nothing reaches the Jetson. The Sharing
tab still shows the box ticked.

The lesson generalises: **ICS owns that address.** It assigns `192.168.137.1`
itself; it does not obtain one. Never hand-edit IPv4 on the shared adapter — the
repair is always an off/on toggle of sharing, never an IP edit.

Note `PrefixOrigin` **cannot** tell you who set the address: ICS's own
`192.168.137.1` reports `Manual`, exactly as a hand-set one does. Don't read guilt
into that field — an early misreading of it is what produced the bad advice that
caused this outage in the first place.

The script now treats a missing `192.168.137.1` as *not shared*, regardless of the
flags, and forces a re-toggle to repair it. Verified on hardware:

```
[ ~] Sharing is flagged ON but 'Ethernet 3' has no 192.168.137.1 — forcing a re-toggle
[OK] Laptop is 192.168.137.1 on 'Ethernet 3'
```

### The relay firewall rule is real — verified blocked, then open

The prediction was exactly right. With a listener up on `0.0.0.0:8000` and no
rule, the Jetson's connection **times out silently** — nothing in any log, no
error on either end. The ICS adapter lands in the **Public** firewall profile,
whose default inbound action is Block.

The documented command works verbatim (returns `Ok.`, creates an `Any`-profile
inbound allow):

```
netsh advfirewall firewall add rule name="Workshop Relay 8000" dir=in action=allow protocol=TCP localport=8000
```

After it: the Jetson connects and the relay replies. The script does this for you.
Full path verified — the Jetson discovers the relay as its default gateway
(`ip route | awk '/^default/{print $3}'` → `192.168.137.1`), connects, and the
listener logs the inbound connection. This has **no macOS equivalent**.

### Why the Windows script writes, and the macOS one doesn't

`scripts/setup-internet-sharing-windows.ps1` **configures ICS**, unlike its
read-only macOS counterpart. That inconsistency is deliberate.

The macOS script is read-only because macOS has **no supported CLI** for Internet
Sharing — the unofficial route (writing `com.apple.nat.plist` and poking
`launchctl`) is undocumented, needs `sudo`, and Apple has broken it between
releases. A script that half-enables sharing on 30 laptops is worse than a GUI
click. Windows has a **documented COM API** (`HNetCfg.HNetShare`), so automating it
is supported rather than a hack.

More importantly, the step being automated — **picking the right adapter** — is
the one students get wrong, because the dropdown shows exactly the unstable name
described above. Here, scripting removes a failure mode rather than adding one.

The macOS script's checks, and what each proves:

| Check | What it proves |
|---|---|
| 1. Wi-Fi + internet | You have a connection to share at all |
| 2. Adapter has link | Cable/adapter/Jetson-power are fine |
| 3. `bridge100` + `192.168.2.1` + correct member | Sharing is ON *and pointed at the right adapter* |
| 4. Lease in `/var/db/dhcpd_leases` | The Jetson booted, linked up, and asked for an IP |
| 5. Ping + mDNS + port 22 | The Jetson is actually reachable and sshd is up |

Verified against a deliberately broken machine (ICS enabled but pointed at a
disconnected built-in `Ethernet` — the exact bug we hit): the Windows script
cleared the stale sharing, repointed to the live adapter, created the firewall
rule, and the Jetson had internet again, all in one run.

### Reaching the Jetson when sharing is off

**This got much simpler under the static design.** The Jetson now sits at a fixed
`192.168.137.100` whether or not sharing is on, so reaching it needs nothing but
an address on that subnet:

```powershell
New-NetIPAddress -InterfaceAlias "Ethernet 3" -IPAddress 192.168.137.50 -PrefixLength 24
```

**No gateway on purpose** — that's what stops the Jetson hijacking the default
route (see ["Plugging in the cable kills my Wi-Fi"](#plugging-in-the-cable-kills-my-wi-fi)).
**ICS wipes hand-added addresses on that adapter when sharing is enabled**, so
treat this as a debugging tool, not a persistent setting — and read
[ICS can be "on" and still not working](#ics-can-be-on-and-still-not-working)
before touching that adapter's IPv4 at all.

> **Historical.** Under the DHCP design this was harder: the Jetson's fallback was
> an `eth0:1` alias at `192.168.1.100`, off-scope for ICS, needing a laptop alias
> at `192.168.1.50`. That alias was confirmed to coexist with ICS's
> `192.168.137.1` on the same adapter and persist across reboots (macOS cannot do
> either — `bridge100` is destroyed on every toggle). Both the stanza and the trick
> are retired.

---

## Open risks

- **Group policy.** University-managed Windows laptops sometimes **disable ICS by
  group policy**. Untested — the dev laptop is unmanaged. With live installs on
  the critical path, an affected student is stuck. A fallback plan still needs
  deciding before the workshop. **This is now the only untested item on the
  critical path.**
- **Does Windows ICS NAT an off-scope source?** Still unmeasured — see
  [the shortcut note](#internet-sharing-is-on-but-the-jetson-has-no-internet).
  It no longer blocks anything (the Jetson is in-scope by design), but it's the
  one open question if the addressing is ever revisited.

### Closed

- ~~`resolvconf` on the Jetson~~ — **verified working** 2026-07-16. See
  [the DNS stack](#the-dns-stack-on-this-image-is-not-what-it-looks-like).
- ~~The static Jetson image is not hardware-verified~~ — **verified end-to-end**
  2026-07-16 after a real reboot: `192.168.137.100` as the only address on `eth0`,
  `default via 192.168.137.1`, `ping 8.8.8.8` at 0% loss, DNS resolving, and no
  `dhclient` process.

---

## Corrections to earlier claims in this pack

Recorded because each was asserted before it was tested, and someone re-reading
old notes could be misled by them.

| Claim once made here | Reality |
|---|---|
| "`PrefixOrigin: Manual` means someone hand-set the address" | **False.** ICS's own `192.168.137.1` also reports `Manual`. The field cannot attribute the address. Acting on this produced the advice that broke ICS. |
| "Set the shared adapter's IPv4 back to *Obtain automatically* to let ICS re-apply it" | **Actively harmful.** That strips ICS's address and it never comes back. The repair is the sharing off/on toggle. |
| "`/etc/resolv.conf` will always show only the `127.0.0.53` stub" | **False under static.** It lists `192.168.137.1` too. True only under DHCP — see the table above. |
| "The Jetson's internet was broken by the stale-lease bug" | **Unproven for that specific incident.** When finally inspected, `ip route` was correct and `ping 8.8.8.8` worked; the outage was the ICS breakage. The stale-lease bug is real and documented, but it was not what happened that day. |
