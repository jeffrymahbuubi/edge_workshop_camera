# Project Context Pack

This folder is a **self-contained context pack**. It was written on a Mac so that
anyone picking the project up later — especially working **on the Jetson Nano 4GB
itself** — can read these files and understand *what this project is* and *what
the goal on the Jetson is*, without having to re-derive it from the source code.

> **Why this exists**: the actual working code lives in
> `references/context/edge-workshop-camera-en/`. That code is a teaching package
> written for laptops. The intent is to run it on a Jetson Nano 4GB. These docs
> capture the project, the reasoning, and the open questions so the Jetson-side
> work starts with full context instead of a cold read.

## How to use this pack

The folders are grouped by **where you are when you need them** — at a desk
deciding, at the bench with a Jetson in hand, or setting up dev tooling. The file
numbers are a **reading order** that runs straight through `01` → `12`, so you can
still read the pack front-to-back and ignore the folders entirely.

### [`01-design/`](01-design) — understand and decide

Read at a desk. No hardware needed.

| File | What it gives you |
|---|---|
| [`01-project-overview.md`](01-design/01-project-overview.md) | What the project *is*: the workshop, its core teaching idea, the two modes, the application domain (home fall-detection). Read this first. |
| [`02-architecture-and-code.md`](01-design/02-architecture-and-code.md) | The technical reference: file-by-file breakdown, the model-free algorithm, data flow, the relay API, config knobs. |
| [`03-ultimate-goal-jetson.md`](01-design/03-ultimate-goal-jetson.md) | **The goal**: run this workshop on Jetson Nano 4GB. Candidate hardware roles for the Jetson (undecided — trade-offs documented), conceptual porting concerns, and the open questions to resolve on-device. |
| [`04-mode2-llm-interpretation.md`](01-design/04-mode2-llm-interpretation.md) | The Mode 2 + hosted-LLM step: confirmed constraints (original Nano 4GB → no local LLM; hybrid connectivity → graceful degradation) and hosted-LLM options. *Extended by `05`.* |
| [`05-hybrid-escalation-architecture.md`](01-design/05-hybrid-escalation-architecture.md) | **Confirmed architecture**: hybrid escalation — Mode 2 always-on base + upload the raw clip *only on a suspected fall* to a cloud interpreter. Answers "what's the Jetson's role" (smart first-pass gate) and proposes the cloud-interpreter options (VLM; Claude leading, NVIDIA free-tier fallback). |
| [`06-deployment-topology-edge-relay.md`](01-design/06-deployment-topology-edge-relay.md) | **Confirmed deployment topology (boss-faithful)**: **Jetson = edge / sensing node, laptop = cloud/relay + web dashboard**, real LAN hop between them (Role A). Revised away from an earlier all-in-one draft. Lists the boss's target metrics (bandwidth, privacy, resilience) and the new SSE dashboard. |

### [`specs/`](specs) — build from these

**Live implementation guides.** Written 2026-07-16, grounded in a live probe of
`jetson-2gNANO`. Tick the checkboxes as you build; when a decision changes, change it in
the spec *first*. `SPEC-01` is the contract — if any spec contradicts it, `SPEC-01` wins.

| File | What it gives you |
|---|---|
| [`SPEC-01-layout-and-contracts.md`](specs/SPEC-01-layout-and-contracts.md) | **Read first.** Verified platform facts (**python3 is 3.8, not 3.6**; PyTorch already installed; **disk at 88% is the real constraint**), the `src/` layout by machine, and the normative edge↔relay HTTP contract. |
| [`SPEC-02-relay-and-edge.md`](specs/SPEC-02-relay-and-edge.md) | 🔴 **Top priority.** Modes 1+2 → dashboard. Byte accounting (the 689× counter has no data source today), the shared flag helper, SSE, `/latest.jpg`, ring buffer. **Includes hardware-validated results** — the real ratio is **~2,395×, not 689×** — and two confirmed blockers. |
| [`SPEC-03-web-dashboard.md`](specs/SPEC-03-web-dashboard.md) | The browser: split status/lesson layout, the video panel (whose *emptiness* in Mode 2 is the privacy lesson), 60 s chart, event log, offline-only assets. |
| [`SPEC-04-mode3-posture.md`](specs/SPEC-04-mode3-posture.md) | 🟢 **BUILT + HARDWARE-VALIDATED 2026-07-16.** Mode 3 = **MoveNet keypoints on the Jetson** → fall rule → relay → **live skeleton on the dashboard**, and the alarm **fires on a real person**. 562 B on the wire (~1,037× under Mode 1) and it carries a skeleton. Records why `bgsub` was deleted (it faded a still person to `absent` in ~2 s, making the fall unfireable — *and* it could not work without Mode 2's detector), and why keypoints are now allowed on the LAN when frames never are. |
| ~~`SPEC-05-tensorrt-backend.md`~~ | ⛔ **DELETED 2026-07-16.** Designed a `trt_pose`/TensorRT backend that was never built — MoveNet/TFLite shipped instead (SPEC-04). Its **pre-clone checklist moved to SPEC-01 §6**, which is the part that mattered. The lesson it paid for is recorded in SPEC-01 §1: it agonised over 81 MB of weights and an engine build against 88% disk, while **TensorFlow was already installed** — the answer cost 4.7 MB and no install. Nobody checked before designing around TensorRT. |
| [`SPEC-06-live-fall-tuning.md`](specs/SPEC-06-live-fall-tuning.md) | **Live-tunable fall thresholds for Modes 1/2** from the dashboard — two sliders POST to the relay; Mode 1 applies instantly, Mode 2's edge pulls the numbers back and applies them next tick (fusion stays on the Jetson). Solves the solo-demo problem where making the loud sound is itself motion. Built + laptop-verified 2026-07-16. |
| [`SPEC-07-dashboard-mode-switch.md`](specs/SPEC-07-dashboard-mode-switch.md) | **Student-driven mode switching from the dashboard** — Mode 1/2/3 buttons POST to the relay; a new `edge/supervisor.py` on the Jetson polls and starts/stops the matching client. Keeps the three programs separate (boss's structure), adds a control channel so a student switches modes without terminal access. Built + validated end-to-end on the Jetson 2026-07-16. |

### [`02-hardware/`](02-hardware) — at the bench, Jetson in hand

The **steps** (`07`–`09`, `12`) and the **why** (`10`) are deliberately separate: a
runbook you can follow without reading, and the rationale for when a step
surprises you.

| File | What it gives you |
|---|---|
| [`07-getting-started-action-plan.md`](02-hardware/07-getting-started-action-plan.md) | **The *do* list**: ordered, machine-split action plan (MacBook now → Jetson later) with exact commands. Start here when moving from design to work. The recommended first step is `python compare.py` on the Mac. |
| [`08-jetson-flashing-bringup-runbook.md`](02-hardware/08-jetson-flashing-bringup-runbook.md) | **Jetson bring-up / flashing runbook (Ubuntu 18.04 host)**. Self-contained context for a Claude session on the Ubuntu laptop. The active hardware problem: a Nano 4GB **hangs at the NVIDIA logo** (custom image is known-good on another 4GB board). Diagnosis-first plan: **serial console → recovery-mode `flash.sh`** if it's a bootloader/QSPI-stage hang. Read this when working on the physical device. |
| [`09-internet-sharing-setup.md`](02-hardware/09-internet-sharing-setup.md) | **The runbook: how a student's laptop gives the Jetson internet over the LAN cable** — the only path, since the Jetson has no Wi-Fi and the lab Wi-Fi isolates clients. **Steps only.** Windows (run `scripts\setup-internet-sharing-windows.ps1` as admin → `ssh jetson@192.168.137.100`) and macOS (toggle Internet Sharing → `scripts/setup-internet-sharing-macos.sh`). Read this before the workshop, or when the Jetson can't reach the internet. |
| [`10-internet-sharing-findings.md`](02-hardware/10-internet-sharing-findings.md) | **The *why* behind `09`** — findings, gotchas and design rationale, all hardware-verified or explicitly marked unverified. The core trade: **the Jetson is pinned to a static `192.168.137.100`, which pins the workshop to Windows**, because every host OS shares on a different subnet and NATs only for its own. Also holds [the rejected DHCP design](02-hardware/10-internet-sharing-findings.md#the-rejected-alternative-dhcp) — what to revert to if a Mac ever needs supporting. Read this when a step in `09` breaks, or before changing any address. |
| ~~`12-mode3-selftest-runbook.md`~~ | ⛔ **DELETED 2026-07-16** — a runbook for the deleted `bgsub` backend: its fade test measured something that no longer exists and its tuning knobs went with the code. **For Mode 3 today use `MODE3_TEST_GUIDE.md`** in `references/context/edge-workshop-camera-en/mode3/` — its §9 on camera framing is the single biggest accuracy factor. |

### [`03-tooling/`](03-tooling) — the dev environment

About the machines we *build* on, not the ones we ship.

| File | What it gives you |
|---|---|
| [`11-nvidia-tooling-and-skills-findings.md`](03-tooling/11-nvidia-tooling-and-skills-findings.md) | **What upstream NVIDIA tooling is worth using — and what bricks a Nano.** Of four repos in `references/nvidia-jetson/`, only **Elements** ships an MCP server (now wired into `.mcp.json`, and its UI bundle vendored offline to `src/web/vendor/elements/` — proven offline-safe in a real browser). Of the Jetson Agent Skills, only **3 of 6 are safe on a Nano 4GB**: they all assume Orin/Thor, so a **t210 reports `sku=unknown`**. **🛑 `jetson-optimize-memory` can brick the board** — it edits t234-only BCT carveouts and its only guard is prose. Read this before installing any NVIDIA skill, or before touching `.mcp.json`. |

## One-paragraph summary (if you read nothing else)

This is a **6-hour teaching workshop** called *"Edge Sensing & Cloud Processing
(Camera + Audio)."* It teaches one idea: **between a sensor and the cloud, where
should you draw the compute-partitioning line?** It answers this by running the
same webcam+mic feed two ways — **Mode 1** streams raw audio/video to a cloud
relay (~7.3 GB/day, faces + voices leave the room), **Mode 2** does **model-free**
motion + audio detection on the edge and uploads only a tiny feature vector
(~10 MB/day, ~689× less, privacy-preserving). The detection is deliberately
**pure OpenCV frame-differencing + audio RMS — no neural networks, no TensorRT,
no models.** The concrete application is **elderly / home fall detection**. The
**ultimate goal** is to deliver this workshop with **Jetson Nano 4GB devices** as
the edge hardware instead of laptops.

## Scope notes (decisions baked into this pack)

- **Conceptual, not command-level.** These docs explain *what differs* on the
  Jetson and *why*. Exact JetPack/Python/OpenCV versions and install commands are
  intentionally left to be verified on the device — hardware in hand beats
  guessing from a Mac.
- **Model-free only.** The ML-upgrade path (YOLO / MediaPipe / TensorRT — what a
  Jetson GPU is normally *for*) is **deliberately out of scope** here, matching
  the workshop's design. It is noted only where honesty requires it, never
  documented as a goal.
- **Source of truth is the code.** Where these docs and the code in
  `references/context/edge-workshop-camera-en/` ever disagree, the code wins —
  re-read it and update these notes.
