# Jetson Nano Setup Guide — Edge Sensing Workshop

End-to-end setup for running the workshop on a **Jetson Nano (edge client)** talking
to a **laptop (relay / "cloud")**. Written from a real setup session, including the
mistakes and how to avoid them.

---

## 0. The setup at a glance

```
   ┌─────────────────┐        Ethernet          ┌──────────────────┐
   │  Jetson Nano    │  ────────────────────►   │  Laptop (relay)  │
   │  192.168.1.100  │   feature vectors /      │  192.168.1.13    │
   │  (edge client)  │   raw frames over HTTP   │  uvicorn :8000   │
   └─────────────────┘                          └──────────────────┘
        USB C270 webcam+mic                          Wi-Fi / 2nd NIC → internet
```

- **Jetson = `192.168.1.100`** — a **static IP baked into the course image** (don't change it).
- **Laptop = your own IP** — check it with `ipconfig` on the Jetson-facing Ethernet
  (see §4a). It differs per laptop; the examples below use `192.168.1.13` as a stand-in
  for `<LAPTOP-IP>`.
- The **Jetson connects TO the laptop**, so the one address you look up and type is
  your laptop's: `RELAY_URL=http://<LAPTOP-IP>:8000`.
- Only the laptop IP varies; the Jetson's `192.168.1.100` is the same for everyone.
  Your laptop must be on the **same `192.168.1.x` network** as the Jetson (normally it is).

> **Roles are reversed from the generic manual.** Here the *laptop* is the relay/server
> and the *Jetson* is the client. The Jetson never needs a display — access it over SSH:
> `ssh jetson@192.168.1.100`.

**Golden rule:** the Jetson needs the internet **only once**, to install
dependencies (§1–§2). The demo itself (§4–§6) needs **no internet** on the Jetson.
Do all installs ahead of time.

---

## 1. Give the Jetson internet (one time, for installs only)

The demo cable (Jetson↔laptop) has **no internet**. To `pip install`, give the
Jetson internet by ONE of the two methods below. **Wi-Fi dongle (1b) is
recommended** — it doesn't disturb the demo network. ICS (1a) is included for
completeness but has side effects.

### 1a. Internet Connection Sharing (ICS) — NOT recommended for headless

Shares the laptop's internet down the Ethernet cable to the Jetson.

1. Press **Win+R**, type `ncpa.cpl`, Enter (Network Connections).
2. Right-click **乙太網路 2** (the *internet* adapter, `192.168.50.216`) →
   **Properties** → **Sharing** tab.
3. Check **"Allow other network users to connect through this computer's Internet
   connection."**
4. If a dropdown ("Home networking connection") appears, select **乙太網路 3** (the
   Jetson side). Click **OK**.

> ⚠️ **Critical side effect:** ICS **forces the shared adapter (Ethernet 3) to
> `192.168.137.1`**. After enabling it:
> - The Jetson gets a new `192.168.137.x` address from the PC's built-in ICS DHCP.
> - The relay address **changes** → `RELAY_URL=http://192.168.137.1:8000` (no longer
>   `192.168.1.13`).
> - **You lose SSH** until the Jetson renews its lease, and finding the Jetson's new
>   IP headlessly is painful — this is why ICS needs a display/serial console.
>   **For a 100% headless classroom, use 1b instead.**

On the Jetson (needs console/serial access), renew the lease to join the new network:
```bash
sudo dhclient -r eth0 && sudo dhclient eth0
#   or: sudo nmcli device disconnect eth0 && sudo nmcli device connect eth0
ping -c 3 8.8.8.8          # internet routing
ping -c 3 pypi.org         # DNS + internet
```
**Turn ICS OFF after installing** (uncheck the box) and restore the laptop to
`192.168.1.13` (see §7) before the demo.

### 1b. Wi-Fi dongle — recommended (keeps SSH + demo link intact)

A USB Wi-Fi dongle adds a separate `wlan0` interface. Because it's separate from
`eth0`, **your SSH session over Ethernet stays alive** the whole time.

```bash
# 1. Confirm the dongle is detected:
nmcli device                          # look for a line: wlan0 ... wifi
#    (no wifi line = driver missing; note the dongle chipset and install its driver)

# 2. Turn on the radio and scan:
nmcli radio wifi on
nmcli device wifi list

# 3. Connect:
sudo nmcli device wifi connect "YOUR_SSID" password "YOUR_PASSWORD"

# 4. Test internet:
ping -c 3 8.8.8.8
ping -c 3 pypi.org
```

**If Wi-Fi connects but internet still fails** ("Destination Host Unreachable" /
"Network is unreachable"), you have **two default routes** and the Ethernet one is
winning. Check with `ip route` — you'll see something like:
```
default via 192.168.1.1 dev eth0 onlink               ← wrong (metric 0, wins)
default via 192.168.51.1 dev wlan0 proto dhcp metric 600
```
Fix — remove the Ethernet default route so Wi-Fi becomes the internet path
(this does **not** drop SSH or the relay link — those use the same-subnet local
route, not the default route):
```bash
sudo ip route del default via 192.168.1.1 dev eth0
ip route                       # 'default' should now be ONLY via wlan0
ping -c 3 8.8.8.8              # should work now
```

> If `eth0` is managed by NetworkManager (`nmcli device` shows it as *not*
> "unmanaged"), you can instead tell it never to be the default route:
> ```bash
> sudo nmcli connection modify "Wired connection 1" ipv4.never-default yes ipv4.gateway ""
> sudo nmcli connection up "Wired connection 1"
> ```
> If `eth0` shows **unmanaged**, use the `ip route del` command above instead
> (nmcli can't modify an unmanaged interface).

---

## 2. Install dependencies (while the Jetson has internet)

`cv2` and `numpy` already come with JetPack. You only add three things:

```bash
pip3 install requests sounddevice
sudo apt-get install -y --no-install-recommends libportaudio2
```

- **`requests`** (pip) — required; the client POSTs to the relay with it.
- **`sounddevice`** (pip) — the Python mic wrapper. Optional (video-only without it),
  but needed for live fall detection.
- **`libportaudio2`** (apt) — the C library `sounddevice` needs to reach the mic.
  `--no-install-recommends` keeps it minimal so it won't disturb the image.

> These install to the *user* directory (`~/.local`) — they do **not** modify the
> system/custom image. Safe and reversible (`pip3 uninstall ...`).

**Verify:**
```bash
python3 -c "import requests; print('requests', requests.__version__)"
python3 -c "import sounddevice; print('sounddevice OK')"
python3 -c "import sounddevice; print(sounddevice.query_devices())"   # lists audio devices
python3 -c "import cv2, numpy; print(cv2.__version__, numpy.__version__)"
```
Expected: version strings and a device list. If `import sounddevice` raises
`OSError: PortAudio library not found`, the `libportaudio2` apt step didn't run.

Once installs are done you can disconnect Wi-Fi (`nmcli device disconnect wlan0`) —
the demo doesn't need it.

---

## 3. Transfer the code to the Jetson (SCP, from the laptop)

Run on the **laptop** (it must be able to `ping 192.168.1.100`, i.e. on the same
`192.168.1.x` network as the Jetson — see §4/§7 first if not):
```powershell
cd "c:\Users\fred\Downloads\files\edge-workshop-camera-en"
ssh jetson@192.168.1.100 "mkdir -p ~/EDGE-CAMERA"
scp *.py jetson@192.168.1.100:~/EDGE-CAMERA/
```
`scp.exe` ships with Windows' OpenSSH client (same as `ssh`). It'll prompt for the
Jetson password.

**Verify on the Jetson:**
```bash
ls -la ~/EDGE-CAMERA/*.py
grep MOTION_LEVEL_THRESH ~/EDGE-CAMERA/common.py     # must show 0.006 (the default)
```

> ⚠️ **Watch the threshold.** `common.py`'s `MOTION_LEVEL_THRESH` must be **`0.006`**.
> If it's higher (e.g. `0.05` or `0.1`), `compare.py` fails with **motion 4/12,
> falls 0/2** and live motion won't register — that's the "raised threshold"
> classroom exercise, not a bug. Fix it in the laptop copy and re-`scp`.

---

## 4. Network for the demo + start the relay

### 4a. Find your laptop's IP (this is the relay address)

The Jetson connects to your laptop, so look up your laptop's IP on the Jetson-facing
Ethernet:
```powershell
ipconfig
```
Read the **IPv4 Address** of the Ethernet adapter the Jetson cable plugs into
(e.g. `192.168.1.13`). Use that value wherever the steps below show `<LAPTOP-IP>`.

It should be on the **same `192.168.1.x` network as the Jetson** (`192.168.1.100`).
If instead you see `192.168.137.x`, ICS is still on from an earlier step — turn it
off and re-check (see §7).

### 4b. Open the firewall (once, Administrator PowerShell)
```powershell
New-NetFirewallRule -DisplayName "Relay 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
```

### 4c. Start the relay (leave running)
```powershell
uvicorn relay_server:app --host 0.0.0.0 --port 8000
curl.exe http://localhost:8000/health          # -> {"ok":true}
```
`--host 0.0.0.0` is required so the Jetson (a different machine) can reach it.

### 4d. Test the link from the Jetson
```bash
wget -qO- http://<LAPTOP-IP>:8000/health         # -> {"ok":true}  (use your IP from 4a)
```
`{"ok":true}` = the whole Jetson→laptop path works.

---

## 5. Fix the microphone (C270 webcam mic)

The Jetson opens the **default** audio input, which is the silent onboard `tegra`
codec — **not** the C270's mic. Symptom in `webcam_selftest.py`: `audio_rms 0.0000`
and `loud?` never True.

Find the C270 source and make it the default:
```bash
pactl list short sources
#  look for the C270, e.g.:
#  0   alsa_input.usb-046d_C270_HD_WEBCAM_200901010001-02.analog-mono   ...
pactl set-default-source alsa_input.usb-046d_C270_HD_WEBCAM_200901010001-02.analog-mono
```
Re-test:
```bash
SENSOR=webcam python3 webcam_selftest.py         # clap → loud? should turn True
```

> - The C270 mic runs at 48 kHz; PulseAudio resamples to the code's 16 kHz
>   automatically (we go through the `default`→`pulse` path).
> - The source name is the **same for every C270** (Logitech ships the generic serial
>   `200901010001`), so the exact command works for all students.
> - `pactl set-default-source` resets on reboot. To make it stick, add the line to
>   `~/.bashrc` or a small `setup_audio.sh`, or put it in your demo runbook.
> - No mic / don't care about live falls? Skip this — the demo runs video-only and
>   `compare.py` still shows falls (synthetic scene, no mic needed).

---

## 6. Run the demo

**On the laptop:** relay running (§4c). **SSH into the Jetson** and run:
```bash
cd ~/EDGE-CAMERA
pactl set-default-source alsa_input.usb-046d_C270_HD_WEBCAM_200901010001-02.analog-mono
export RELAY_URL="http://<LAPTOP-IP>:8000"        # <LAPTOP-IP> = your laptop's IP (§4a)

# sanity checks
wget -qO- http://<LAPTOP-IP>:8000/health          # {"ok":true}
python3 compare.py                                # 12/12 motion, 2/2 falls, ~689x
SENSOR=webcam python3 webcam_selftest.py          # wave = motion, clap = loud

# the workshop itself
SENSOR=webcam python3 mode2_edge.py               # edge features → tiny upload (the point)
SENSOR=webcam python3 mode1_streamer.py           # raw stream → heavy upload (contrast)
```
Camera not found? `ls /dev/video*` then `export CAMERA_INDEX=1` (or 2).

---

## 7. Recovery: laptop stuck at `192.168.137.1` (leftover ICS)

If you used ICS and the laptop can't reach the Jetson (`ping 192.168.1.100` fails,
`ipconfig` shows `192.168.137.1`):

1. `ncpa.cpl` → right-click the adapter with Sharing enabled → Properties →
   **Sharing** tab → **uncheck** the box → OK.
2. The adapter should return to its normal `192.168.1.x` address. Re-check and
   confirm you can reach the Jetson:
   ```powershell
   ipconfig                                     # note the Ethernet IPv4 (your <LAPTOP-IP>)
   Test-Connection 192.168.1.100 -Count 2       # should succeed
   ```
3. If it's still stuck on `192.168.137.1`, clear the leftover ICS address and renew
   (Administrator PowerShell):
   ```powershell
   Remove-NetIPAddress -InterfaceAlias "乙太網路 3" -IPAddress 192.168.137.1 -Confirm:$false
   ipconfig /renew
   ```

---

## 8. Troubleshooting quick reference

| Symptom | Cause | Fix |
|---|---|---|
| `ping 192.168.1.100` fails from laptop | Laptop off the `192.168.1.x` subnet (ICS?) | §7 — confirm laptop is on `192.168.1.x` via `ipconfig` |
| Jetson `wget .../health` fails | Relay down / firewall / wrong IP | §4a–§4d; recheck `<LAPTOP-IP>` with `ipconfig` |
| `pip3` "Network is unreachable" | Jetson has no internet route | §1b default-route fix (`ip route del …`) |
| `OSError: PortAudio library not found` | `libportaudio2` missing | `sudo apt-get install -y libportaudio2` |
| `audio_rms 0.0000`, `loud?` never True | Default mic = silent onboard codec | §5 — `pactl set-default-source` to the C270 |
| `compare.py`: motion 4/12, falls 0/2 | `MOTION_LEVEL_THRESH` too high | set it back to `0.006` in `common.py`, re-`scp` |
| Camera won't open | Wrong index / in use | `export CAMERA_INDEX=1`; `ls /dev/video*` |
| SSH drops right after enabling ICS | ICS renumbered the subnet | §1a note; prefer Wi-Fi dongle (§1b) |

---

## 9. Key values for this course (put on the whiteboard)

| Item | Value |
|---|---|
| Jetson IP (in image) | `192.168.1.100` (same for everyone) |
| Laptop / relay IP | **your own** — find with `ipconfig` (e.g. `192.168.1.13`) |
| Relay URL (on Jetson) | `http://<LAPTOP-IP>:8000` |
| SSH | `ssh jetson@192.168.1.100` |
| Code folder on Jetson | `~/EDGE-CAMERA` |
| Mic source | `alsa_input.usb-046d_C270_HD_WEBCAM_200901010001-02.analog-mono` |
| Motion threshold | `MOTION_LEVEL_THRESH = 0.006` |
