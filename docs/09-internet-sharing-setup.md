# 09 — Internet Sharing: Laptop → Jetson (runbook)

> **What this solves.** The Jetson has **no Wi-Fi** and the lab Wi-Fi uses
> **client isolation** (devices can't talk to each other). So the only link
> between a student's laptop and their Jetson is the **LAN cable**, and the only
> way the Jetson reaches the internet is the laptop **sharing** its Wi-Fi down
> that cable. Students install libraries live during the workshop, so this is on
> the critical path — not a nice-to-have.

**This file is the steps, and nothing else.** Every gotcha, finding, hardware
measurement and design rationale lives in
[`10-internet-sharing-findings.md`](10-internet-sharing-findings.md). If a step
here surprises you, breaks, or looks arbitrary, the reason is in there.

| | |
|---|---|
| **Workshop laptops** | Windows-only (decided 2026-07-16) |
| **Jetson address** | static `192.168.137.100` |
| **Student command** | `ssh jetson@192.168.137.100` |
| **Verified** | **end-to-end on hardware, 2026-07-16** — laptop ICS *and* the Jetson static image, routing and DNS both confirmed after a real reboot |

---

## Pick your path

| Your laptop | Script | Jetson image must be | Status |
|---|---|---|---|
| **Windows** | `scripts\setup-internet-sharing-windows.ps1` | static `192.168.137.100` | **this is the current image** |
| **macOS** | `scripts/setup-internet-sharing-macos.sh` | DHCP | needs [reverting the image](10-internet-sharing-findings.md#the-rejected-alternative-dhcp) first |

Both scripts are **laptop-side only** — neither touches the Jetson.

A Jetson baked for one OS **cannot** be reached from the other, and no
laptop-side script can fix that; the image itself has to change. Why:
[the trade](10-internet-sharing-findings.md#the-one-idea-that-makes-this-work).

---

## Windows — the student flow

1. Connect to lab Wi-Fi.
2. Plug in the USB-ethernet dongle (**or** use the laptop's built-in LAN port),
   run the LAN cable to the Jetson, power the Jetson on. Give it ~40 seconds.
3. Open **PowerShell as Administrator** — Start → type `PowerShell` →
   right-click → **Run as administrator** — and run:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\setup-internet-sharing-windows.ps1
   ```

4. `ssh jetson@192.168.137.100`

Admin is **required**: ICS and firewall rules both need it. Add `-CheckOnly` to
diagnose without changing anything — but it still needs admin to see past step 2,
because the ICS COM API returns nothing unelevated.

What the script does, in order, stopping at the first failure with a specific fix:

1. Confirms your Wi-Fi is up and actually has internet.
2. Finds the Jetson's cable by **what it is** — the only wired adapter with link
   — never by name.
3. Enables ICS from Wi-Fi → that adapter, repairing a half-configured ICS if it
   finds one.
4. Adds the relay firewall rule (TCP 8000 inbound).
5. Waits for the Jetson to answer on port 22 at `192.168.137.100`.

### GUI equivalent (Windows)

If you'd rather click, or the script fails:

1. `Win+R` → **`ncpa.cpl`**
2. Right-click **Wi-Fi** → **Properties** → **Sharing** tab
3. Tick *"Allow other network users to connect…"*
4. **Home networking connection** → pick your Jetson's adapter. It's the one
   whose grey subtitle names your dongle, or the one that appears/disappears when
   you unplug it. **Do not trust the `Ethernet N` number** —
   [it is a per-laptop artifact](10-internet-sharing-findings.md#adapter-names-are-per-laptop-and-must-never-be-hardcoded).
5. **OK**

Then add the relay rule in an admin prompt:

```
netsh advfirewall firewall add rule name="Workshop Relay 8000" dir=in action=allow protocol=TCP localport=8000
```

To repoint an existing share: untick → **OK** → reopen → re-tick → choose the
right adapter.

> **Never hand-edit IPv4 on the shared adapter.** ICS owns that address and
> assigns `192.168.137.1` itself. Setting it manually — or ticking *"Obtain an IP
> address automatically"* — silently breaks sharing while still showing the box
> ticked. The repair is always the sharing off/on toggle, never an IP edit. See
> [ICS can be "on" and still not working](10-internet-sharing-findings.md#ics-can-be-on-and-still-not-working).

---

## macOS — the student flow

> **Prerequisite: the Jetson must be on the DHCP image.** The current image is
> pinned to `192.168.137.100` and a Mac cannot reach it at all. Revert it first —
> see [the rejected alternative](10-internet-sharing-findings.md#the-rejected-alternative-dhcp).

1. Connect to lab Wi-Fi.
2. Plug the USB-ethernet adapter into the Mac, run the LAN cable to the Jetson,
   power the Jetson on.
3. **System Settings → General → Sharing → Internet Sharing**: share **from
   Wi-Fi**, **to** your USB adapter. Toggle **ON**.
4. Run the checker:

   ```bash
   bash scripts/setup-internet-sharing-macos.sh
   ```

5. `ssh jetson@jetson-2gnano.local`

The macOS script is **read-only** — it enables nothing, because macOS has no
supported CLI for Internet Sharing. It checks each layer in dependency order and
names whatever is broken.
[Why the two scripts differ](10-internet-sharing-findings.md#why-the-windows-script-writes-and-the-macos-one-doesnt).

---

## Jetson-side config

Done **once, by the instructor, before cloning** the student image. Students never
do this.

`eth0` is managed by **ifupdown** (`/etc/network/interfaces`), **not**
NetworkManager — `nmcli` commands for `eth0` appear to succeed and do nothing.

`/etc/network/interfaces`:

```
auto eth0
iface eth0 inet static
address 192.168.137.100
netmask 255.255.255.0
gateway 192.168.137.1
dns-nameservers 192.168.137.1
```

The `gateway` line is what gives the Jetson internet — nothing hands one out
anymore. To apply it, over SSH:

```bash
sudo cp /etc/network/interfaces /etc/network/interfaces.bak
sudo nano /etc/network/interfaces      # make it match the block above
cat /etc/network/interfaces            # read it back before committing
sudo rm -f /var/lib/dhcp/dhclient*.leases
sudo reboot
```

Keep the `.bak`. If the Jetson doesn't come back, restoring it needs a monitor and
keyboard on the device.

### Before cloning the student image

```bash
sudo rm -f /var/lib/dhcp/dhclient*.leases
```

Hygiene only under the static image, since `dhclient` never runs — but
**mandatory** if you ever revert to DHCP. See
[the landmine](10-internet-sharing-findings.md#the-landmine-that-dhcp-carries-and-why-it-bit-us).

Already true of the image, and worth not breaking:

- `isc-dhcp-server` is **disabled**. It bound *every* interface, so it would
  become a rogue DHCP server on the lab Wi-Fi if the Jetson ever joined it.
- `eth0:1` (the old `192.168.1.100` fallback) is **removed**.
- Hostname is `jetson-2gNANO` — a 4GB board despite the name, kept deliberately.

---

## Verify it worked

The Windows script's last step covers the laptop side. On the Jetson:

```bash
ip route                # want: default via 192.168.137.1
ping -c2 8.8.8.8        # routing
ping -c2 google.com     # DNS
```

**`ping 8.8.8.8` is the one that matters.** SSH, gateway ping and DNS can all
succeed while routing is dead — that combination is a known fingerprint, not a
sign of health. See
[the landmine](10-internet-sharing-findings.md#the-landmine-that-dhcp-carries-and-why-it-bit-us).

Captured on hardware after a real reboot (2026-07-16) — this is what a healthy
Jetson looks like:

```
$ ip -4 addr show eth0 | grep inet
    inet 192.168.137.100/24 brd 192.168.137.255 scope global eth0   <- and nothing else

$ ip route | awk '/^default/{print $3}'
192.168.137.1

$ ping -c2 8.8.8.8
2 packets transmitted, 2 received, 0% packet loss     rtt avg 8.371 ms

$ ping -c2 google.com
2 packets transmitted, 2 received, 0% packet loss

$ pgrep -a dhclient
(nothing — correct; dhclient must never run)
```

> **On DNS, if you go looking.** This image runs **systemd-resolved**, so
> `/etc/resolv.conf` is a symlink to `/run/resolvconf/resolv.conf` and lists
> **both** `nameserver 192.168.137.1` and `nameserver 127.0.0.53` (the stub). Both
> lines are correct — the stub is not a fault. `systemd-resolve --status` shows the
> real upstream as `192.168.137.1`. Verified working.

---

## When it breaks

| Symptom | What to do |
|---|---|
| **It worked, now it doesn't** | Sharing turns itself off after sleep or reboot. **Re-run the script first** — this is the most common one. |
| Script says `ICS returned no connections` | You aren't elevated. Re-run as Administrator. |
| Sharing is on, Jetson has no internet | [findings](10-internet-sharing-findings.md#internet-sharing-is-on-but-the-jetson-has-no-internet) |
| Sharing looks on but nothing reaches the Jetson | [ICS half-configured](10-internet-sharing-findings.md#ics-can-be-on-and-still-not-working) |
| Plugging in the cable kills my Wi-Fi | [findings](10-internet-sharing-findings.md#plugging-in-the-cable-kills-my-wi-fi) |
| Need to reach the Jetson with sharing off | [findings](10-internet-sharing-findings.md#reaching-the-jetson-when-sharing-is-off) |

> **Open risk, no workaround.** University-managed Windows laptops sometimes
> **disable ICS by group policy**. Untested — the dev laptop is unmanaged. With
> live installs on the critical path, an affected student is stuck. A fallback
> plan (a spare laptop? a pre-baked image?) still needs deciding before the
> workshop.
