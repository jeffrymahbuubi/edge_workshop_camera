# 03 — Ultimate Goal & Jetson Nano 4GB Context

## The ultimate goal (one sentence)

> **Deliver this edge-sensing workshop with NVIDIA Jetson Nano 4GB Developer Kit
> devices serving as the edge hardware, instead of laptops.**

The teaching content and the model-free algorithm stay the same. What changes is
the *machine* the sensing/edge code runs on. The point is not to exploit the
Jetson's GPU (that's explicitly out of scope — see the guardrail below); it is to
run the existing workshop on this specific, constrained, older device and have it
work reliably in a classroom.

### Guardrail: model-free only

The Jetson's GPU would normally be used for real detection models (YOLO /
MediaPipe + TensorRT). **That is deliberately excluded** from this goal, matching
the workshop's design. Do **not** introduce ML models as part of "getting it onto
the Jetson." If the GPU/ML path ever becomes a real objective, it's a *new* goal
and this doc should be revised first.

## Working context (as of writing)

- The Jetson Nano 4GB is **in hand**.
- The plan is to continue the porting work **directly on the Jetson**. This pack is
  the context for that on-device work.
- These docs were prepared on a Mac; nothing here has been executed on the Jetson
  yet. Treat every hardware/version claim below as **"verify on the device."**

## Candidate roles for the Jetson (UNDECIDED — trade-offs to choose from)

The workshop has three logical components: **sensor + edge client** (captures,
optionally extracts features), and the **relay** (the "cloud" — holds the key,
validates tokens, interprets). How these map onto Jetson(s) vs laptops is **not
yet decided.** Four plausible arrangements:

### Role A — Jetson as edge client only (closest to current design)
Jetson runs the sensor + Mode 1/2 client (webcam capture, feature extraction). A
laptop or cloud host still runs the FastAPI relay.
- **Pros**: Smallest change from the current code; the Jetson does exactly what
  the workshop calls "the edge," which is conceptually the honest place for it.
  Relay stays on a roomier machine.
- **Cons**: Still needs a separate relay host + a working LAN; doesn't showcase
  the Jetson as a self-contained node.

### Role B — Jetson all-in-one / standalone
Each Jetson runs **everything** — sensor + client + relay — on one box
(`RELAY_URL=http://localhost:8000`). A student does the whole workshop on one
self-contained device.
- **Pros**: No dependency on other machines or classroom networking; each student
  is independent; simplest classroom logistics; still demonstrates every concept
  (the "network drop" test can point at a dead port as today).
- **Cons**: Heaviest load on a 4GB device (camera capture + JPEG encode + FastAPI
  + feature extraction together); the client↔relay "network" is just loopback, so
  the LAN/Wi-Fi realism of the bandwidth story is muted.

### Role C — one Jetson as the shared relay; laptops are edge clients
A single Jetson is the central "cloud" relay; student laptops run the clients.
- **Pros**: One Jetson serves a whole room; students keep familiar laptops as
  clients; positions the Jetson as an always-on appliance.
- **Cons**: Fewer Jetsons needed but the Jetson becomes a single point of failure
  for the class; the relay is the least "edge" role, so it under-uses the device
  conceptually; must handle N concurrent clients on 4GB.

### Role D — mixed / per-bench pairs
Some benches use Jetson-as-client (Role A), one Jetson is the shared relay (Role
C), etc.
- **Pros**: Flexible; matches however many Jetsons actually exist.
- **Cons**: More moving parts to explain and support on the day.

> **RESOLVED → Role A** (see `06`). Grounding in the boss's package (README
> "sensing node … upload to a cloud API"; handout diagram `[laptop]--Wi-Fi-->
> [Relay]`; TA manual §5.1 separate relay; Jetson framed as an edge device
> throughout) shows the boss's design is an **edge↔cloud split with a real network
> hop** — so **Jetson = edge, laptop = relay/cloud**. An earlier draft favored Role B
> (all-in-one); that was revised because all-in-one runs everything on localhost and
> collapses the very network split the lesson teaches. **Role B is retained only as a
> single-device smoke-test fallback.**

## Conceptual porting concerns (Jetson Nano 4GB)

Left at the *concept* level on purpose — confirm specifics on the device. The
Jetson Nano 4GB is an older, constrained, ARM64 board; the friction points to
expect:

1. **CPU-bound, and that's fine — but tight.** The whole algorithm is CPU-only
   (OpenCV + NumPy). The Nano's CPU is far weaker than a laptop's. Per-frame JPEG
   encoding in **Mode 1** is the acknowledged CPU hog even on laptops; on the Nano
   it may struggle to keep the 1 s cadence at `320×240 @15fps`. Mitigations that
   already exist in config: lower `FRAME_W/H`, lower `FPS`, lower `JPEG_QUALITY`.
   Mode 2 is much lighter (it uploads tiny vectors).

2. **4GB RAM is the headline constraint.** Camera buffers + OpenCV + FastAPI all
   share 4GB. Expect to care about swap and about not running everything at once.
   Role B (all-in-one) concentrates this pressure the most.

3. **Old OS / old Python.** The Nano's last official JetPack line is old (Ubuntu
   18.04-era, an older default Python). The code targets **Python 3.8+**. Whether
   the stock Python satisfies that, or a newer Python must be provided, is a
   **verify-on-device** question — do not assume.

4. **ARM64 (aarch64) wheels.** `numpy`, `opencv-python`, `fastapi`, `uvicorn`,
   `pydantic`, `sounddevice` must resolve to **aarch64** builds. Some may not have
   prebuilt wheels for an old Python/OS and could need system packages or building
   from source. **OpenCV specifically**: JetPack often ships a system OpenCV; the
   pip `opencv-python` wheel may or may not be the right choice — reconcile on the
   device (and mind `opencv-python` vs `opencv-python-headless`, below).

5. **Headless vs. display.** If the Jetson is run headless (SSH, no monitor), use
   `opencv-python-headless` (the code and handout already call this out). No
   display also affects camera/GUI assumptions — but note this code never opens a
   GUI window, so headless is fine functionally.

6. **Camera + audio device access.** `CAMERA_INDEX` may not be 0 (USB cams often
   1/2). A CSI camera vs a USB webcam behaves differently at the `cv2.VideoCapture`
   layer. `sounddevice` needs a working audio stack + device; if it's absent the
   code **already degrades to video-only with silent audio**, so a mic problem
   won't block bring-up.

7. **Networking realism.** The bandwidth story assumes real Wi-Fi/LAN. Role B
   makes the "network" loopback; Roles A/C need the Jetson reachable on the
   classroom subnet (`--host 0.0.0.0`, firewall/port 8000, correct `RELAY_URL`).

## Suggested first steps once on the Jetson (safe order)

Framed conceptually; the exact commands come from the TA manual / handout and
from what the device turns out to support.

1. **Prove the environment with zero hardware/network**: run `compare.py`. It
   needs no camera and no relay and reproduces the ~689× headline. If this runs,
   Python + numpy + OpenCV + the code all import correctly on the Nano.
2. **Stand up the relay locally** and hit `/health` (`{"ok":true}`).
3. **Run Mode 2** against the local relay (synthetic scene) — light load, exercises
   the full client→relay→flag path.
4. **Run Mode 1** against the local relay — this is where CPU/cadence limits show;
   watch whether it keeps up, and dial `FRAME_W/H`, `FPS`, `JPEG_QUALITY` if not.
5. **Attach a real webcam/mic**: `webcam_selftest.py` to confirm devices and
   **re-tune thresholds** (`MOTION_LEVEL_THRESH`, `LOUD_RMS_THRESH`), then
   `SENSOR=webcam` for Mode 1/2.
6. **Apply the resolved topology (Role A)**: Jetson = edge client, relay + dashboard
   on the laptop (see `06`); the earlier "decide topology" step is now settled.

## Open questions to resolve (carry these to the device)

- **Topology — RESOLVED (Role A)**: Jetson = edge, relay + dashboard on the laptop
  (see `06`). *(Still practical to confirm: how many Jetsons are available for the
  class, and the switch/router layout for multiple benches.)*
- **Performance**: can the Nano sustain Mode 1's per-frame JPEG at 1 s cadence, or
  must the default `FRAME_W/H` / `FPS` / `JPEG_QUALITY` drop? What settings keep
  it real-time?
- **Python/OS**: does the stock JetPack Python meet 3.8+, or is a newer Python
  needed? Do all deps have working aarch64 builds on it?
- **OpenCV**: system OpenCV (JetPack) vs pip wheel vs headless — which is correct
  on this image?
- **Memory headroom**: does the workshop leave enough of the 4GB to work
  comfortably on the device? *(Lighter now under Role A — the Jetson runs only the
  edge client, not the relay/dashboard/VLM, which live on the laptop.)*

> Every one of these is intentionally left open because it depends on the actual
> device state. When each is answered on the Jetson, record the answer back into
> this file so the context stays current.
