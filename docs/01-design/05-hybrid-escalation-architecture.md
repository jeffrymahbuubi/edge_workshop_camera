# 05 — Confirmed Architecture: Hybrid Escalation (Mode 2 base + raw-on-event cloud interpretation)

This supersedes the "pure Mode 2" framing in `04` by *extending* it (Mode 2 stays
the base). It records the architecture the user selected and the cloud-interpreter
options proposed for it.

## Confirmed decision

Build **hybrid escalation** (the handout's own "mature compromise"):

- **Always-on, offline-capable base = Mode 2.** Every second: `extract_features`
  (model-free OpenCV frame-diff + audio RMS + fusion) → flag
  `quiet / person-active / FALL?`. No model, no network needed. Only tiny feature
  vectors leave the device in normal operation.
- **On a suspected fall, escalate.** When `fall_suspected` is true, upload **only
  that short raw clip** (a few keyframes + the second of audio) to a **cloud
  interpreter** that actually "sees" it and returns a grounded caregiver note.
- **Best-effort.** The escalation is optional enrichment: buffer the flagged clip
  and back-fill the interpretation when connectivity returns (reuse Mode 2's
  store-and-forward). Never a hard dependency.

```
Every second (always-on, private, offline-OK):
  sensor → extract_features → flag: quiet / person-active / FALL?
                                             │ fall_suspected
                                             ▼
   ESCALATE: upload just that raw clip (few keyframes + audio) to CLOUD INTERPRETER
                                             ▼
   interpreter sees the clip → grounded caregiver note  (buffer + back-fill if offline)
```

## Why this architecture (fits every confirmed constraint)

- **Original Jetson Nano 4GB** (no local LLM/VLM): the rich interpreter lives in
  the **cloud**, not on the device — consistent with "no local ML on the Jetson."
- **Hybrid connectivity**: normal path needs no network; escalation is best-effort
  + buffered.
- **Privacy**: raw frames leave **only** for flagged fall moments, not continuously.
- **Bandwidth**: ~feature-scale in normal operation; raw only on rare events.
- **Meaningful Jetson role** (this was the user's open question — now answered):
  the Jetson is the **always-on, private, cheap first-pass detector that decides
  *when* an expensive/privacy-costly raw upload + rich cloud interpretation is
  warranted.** Not a dumb camera (that was pure Mode 1); a smart filter/gate.

## Correcting the earlier confusion (for the record)

Mode 1's cloud "interpretation" was **never ambiguous** in the code: `/ingest_raw`
runs the **same `extract_features`** as Mode 2 — the difference between the modes
is *where* features are computed, not *what* computes them. What was genuinely
absent is a *richer-than-frame-differencing* interpreter (one that understands the
scene). That absence was **deliberate** (the workshop's "honest gap map"). Hybrid
escalation is precisely where that richer interpreter now gets added — in the
cloud, on rare events.

## Cloud raw-interpreter options (proposed; interpreter choice pending)

Escalation only fires on suspected falls (rare), so even a costly interpreter is
cheap in aggregate. The relay in a workshop is typically a **laptop with no GPU**,
which strongly favours a **hosted** interpreter over self-hosting.

| | Option 1 — Hosted VLM (multimodal) | Option 2 — Classic vision model | Option 3 — Vision model + text LLM |
|---|---|---|---|
| Does what | Looks at keyframes (+audio context), writes a grounded note | Pose/person detection → structured facts | Detector → structure → LLM narrative |
| Runs where | Hosted API: **NVIDIA API Catalog** (free tier, OpenAI-compatible) / Gemini / Anthropic | Relay GPU (workshop relay has none) or hosted endpoint | Detector endpoint + LLM |
| Effort | **Lowest** — existing `_maybe_llm_note` REST call + image content | Medium — model serving, pose→fall logic | Highest — two services |
| Cost | Free tier suffices (rare events) | GPU/compute or endpoint cost | Both |
| Output | Rich, human-readable, context-aware | Precise, explainable, not narrative | Best of both |
| Constraint fit | **Best** | Weakest (reintroduces model-serving) | Good but heavy |

**Recommendation: Option 1 — hosted VLM.** Two strong provider choices:

- **Anthropic Claude (leading candidate — already wired).** `_maybe_llm_note`
  already calls the `anthropic` SDK with default `LLM_MODEL = "claude-sonnet-5"`;
  current Claude models (Opus 4.8, Sonnet 5, Haiku 4.5) are **vision-capable**, so
  extending that existing call to include keyframes is the smallest possible delta.
  Sonnet 5 or Haiku 4.5 are the cost-sensible picks (events are rare → cents/day);
  Opus 4.8 for best reasoning.
  - ⚠️ **Billing caveat**: the lab's **Claude *Team tier* subscription does NOT
    grant programmatic API access.** Subscription plans (Free/Pro/Max/Team/
    Enterprise) are separate from the Anthropic **API**. The relay needs an API key
    from the Anthropic **Developer Platform / Console** (console.anthropic.com),
    billed separately (usage-based). A Team subscription does not cover the app's
    runtime LLM calls.
- **NVIDIA API Catalog (free-tier alternative).** build.nvidia.com — free tier,
  OpenAI-compatible, hosts VLMs. Use this if a Console API key / API billing isn't
  available. Gemini is another free-tier alternate.

Either way the API key stays **server-side on the relay**, consistent with the
project's key-security design. Exact model picked/verified on-device (conceptual
per project scope).

## Privacy & connectivity handling (must stay true)

- **Privacy**: escalation is a bounded, deliberate exception to "nothing leaves."
  Mitigations: send only a few keyframes (not full video), only on high-confidence
  events, optionally crop/blur, and choose the provider deliberately. Normal
  operation remains fully de-identified (features only).
- **Connectivity**: escalation upload + interpretation are best-effort. Buffer the
  flagged clip; back-fill the note when online. The flag itself is always produced
  offline.
- **Key safety**: the interpreter's API key stays server-side (as `_maybe_llm_note`
  already does). Where "server-side" physically is depends on topology (below).

## Implementation seams (where this touches existing code)

- `features.py::extract_features` → already yields `fall_suspected` (the escalation
  trigger). **No change needed to the detector.**
- `relay_server.py` → currently `/ingest_raw` (Mode 1, recomputes features) and
  `/ingest_features` (Mode 2 + `_maybe_llm_note`). The escalation path either
  extends `/ingest_raw` to call a VLM, or adds a dedicated `/ingest_event_clip`
  endpoint. `_maybe_llm_note` is the seam to generalize into a provider-agnostic,
  vision-capable interpreter.
- `mode2_edge.py` → gains logic: on `fall_suspected`, also send the raw clip
  (reuse `codec.encode_frame/encode_audio`) to the escalation endpoint, with a
  best-effort/buffered send like its existing `outbox`.

## Still open

- **Topology — RESOLVED (see `06`)**: **Jetson = edge, laptop = relay/cloud**
  (Role A — the boss-faithful mapping; an earlier all-in-one draft was revised).
  The escalation call + **API key live on the laptop-relay** (key *off* the edge,
  matching the boss's key-security design). Sensor on the Jetson (edge); the laptop
  runs the relay + the new web dashboard.
- **Interpreter choice**: Option 1 (hosted VLM) confirmed; **provider pending an
  account check** — does the lab have/can it get an Anthropic **Console** API key
  (console.anthropic.com) with billing, separate from the Claude Team subscription?
  - **If yes** → use **Claude** (already wired, vision-capable, best quality).
  - **If no** → use **NVIDIA API Catalog** free tier for the app.
  - *How to check*: sign in at console.anthropic.com with the lab account and look
    for **API Keys** + a billing/credits balance. Team-subscription-only accounts
    can sign in to claude.ai but won't have API keys / API billing there.
- **Escalation payload**: how many keyframes, whether to include audio or just its
  features, any crop/blur.
- **Note content**: severity, suggested action, use of the `context` field.
