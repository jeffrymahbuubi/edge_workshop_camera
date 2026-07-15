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

1. **Web dashboard (HTML/JS)** — served by `relay_server.py`, shows per second:
   motion / loud / fall flag + (when present) the caregiver note.
2. **Live-update channel — SSE.** One-way relay→browser; FastAPI serves it with
   `StreamingResponse`; the browser uses `EventSource`.
3. The relay already computes the flag on ingest; the dashboard just needs the relay
   to push each result to connected browsers (keep a "latest result" + fan-out).

`features.py` (the detector) and the escalation design are unchanged.

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

- **Interpreter provider** (Claude vs NVIDIA free tier) — pending the lab's
  Console-API-access check (`05`).
- **Dashboard content/design** — what to show (current second? fall-event log + note?).
- **Multi-bench networking** — switch/router layout for a whole class (later).
