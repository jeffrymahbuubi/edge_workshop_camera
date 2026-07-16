# 06 — Confirmed Deployment: Jetson = Edge, Laptop = Relay/Cloud + Web Dashboard

Records the topology + delivery decision, **grounded in the boss's original design**.

> **Revision note.** An earlier draft of this file proposed an *all-in-one* Jetson
> (relay on the Jetson, laptop as a pure viewer). That was reconsidered against the
> boss's package and **revised**: the boss's design is fundamentally an **edge↔cloud
> split with a real network hop**, so the faithful mapping is **Jetson = edge,
> laptop = cloud/relay**. All-in-one is kept only as a *fallback* for a single-device
> smoke test (see end). This is "Role A" from `03`.

## Why this is the boss-faithful topology (evidence)

- README: *"Use a laptop + USB webcam as a **sensing node** … then **upload to a
  cloud API** for processing."* → edge and cloud are separate.
- Handout diagram: `[USB webcam+mic] → [laptop] --Wi-Fi--> [Relay (cloud)]` → real
  network hop between device and relay.
- TA manual §5.1: one machine is the relay; clients point `RELAY_URL` across the LAN.
- The boss frames the Jetson as an **edge device** throughout (H.264 encode "a Jetson
  strength," TensorRT as the edge upgrade path) — never as the cloud.

The whole lesson (689× bandwidth, "faces leave the room," pull-the-network
resilience) **only exists because raw physically crosses a network.** An all-in-one
Jetson (everything on localhost) collapses exactly what the lesson teaches.

## Decisions locked

- **Topology = Jetson edge + separate laptop relay (Role A).**
- **Jetson = edge / sensing node.** USB webcam+mic on the Jetson; it runs the client
  (`mode1_streamer.py` / `mode2_edge.py`) and does **Mode 2 edge feature extraction**.
- **Student laptop = the "cloud"/relay + dashboard.** Runs `relay_server.py`,
  processes Mode 1 raw (or receives Mode 2 features), serves the web dashboard, and
  **holds the API key** for escalation (key stays *off* the edge — matches the boss's
  key-security design).
- **Real LAN hop** between them (a cable for now) — so bandwidth/privacy/resilience
  are **physically demonstrated**, not just conceptual.
- **New feature: a web dashboard** (current code has none) served by the laptop-relay.

## Node responsibilities

```
   ┌───────── Jetson Nano 4GB (EDGE / sensing node) ─────────┐        ┌──── Student laptop (CLOUD / relay) ────┐
   │ USB webcam+mic                                          │        │ relay_server.py                       │
   │  Mode 1: encode RAW frames+audio ───────────────────────┼─LAN───►│  Mode 1 → decode + run features.py    │
   │  Mode 2: run features.py at the EDGE → feature vector ───┼─LAN───►│  Mode 2 → receive features (no decode)│
   │  (does the on-device compute in Mode 2)                 │        │  → flag + escalation VLM (holds key)  │
   └─────────────────────────────────────────────────────────┘        │  → serves web dashboard (SSE)         │
                                                                       └───────────────┬───────────────────────┘
                                                                          student watches dashboard in browser
```

- **Mode 1**: Jetson ships **raw over the LAN** → laptop decodes + runs `features.py`
  → dashboard. Heavy, privacy-exposing, lost-on-drop. (Jetson is a dumb
  camera here — *that's the naive-baseline point*.)
- **Mode 2**: Jetson runs `features.py` **at the edge** → ships only the **tiny
  feature vector** → laptop maps to flag + dashboard. Light, private, buffered.
  (Jetson's edge compute is the star.)

The Mode1-vs-Mode2 contrast now maps cleanly onto the hardware: *Mode 2 uses the
Jetson's compute to avoid shipping raw; Mode 1 wastes it and pays the price.*

## What the lesson demonstrates (the boss's metrics)

Priority order, from the handout's own emphasis:

1. **Bandwidth (~689×)** — *"the most important teaching moment of the morning."*
2. **Privacy** — raw faces/voices vs de-identified labels — *"the star of this edition."*
3. **Network resilience** — pull-the-network: Mode 1 loses data, Mode 2 buffers —
   *"a required lesson in failure modes."*

Plus the overarching goal (the **compute-partitioning decision**), and the
model-free-method lessons (**threshold fragility**, **multimodal fusion**).

## Wiring & networking

- **Now (simplest)**: Jetson (edge) ↔ Ethernet cable ↔ laptop (relay+dashboard).
  Laptop runs the relay on `0.0.0.0:8000`; Jetson's client uses
  `RELAY_URL=http://<laptop-ip>:8000`; student opens the dashboard on the same laptop.
- **Internet**: a direct cable = no internet on that segment. Bandwidth/privacy/
  resilience all demonstrate fine offline; only the **escalation VLM note**
  needs internet (buffers until the laptop is online) — matches `04`/`05`.
- **Later**: a switch/router for a class of benches.

## New components to build (on the laptop-relay)

1. **Web dashboard (HTML/JS)** — served by `relay_server.py`. Layout decided below.
2. **Live-update channel — SSE.** One-way relay→browser; FastAPI serves it with
   `StreamingResponse`; the browser uses `EventSource`.
3. The relay already computes the flag on ingest; the dashboard just needs the relay
   to push each result to connected browsers (keep a "latest result" + fan-out).

`features.py` (the detector) and the escalation design are unchanged.

## Dashboard design (decided with Jeffry, 2026-07-16)

Both modes converge on the **same six fields per second** — `motion_level`,
`n_blobs`, `motion_flag`, `audio_rms`, `loud_flag`, `fall_suspected` (`features.py`).
One layout therefore serves both; only the *provenance* differs (Jetson-computed in
Mode 2, laptop-computed in Mode 1). The dashboard makes that provenance visible.

### Layout: split — status on top, the lesson below

```
┌─ STATUS ──────────────────────┐
│  ● person-active              │   live flag: quiet / person-active / FALL?
│  motion ▓▓▓▓▓░░░░░  0.34      │
│  audio  ▓▓░░░░░░░░  0.08      │
│  blobs: 2      fall: —        │
├─ THE LESSON ──────────────────┤
│  MODE 1   1.42 MB/s           │
│  MODE 2   2.1  KB/s           │
│  ratio      676× ▲            │   ← the ~689× teaching moment, live
└───────────────────────────────┘
```

### The video panel IS the privacy lesson

Show the live frames — because **the panel's emptiness in Mode 2 is the point.**
In Mode 1 the relay *has* the JPEGs (it must decode them to run `features.py`), so it
can display faces. In Mode 2 it **physically cannot** — no image ever crossed the LAN,
only a feature vector. The same panel going blank on a mode switch turns "faces leave
the room" from a claim into something the student watches happen.

```
MODE 1                MODE 2
┌────────────┐        ┌────────────┐
│  [ face ]  │        │  ␀         │
│  visible   │        │  no image  │
│  on relay  │        │  ever sent │
└────────────┘        └────────────┘
  ↑ privacy exposed     ↑ private
```

### History: rolling 60s chart + fall event log

A sparkline of motion/audio over the last minute, plus a timestamped event log.
The chart is what makes the **pull-the-network** demo legible: Mode 1's trace flatlines
and the lost seconds never return; Mode 2 buffers and **backfills** when the cable is
reconnected. Without a time axis a dropped second just flickers past unnoticed.

### Mode comparison: one mode live, both totals persist

Students run **one mode at a time** (one Jetson, one camera — no second sender, no
extra bench cost). The dashboard shows the live mode but **retains each mode's
cumulative byte total**, so switching Mode 1 → Mode 2 makes the ratio appear on screen.

```
LIVE: ▶ MODE 2
           bytes sent   last seen
MODE 1     84.2 MB      13:58
MODE 2     126 KB       ▶ now
           ─────────────────────
           ratio 668×
```

### Relay gaps this design exposes (must be built)

Reading the boss's `relay_server.py` against the layout above surfaces two real gaps:

1. **No payload accounting anywhere.** Neither `/ingest_raw` nor `/ingest_features`
   records how many bytes arrived, so **the 689× counter has nothing to feed it.**
   Needs a per-device, per-mode byte tally + a rate (bytes/sec) and cumulative total.
2. **`/ingest_raw` never computes the `flag` string.** It returns `cloud_features`
   only; the `"FALL?" / "person-active" / "quiet"` mapping lives solely in
   `/ingest_features`. For one dashboard to serve both modes, **lift that mapping into
   a shared helper** both endpoints call — otherwise Mode 1 has no flag to display.

## Build & test sequence (confirmed with the user)

All real code + testing happen **on the hardware later** — this session is
**documentation only**. When build starts:

1. **Terminal-first backend validation** — get the pipeline working with the
   **existing terminal clients** (synthetic scene → `compare.py`, then Mode 2, then
   `SENSOR=webcam` on the Jetson pointing `RELAY_URL` at the laptop relay), watching
   terminal output. Proves capture → transfer → `features.py` → flag end-to-end.
2. **Web dashboard second** — only once the terminal back-end is solid, add the
   dashboard + SSE on the relay.

## Fallback: all-in-one on the Jetson (single-device smoke test only)

If no second machine is handy, everything can run on the Jetson alone
(`RELAY_URL=http://localhost:8000`) as a **smoke test** — but the network hop is then
localhost, so the bandwidth difference is not physically demonstrated. Use only to verify
the pipeline runs; the boss-faithful classroom setup is edge + separate relay above.

## Still open / next

Priorities set by Jeffry on 2026-07-16:

- **TOP PRIORITY — get Mode 1 and Mode 2 onto the web dashboard.** Everything below
  is subordinate to this.
- **Dashboard content/design** — ✅ decided 2026-07-16, see *Dashboard design* above.
  Remaining sub-questions: video transport (SSE-inline vs MJPEG endpoint), byte-total
  reset/scoping, and whether the 60s history buffer lives server-side.

### Deferred / dropped

- **Interpreter provider** (Claude vs NVIDIA free tier, `05`) — **deferred, lowest
  priority.** The LLM escalation note is the last thing to build, so the
  Console-API-access check is no longer a blocker for anything on the critical path.
- **Multi-bench networking** (switch/router for a whole class) — **dropped.** A single
  Jetson↔laptop cable per bench is the design; no class-wide network layout is planned.
