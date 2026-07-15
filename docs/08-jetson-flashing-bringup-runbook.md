# 08 — Jetson Nano Bring-up & Flashing Runbook (Ubuntu 18.04 host)

> **Read me first if you are working on the Ubuntu 18.04 laptop.** This file is
> self-contained on purpose: the project's working notes live on a *different*
> machine (a Mac) and are **not** available here. Everything you need to continue
> the Jetson bring-up is below.
> For the broader workshop project (what the code does, the Jetson end-goal), read
> `docs/01`–`07` — but that is background; **the active task is getting one Jetson
> Nano 4GB to boot.**

---

## TL;DR — current state (2026-07-15)

A Jetson Nano 4GB dev kit **hangs at the NVIDIA splash logo and never reaches
login.** The custom SD image is known-good (it boots on another, identical 4GB
board). So the image is *not* the problem — this specific unit is. Prime suspects,
in order: **(1) the module's QSPI bootloader** (corrupt or version-mismatched vs
the SD), **(2) a marginal microSD card**, **(3) power.** The plan is: **read the
serial console to see exactly where boot dies → then apply the matching fix**
(recovery-mode `flash.sh` if it's a bootloader-stage hang; a re-flash/new card if
it's an SD/kernel-stage hang).

Why Ubuntu 18.04 matters: NVIDIA's recovery-mode flashing tools (**SDK Manager /
`flash.sh`, L4T R32.7.x**) for the original Jetson Nano run on an **x86_64 Ubuntu
18.04 host**. This laptop is that host.

---

## Hardware & artifacts (facts established with the user)

| Item | Value |
|---|---|
| Target board | **Jetson Nano 4GB Developer Kit** (original Maxwell Nano, *not* Orin) |
| Reference board | A **friend's second Nano 4GB** boots the **same** image to login — proves the image is 4GB-compatible |
| Custom image | `references/context/Jetson2G_SEA_APRILTAG_250422.img` — **50 GB raw GPT microSD clone** (full `dd`-style image, not compressed, not a BSP). Filename says "2G"; payload is a **SEA / AprilTag** setup that looks **unrelated to the edge-sensing camera workshop** (that workshop is just Python + OpenCV). |
| microSD used | 128 GB card, written with **balenaEtcher** (Etcher validated the write) |
| Flash method used | Etcher raw write → boots → **stuck at NVIDIA logo** |
| Serial adapter | User **has a USB-to-TTL (3.3 V) adapter** for console debugging |
| Debug link tried | Mac ↔ Jetson direct Ethernet cable (see LAN test below) |

---

## The problem & how far diagnosis has gone

**Symptom:** powers on, shows the NVIDIA logo, **never reaches a login prompt.**

**What is RULED OUT:**
- ❌ *"2 GB image on a 4 GB board" device-tree mismatch.* Disproven — the identical
  image boots on another 4 GB board.
- ❌ *"It booted fine, only the display/HDMI is dead" (headless-OK).* Disproven by a
  LAN reachability test: on a direct cable, an IPv6 all-nodes ping (`ping6 ff02::1`)
  got **no reply from the Jetson** (only the host's own interface answered). An IPv6
  link-local address comes up on **any** booted Linux NIC regardless of DHCP, so
  silence means **the OS never finished booting.** This is a **true boot hang**, not
  a display problem — running it headless will not rescue it.

**What is SUSPECTED (this specific unit):**
1. **QSPI bootloader.** On the Nano, the **NVIDIA splash is drawn by CBoot**, the
   bootloader stored in the module's **QSPI-NOR** (B01 modules have QSPI; the SD
   dev-kit module has no eMMC but does carry QSPI boot firmware). CBoot then loads
   the kernel from the SD's APP partition. **A hang *at the logo* = stuck at/after
   CBoot.** A corrupt QSPI, or a QSPI bootloader whose version doesn't match the
   kernel on the SD, produces exactly this. **Etcher cannot fix QSPI; recovery-mode
   `flash.sh` can.** This is the leading hypothesis and the one recovery-flashing is
   the right tool for.
2. **Marginal 128 GB card.** Etcher can validate a write yet the card still faults
   at runtime (cheap/counterfeit/worn cards are the #1 Nano-won't-boot cause).
3. **Power.** Under-powered supply (micro-USB vs barrel jack) can stall boot; use
   the **barrel jack + the J48 jumper** for a stable 4 A.

---

## Action plan (do in this order)

### Step 1 — Read the serial console (do this FIRST; it decides everything)

"Stuck at the logo" has different fixes depending on the exact stall point. The
console shows it in one boot. **You have the adapter — this is 5 minutes.**

**Wiring (3 wires):** `GND↔GND`, `Jetson TX→adapter RX`, `Jetson RX→adapter TX`.
**Do not connect VCC/3.3 V.** The debug UART is the dedicated header (labeled `J44`
on most carriers, near the module — *not* the 40-pin GPIO header). A02 vs B01 pin
numbers differ slightly — confirm against JetsonHacks *"Jetson Nano – Serial
Console."* If you see nothing, **swap the two data wires** (harmless, usual fix).

**On this Ubuntu host:**
```bash
# find the adapter (FTDI/CP210x/CH340 all enumerate as ttyUSB*)
dmesg | grep -i tty | tail
ls /dev/ttyUSB*

# open at 115200 8N1 with a log file (sudo, or add yourself to the dialout group)
sudo apt-get install -y minicom            # if not present
sudo minicom -D /dev/ttyUSB0 -b 115200 -C jetson-boot.log
# --- or with screen ---
sudo screen -L /dev/ttyUSB0 115200         # logs to screenlog.0 ; quit: Ctrl-A then K
```
Start the terminal **first**, then power-cycle the Jetson so you capture from the
first line. Let it sit at the frozen logo ~30 s, then save/paste the log.

**Interpretation — where it freezes tells you the fix:**

| Freezes at… | Meaning | Fix |
|---|---|---|
| A few chars, or `MB1`/`MB2`/`CBoot` before "Loading kernel" | **QSPI bootloader** corrupt or version-mismatched | **Step 3 — recovery-mode `flash.sh`** (rewrites QSPI) |
| `Starting kernel …` then silence | Bootloader OK; kernel/SD handoff fails | **Step 2** — re-flash SD / suspect the card |
| Kernel logs scroll, then `Unable to mount root fs`, `mmcblk0` or `EXT4-fs` errors | **SD card read failure** | New card, re-flash |
| Reaches `systemd`, hangs on a service | Userspace / first-boot config | Fixable in place — capture which unit |

### Step 2 — Cheap isolation tests (parallel, no tools needed)

- **SD swap (30 s, most decisive):** put the friend's **working** card into this
  board. Boots → this board's SD *content* was the issue. Still hangs → this
  **board** (very likely its QSPI) → go to Step 3. Also try **this** card in the
  friend's board: boots there → card is fine; hangs → **card is bad**.
- **Stock-image sanity flash:** Etcher the **official NVIDIA JetPack 4.6.x Jetson
  Nano (4GB) SD image** to a card and boot. Boots → board+power healthy, problem was
  the custom SD/QSPI pairing. Hangs the same way → board/QSPI/power, go to Step 3.
- **Power:** use the **barrel jack + J48 jumper** (not micro-USB) before drawing
  conclusions.

> Note whether the 128 GB card is the *same* card the friend flashed successfully or
> a different one — if different, the card jumps up the suspect list.

### Step 3 — Recovery-mode flash (only if Step 1/2 point at the bootloader)

This reflashes the **QSPI bootloader + SD** from NVIDIA's L4T package, which is the
one thing Etcher can't do. **Two caveats up front:**
- **It cannot ingest the 50 GB `Jetson2G_…img` directly.** `flash.sh`/SDK Manager
  consume NVIDIA's **L4T BSP directory** (`Linux_for_Tegra/` + a `rootfs/`), not a
  finished SD clone.
- **A plain recovery flash installs NVIDIA's *stock* rootfs — it wipes the custom
  SEA/AprilTag software.** If you don't actually need that payload (it looks
  unrelated to the workshop), this is fine and is the clean path to a known-good
  board.

**Procedure (original Nano SD dev kit, L4T R32.7.x / JetPack 4.6.x — verify exact
version strings against NVIDIA's current Nano L4T download page):**
```bash
# 1) On the Ubuntu 18.04 host, download for "Jetson Nano" (Jetson-210 / t210):
#    - L4T Driver Package (BSP):        Jetson-210_Linux_R32.7.x_aarch64.tbz2
#    - Sample Root Filesystem:          Tegra_Linux_Sample-Root-Filesystem_R32.7.x_aarch64.tbz2

# 2) Assemble the BSP tree
tar xf Jetson-210_Linux_R32.7.x_aarch64.tbz2          # -> Linux_for_Tegra/
sudo tar xpf Tegra_Linux_Sample-Root-Filesystem_R32.7.x_aarch64.tbz2 \
     -C Linux_for_Tegra/rootfs/
cd Linux_for_Tegra
sudo ./apply_binaries.sh

# 3) Put the Nano in FORCE RECOVERY: power OFF, short the header pins labeled
#    [FC REC] and [GND] on the carrier's button header (silkscreen; A02 vs B01
#    differ — see JetsonHacks "force recovery mode"), connect the micro-USB to this
#    laptop, then power ON. Confirm it enumerated:
lsusb | grep -i "0955"      # NVIDIA Corp 0955:7f21 == in recovery mode

# 4) Insert the target microSD into the Nano, then flash bootloader(QSPI)+rootfs(SD):
sudo ./flash.sh jetson-nano-qspi-sd mmcblk0p1
#    ~10–20 min. Then remove the recovery jumper and reboot.
```

**Keeping the custom software (advanced, optional):** to reflash the *bootloader*
while preserving the SEA/AprilTag rootfs, extract that rootfs from the `.img`'s
ext4 **APP** partition into `Linux_for_Tegra/rootfs/` before `apply_binaries.sh`,
or flash stock to fix QSPI first and then re-Etcher the custom SD image and see if
the now-updated QSPI boots it (tests the version-mismatch theory directly).

### Step 4 — If the goal is just the workshop, not this image

For the edge-sensing workshop itself you likely **don't need the custom image at
all**: flash **stock JetPack 4GB** (Etcher), then in the workshop code do
`pip install -r requirements.txt` and run `python compare.py` (see `docs/07`). That
sidesteps the whole custom-image bring-up.

---

## What to capture / report back

1. The **serial boot log** (last ~40 lines at minimum) — this is the single most
   useful artifact; it names the fix.
2. Result of the **SD-swap** test (friend's card in this board; this card in
   friend's board).
3. Whether the **128 GB card** is the same one the friend flashed successfully.
4. Which **power** method is in use (barrel jack + J48 vs micro-USB).
5. Any `mmcblk0` / `EXT4-fs` / `Kernel panic` / `Unable to mount root fs` lines.

Record answers back into this file (or `docs/03`'s open-questions section) so the
context stays current for the next session.

---

## Pointers to the rest of the context pack

- `docs/README.md` — index + one-paragraph project summary.
- `docs/01`–`02` — what the workshop is + the code/architecture.
- `docs/03` — the Jetson end-goal and porting concerns.
- `docs/04`–`06` — the confirmed architecture (Mode 2 + hybrid escalation) and
  deployment topology (Jetson = edge, laptop = relay/dashboard).
- `docs/07` — the ordered action plan (start with `python compare.py`).
