# Edge Sensing & Cloud Processing (Camera + Audio) — Jetson Nano port

A 6-hour teaching workshop that answers one question:

> **Between a sensor and the cloud, where should you draw the compute-partitioning line?**

It answers it by running the *same* camera + microphone feed two ways:

| | What crosses the network | Per day | Privacy |
|---|---|---|---|
| **Mode 1** | Raw video + audio; the cloud does everything | **~7.3 GB** | Faces and voices leave the room |
| **Mode 2** | A tiny feature vector, extracted on the edge | **~10 MB** | Raw pixels never leave the device |

That's a **~689× bandwidth difference** for the same detection result — the headline
number of the workshop. The application is **home / elderly fall detection**.

Detection is deliberately **model-free**: OpenCV frame-differencing + audio RMS + a
fusion rule. **No neural networks, no TensorRT, no models.** The point is the
partitioning decision, not the classifier.

**Everything runs on a synthetic scene by default — no webcam required.**

## 30-second smoke test (no hardware, no network)

```bash
cd references/context/edge-workshop-camera-en
pip install -r requirements.txt
python compare.py     # expect ~689x bandwidth gap, motion 12/12, falls 2/2
```

If that runs, your environment is good. This is the recommended first step on any
new machine, including the Jetson.

## What this repository is

The original workshop is a **laptop** teaching package. This repo is the work of
porting it to **Jetson Nano 4GB** hardware as the edge device.

The deployment topology (documented in `docs/06`) is:

```
[ Jetson Nano ]  --- LAN cable --->  [ Laptop ]
  edge / sensing                       relay + dashboard
  Mode 2 extraction                    holds the API key
  USB camera                           talks to the cloud
```

The Jetson never holds the API key — that's deliberate, and it's part of the lesson.

## Layout

| Path | What's in it |
|---|---|
| [`docs/`](docs/README.md) | **Start here.** The context pack: what the project is, the architecture, the Jetson port plan, and the hardware runbooks. Read `docs/README.md` for the reading order. |
| `references/context/edge-workshop-camera-en/` | The workshop package itself — the runnable code, the instructor handout, and the TA manual. **This is the source of truth**; if the docs disagree with the code, the code wins. |
| `references/context/docs/` | Field notes on Jetson setup and demo-day networking. |
| `scripts/` | Helper scripts (see below). |

## Docs worth knowing about

- **[`docs/01-project-overview.md`](docs/01-project-overview.md)** — what the workshop is and why. Read first.
- **[`docs/02-architecture-and-code.md`](docs/02-architecture-and-code.md)** — file-by-file walkthrough of the code.
- **[`docs/08-jetson-flashing-bringup-runbook.md`](docs/08-jetson-flashing-bringup-runbook.md)** — bring-up and flashing, including a board that hangs at the NVIDIA logo.
- **[`docs/09-internet-sharing-setup.md`](docs/09-internet-sharing-setup.md)** — giving the Jetson internet over the LAN cable from a laptop. macOS is verified on hardware; Windows is not yet written.

> **Heads-up on networking.** Two *different* designs are documented here and they
> contradict each other. `docs/09` uses laptop internet-sharing with the Jetson as a
> DHCP client (verified on hardware). `references/context/docs/DEMO_NETWORK_CHEATSHEET.md`
> uses fixed IPs and explicitly avoids internet-sharing (not yet validated). Read
> both before wiring anything up — which applies depends on whether the Jetson needs
> internet at all.

## Scripts

- `scripts/setup-internet-sharing-macos.sh` — read-only checker for the macOS
  internet-sharing path. Changes nothing; it verifies each layer between your Mac's
  Wi-Fi and the Jetson and names whatever is broken.

## Status

- ✅ Laptop → Jetson networking over the LAN cable (macOS; reboot-verified)
- ✅ Jetson reaches the internet via laptop internet-sharing
- ⬜ Windows equivalent of the above
- ⬜ Real webcam + threshold re-tuning on the Nano
- ⬜ Mode 1 CPU/cadence limits on the Nano
- ⬜ The escalation VLM path (`docs/05`) — blocked on an API provider decision

Open questions are recorded in the docs on purpose, next to the decisions they
affect. When one is answered on the device, record the answer back into the doc.
