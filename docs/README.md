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

Read the files in order:

| File | What it gives you |
|---|---|
| [`01-project-overview.md`](01-project-overview.md) | What the project *is*: the workshop, its core teaching idea, the two modes, the application domain (home fall-detection). Read this first. |
| [`02-architecture-and-code.md`](02-architecture-and-code.md) | The technical reference: file-by-file breakdown, the model-free algorithm, data flow, the relay API, config knobs. |
| [`03-ultimate-goal-jetson.md`](03-ultimate-goal-jetson.md) | **The goal**: run this workshop on Jetson Nano 4GB. Candidate hardware roles for the Jetson (undecided — trade-offs documented), conceptual porting concerns, and the open questions to resolve on-device. |
| [`04-mode2-llm-interpretation.md`](04-mode2-llm-interpretation.md) | The Mode 2 + hosted-LLM step: confirmed constraints (original Nano 4GB → no local LLM; hybrid connectivity → graceful degradation) and hosted-LLM options. *Extended by `05`.* |
| [`05-hybrid-escalation-architecture.md`](05-hybrid-escalation-architecture.md) | **Confirmed architecture**: hybrid escalation — Mode 2 always-on base + upload the raw clip *only on a suspected fall* to a cloud interpreter. Answers "what's the Jetson's role" (smart first-pass gate) and proposes the cloud-interpreter options (VLM; Claude leading, NVIDIA free-tier fallback). |
| [`06-jetson-allinone-web-dashboard.md`](06-jetson-allinone-web-dashboard.md) | **Confirmed deployment topology (boss-faithful)**: **Jetson = edge / sensing node, laptop = cloud/relay + web dashboard**, real LAN hop between them (Role A). Revised away from an earlier all-in-one draft. Lists the boss's target metrics (bandwidth, privacy, resilience) and the new SSE dashboard. |
| [`07-getting-started-action-plan.md`](07-getting-started-action-plan.md) | **The *do* list**: ordered, machine-split action plan (MacBook now → Jetson later) with exact commands. Start here when moving from design to work. The recommended first step is `python compare.py` on the Mac. |
| [`08-jetson-flashing-bringup-runbook.md`](08-jetson-flashing-bringup-runbook.md) | **Jetson bring-up / flashing runbook (Ubuntu 18.04 host)**. Self-contained context for a Claude session on the Ubuntu laptop. The active hardware problem: a Nano 4GB **hangs at the NVIDIA logo** (custom image is known-good on another 4GB board). Diagnosis-first plan: **serial console → recovery-mode `flash.sh`** if it's a bootloader/QSPI-stage hang. Read this when working on the physical device. |
| [`09-internet-sharing-setup.md`](09-internet-sharing-setup.md) | **How a student's laptop gives the Jetson internet over the LAN cable** — the only path, since the Jetson has no Wi-Fi and the lab Wi-Fi isolates clients. **macOS: done and hardware-verified**; Windows: TBD. The core design: **the Jetson is a DHCP client**, because every host OS shares on a different subnet and NATs only for its own. Ships with `scripts/setup-internet-sharing-macos.sh` (read-only checker). Read this before the workshop, or when the Jetson can't reach the internet. |

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
