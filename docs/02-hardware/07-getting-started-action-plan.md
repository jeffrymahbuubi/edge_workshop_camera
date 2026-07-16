# 07 — Getting Started: Action Plan (MacBook now, Jetson later)

Concrete, ordered steps. The design lives in `01`–`06`; this is the *do* list.

> **Key idea**: the reference package runs by default on a **synthetic scene** (no
> camera, no network needed). So this **MacBook can play both roles** (edge + relay)
> and validate the whole back-end **before** any hardware or the Jetson exists. All
> commands run from inside `references/context/edge-workshop-camera-en/`.

## Phase 0 — MacBook: understand + validate the reference back-end (START HERE)

No hardware, no Jetson, no LLM provider, no internet. This is the boss's own smoke
test (TA manual §4) and the foundation for everything.

```bash
cd references/context/edge-workshop-camera-en
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Test A — the headline: bandwidth 689× + detection validation (no network/camera)
python compare.py

# Test B — start the relay in one terminal, health-check in another
uvicorn relay_server:app --host 0.0.0.0 --port 8000
curl http://localhost:8000/health          # expect {"ok":true}

# Test C — Mode 1 (raw → relay runs features.py)
python mode1_streamer.py                    # Ctrl-C to stop

# Test D — Mode 2 (edge runs features.py → sends features)
python mode2_edge.py

# Test D2 — resilience: point at a dead relay, watch it buffer (store-and-forward)
RELAY_URL="http://127.0.0.1:9999" python mode2_edge.py
```

**Why start here**: it needs nothing external, it proves the boss's code runs on your
machine, and it makes the three target metrics concrete — **bandwidth** (Test A),
the **flag pipeline** (C/D), and **resilience** (D2). Everything later builds on it.

## Phase 1 — MacBook: build the NEW web dashboard (the real new work)

Still on the Mac, still synthetic scene. This is the one genuinely new component
(`06`). Build it on the **relay** side:

1. Add a **dashboard page** (HTML/JS) served by `relay_server.py`.
2. Add an **SSE `/stream`** endpoint (FastAPI `StreamingResponse`); the relay pushes
   each per-second result (flag, and later the caregiver note) to connected browsers.
3. Run Mode 2 against the local relay and watch the flag update live in your browser
   instead of the terminal.

Because it's all on the Mac against the synthetic scene, you can iterate fast with no
hardware. When it works here, it ports to the Jetson↔laptop split unchanged.

## Phase 2 — MacBook: escalation → VLM (deferred)

Wire the fall-event escalation to a hosted VLM (`04`/`05`). **Blocked on the provider
decision** (Claude vs NVIDIA free tier — pending the lab's Console-API-access check,
`05`). Can be prototyped fully on the Mac against the synthetic "fall" once a provider
+ key are available. Lowest priority.

## Phase 3 — Jetson: port + real hardware (later, on the device)

Do this on the Jetson once it's set up. Conceptual porting concerns are in `03`.

1. **Environment**: confirm JetPack/Python, install deps for **aarch64** (see `03`);
   run **`python compare.py` first** — if that works, the stack imports correctly.
2. **Edge role**: attach the USB webcam+mic to the Jetson; run
   `python webcam_selftest.py` (wave/clap) and **re-tune thresholds**
   (`MOTION_LEVEL_THRESH`, `LOUD_RMS_THRESH` in `common.py`).
3. **Split topology** (boss-faithful, `06`): relay + dashboard on the **laptop**,
   edge client on the **Jetson**:
   ```bash
   # On the laptop (relay+dashboard):
   uvicorn relay_server:app --host 0.0.0.0 --port 8000
   # On the Jetson (edge), pointing at the laptop over the LAN cable:
   RELAY_URL="http://<laptop-ip>:8000" SENSOR=webcam python mode2_edge.py
   ```
4. Open the dashboard on the laptop browser; verify the full Jetson→laptop pipeline.

## Recommended first step

**Phase 0, Test A — run `python compare.py` on this MacBook.** It's the smallest,
fastest, zero-dependency win, reproduces the boss's headline (689× + detection), and
confirms the environment before anything else. Then walk B → D → D2 to see the flag
pipeline and resilience.

## Split at a glance

| Machine | Can do now? | What |
|---|---|---|
| **MacBook** | ✅ now | Phase 0 (validate back-end), Phase 1 (build dashboard), Phase 2 (escalation, once provider chosen) — all against the synthetic scene |
| **Jetson** | ⏳ later | Phase 3 (env port, real webcam, split topology) — on the device |

Sequence within build: **terminal-first back-end (Phase 0) → dashboard (Phase 1) →
escalation (Phase 2) → Jetson hardware (Phase 3).**
