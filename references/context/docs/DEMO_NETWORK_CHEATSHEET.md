# Demo-Day Network Cheat Sheet (Jetson client + Laptop relay)

**Fixed addresses — the course image already bakes these in. No IP discovery, no DHCP, no ICS.**

```
  Jetson  = 192.168.1.100   (static, in the flashed image — do NOT change)
  Laptop  = 192.168.1.13    (set static on the Jetson-facing Ethernet)
  Relay URL on the Jetson:   http://192.168.1.13:8000
  SSH into the Jetson:       ssh jetson@192.168.1.100
```

Everyone in the room uses these SAME two IPs. The Jetson connects TO the laptop,
so the only thing each student configures is their laptop's static IP.

> ⚠️ Do NOT turn on Internet Connection Sharing (ICS). It renumbers the laptop to
> `192.168.137.1` and breaks the fixed scheme (this is what broke things before).
> The Jetson needs no internet — its dependencies are already in the image.

---

## One-time per laptop: set the static IP on the Jetson-facing Ethernet

GUI (no admin script needed):
1. Win+R → `ncpa.cpl` → Enter.
2. Right-click the **Ethernet adapter the Jetson cable plugs into** → Properties.
3. Select **Internet Protocol Version 4 (TCP/IPv4)** → Properties.
4. **Use the following IP address:**
   - IP address: `192.168.1.13`
   - Subnet mask: `255.255.255.0`
   - Default gateway: **blank**   (internet stays on Wi-Fi / the other adapter)
   - DNS: **blank**
5. OK.

Or in an **Administrator** PowerShell:
```powershell
New-NetIPAddress -InterfaceAlias "乙太網路 3" -IPAddress 192.168.1.13 -PrefixLength 24
```
(replace `乙太網路 3` with your Jetson-facing adapter name from `ipconfig`.)

---

## Open the firewall + start the relay (on the laptop)

```powershell
# firewall, once (Administrator PowerShell):
New-NetFirewallRule -DisplayName "Relay 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow

# relay (leave running):
uvicorn relay_server:app --host 0.0.0.0 --port 8000
curl.exe http://localhost:8000/health          # -> {"ok":true}
```

---

## Run the demo (100% headless)

From the **laptop**:
```powershell
ssh jetson@192.168.1.100
```
Then on the **Jetson**:
```bash
wget -qO- http://192.168.1.13:8000/health       # -> {"ok":true}  (confirms the link)
export RELAY_URL="http://192.168.1.13:8000"
SENSOR=webcam python3 webcam_selftest.py         # wave = motion, clap = loud
SENSOR=webcam python3 mode2_edge.py              # the main demo (edge features)
SENSOR=webcam python3 mode1_streamer.py          # raw stream (CPU/bandwidth cost)
```
If the USB webcam isn't found: `ls /dev/video*` then `export CAMERA_INDEX=1`.

---

## Audio (C270 mic) — needed for live fall detection on the Jetson

The Jetson opens the *default* mic, which is the silent onboard codec — not the
C270 webcam mic. If `webcam_selftest.py` shows `audio_rms 0.0000`, point
PulseAudio's default source at the C270 (run once per login, or add to
`~/.bashrc`). Same command for every student (C270s share this name):
```bash
pactl set-default-source alsa_input.usb-046d_C270_HD_WEBCAM_200901010001-02.analog-mono
```
Then `SENSOR=webcam python3 webcam_selftest.py` → clap → `loud?` = True.
(If your `pactl list short sources` shows a slightly different name, use that one.)

Required Jetson packages (already installed on the prepped unit; no internet on
the demo cable, so do these ahead of time via Wi-Fi): `requests` (pip),
`sounddevice` (pip), and `libportaudio2` (apt). `cv2`/`numpy` come with JetPack.
Without audio the demo still runs video-only, and `compare.py` still shows falls.

---

## If it won't connect — check in this order

1. **Laptop on the right IP?** `ipconfig` → the Jetson-facing adapter must be
   `192.168.1.13` (NOT `192.168.137.x` — if you see that, ICS is still on: turn it
   off in `ncpa.cpl` and re-set the static IP).
2. **Reach the Jetson?** `ping 192.168.1.100` from the laptop.
3. **Relay running?** `curl.exe http://localhost:8000/health`.
4. **Firewall?** Inbound TCP 8000 allowed (rule above).
5. **From the Jetson:** `wget -qO- http://192.168.1.13:8000/health`. Fails =
   cable / IP / subnet, not the app.

---

## Recovering a laptop still stuck in ICS (192.168.137.1)

1. `ncpa.cpl` → right-click the adapter with Sharing enabled → Properties →
   **Sharing** tab → **uncheck** the box → OK.
2. Administrator PowerShell:
   ```powershell
   Remove-NetIPAddress -InterfaceAlias "乙太網路 3" -IPAddress 192.168.137.1 -Confirm:$false
   New-NetIPAddress -InterfaceAlias "乙太網路 3" -IPAddress 192.168.1.13 -PrefixLength 24
   Test-Connection 192.168.1.100 -Count 2       # should succeed
   ```

---

## No internet on the Jetson — installing deps (do this OFF the demo network)

The Jetson has no internet on the demo cable, and the image can't be re-flashed.
If a package is genuinely missing (check first: `python3 -c "import requests, cv2, numpy"`),
install it by temporarily giving that ONE Jetson internet another way — e.g. move
its Ethernet to a router with internet, or a USB Wi-Fi dongle — run the install,
then move it back to the demo cable. `sounddevice` is optional (video-only without
it); `requests`, `cv2`, `numpy` are the ones that matter and are usually already
in the course image.
