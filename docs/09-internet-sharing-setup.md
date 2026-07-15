# 09 — Internet Sharing: Laptop → Jetson (macOS done, Windows TBD)

> **What this solves.** The Jetson has **no Wi-Fi** and the lab Wi-Fi uses
> **client isolation** (devices can't talk to each other). So the only link
> between a student's laptop and their Jetson is the **LAN cable**, and the only
> way the Jetson reaches the internet is the laptop **sharing** its Wi-Fi down
> that cable. Students install libraries live during the workshop, so this is on
> the critical path — not a nice-to-have.
>
> **Status**: macOS **done and verified on hardware** (2026-07-15).
> Windows **not written yet** — see [Windows (TBD)](#windows-tbd).

---

## TL;DR — the student flow (macOS)

1. Connect to lab Wi-Fi.
2. Plug USB-ethernet adapter into the Mac, LAN cable to the Jetson, power on the Jetson.
3. **System Settings → General → Sharing → Internet Sharing**: share **from Wi-Fi**, **to** your USB adapter. Toggle **ON**.
4. Run `bash scripts/setup-internet-sharing-macos.sh` — it checks every layer and names whatever is broken.
5. `ssh jetson@jetson-2gnano.local`

That's it. Nothing to configure on the Jetson, and no IP addresses to type.

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

## The script

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

**Remove the `eth0:1` stanza.** Avahi advertises *both* `192.168.1.100` and the
DHCP address. On the dev Mac that's harmless (it holds a `192.168.1.2` alias), but
a **Windows student is on `192.168.137.x` and cannot reach `192.168.1.100`** — so
`ssh jetson@jetson-2gnano.local` would hang on the unreachable address before
falling back. Thirty students, every connection.

The trade-off, accepted deliberately: without the fallback, a student whose
sharing fails has **no network path to their Jetson** — they'd need a monitor or
serial console. Keep `eth0:1` on the **dev unit only**.

---

## Windows (TBD)

Not written. To be done on the spare Windows desktop, mirroring this doc.
What we already know:

- **ICS forces `192.168.137.1/24`** and is not configurable through any supported
  UI. The DHCP-client design means the Jetson needs **no change** for Windows.
- **Windows Firewall blocks inbound connections on the ICS adapter by default.**
  The relay listens on **port 8000**, so the Jetson's uploads will be **silently
  dropped**. Every Windows student needs this once, as admin:
  ```
  netsh advfirewall firewall add rule name="Workshop Relay 8000" dir=in action=allow protocol=TCP localport=8000
  ```
  This has no macOS equivalent and is the most likely thing to eat class time.
- **ICS needs local admin** and the *Internet Connection Sharing* service enabled.
- **ICS frequently doesn't survive reboot/sleep** and needs re-toggling.
- Unlike macOS, ICS puts its IP **directly on the adapter** (no bridge), so
  `ipconfig` shows what you'd expect.

**Open risk, no workaround.** University-managed Windows laptops sometimes
**disable ICS by group policy**. With live installs on the critical path, an
affected student is stuck. Needs a fallback plan (a spare Mac? a pre-baked image?)
decided before the workshop, not during it.

### To verify on the Windows desktop

1. Does ICS actually give a DHCP-client Jetson internet out of the box?
2. Does `ssh jetson@jetson-2gnano.local` resolve? (Windows 10 1703+ has native
   mDNS, but confirm — it's the whole handout.)
3. Is the firewall rule really needed for the relay, and does that command work?
4. Can the checks in `setup-internet-sharing-macos.sh` be ported to PowerShell?
   `ipconfig`, `arp -a`, `Get-NetIPAddress`, `Test-NetConnection` are the analogues.
