# 12 — Mode 3 self-test runbook (posture & fall detection)

> **Steps only**, to run yourself at the bench. The *why* lives in
> [`docs/specs/SPEC-04-mode3-posture.md`](../specs/SPEC-04-mode3-posture.md); the fall
> rule's edge cases and the reason `bgsub` struggles are there. Read this when you want to
> check Mode 3 on the real Jetson camera.

## Where things run (the one thing to get right)

The camera is on the **Jetson**, so the **command runs on the Jetson**. The dashboard is on
the **laptop**, so you **watch the result on the laptop** — either in a browser, or in the
PuTTY window (the Jetson's terminal output shows up on your laptop screen). The two machines
are cabled together on one bench, so you can stand in front of the Jetson's camera and glance
at the laptop.

| Machine | Runs | You look here |
|---|---|---|
| **Laptop** | relay + web dashboard | browser at **http://localhost:8000/** |
| **Jetson** | the Mode 3 command (over PuTTY) | the PuTTY terminal window |

## Two tools, two questions

| Tool | Answers | Needs the relay? |
|---|---|---|
| `posture_selftest.py` | *Does it see me? What are the numbers?* — prints motion/aspect/posture every second | **No.** Jetson-only |
| `mode3_posture.py` | *Does the whole alarm work?* — posture label + red **FALL?** banner on the dashboard | **Yes** — posts to the laptop |

Start with `posture_selftest` (confirm the labels are right), then `mode3_posture` (see the
alarm end-to-end).

---

## Connect to the Jetson

Open **PuTTY**, host `192.168.137.100`, log in as `jetson` / `jetson`. Then:

```bash
cd ~/EDGE-CAMERA
```

All Jetson commands below are run from there. Stop any running command with **Ctrl-C**.

---

## Step A — does it detect your postures? (`posture_selftest`, no dashboard)

On the Jetson:

```bash
SENSOR=webcam python3 -m edge.posture_selftest
```

It runs for 30 seconds and prints a row per second. Watch the **posture** column:

1. **Step out of frame for ~5 s** — it learns the empty background. Ignore the noisy labels
   during this warm-up.
2. **Stand still** → should read `standing`
3. **Walk / wave** → should read `walking`
4. **Lie down** (or hold something wide and low in front of the lens) → should read `lying`

If a label is wrong, the table's footer names the knob to change in
`~/EDGE-CAMERA/edge/posture.py`:

| Symptom | Edit in `posture.py` | Direction |
|---|---|---|
| Lying down never reads `lying` | `LYING_ASPECT` | raise (toward 1.0) |
| Walking reads `standing` | `WALK_MOTION_THRESH` | lower |
| Standing reads `walking` | `WALK_MOTION_THRESH` | raise |
| You're in frame but it reads `absent` | `MIN_FG_FRACTION` | lower |

Re-run the command after each change.

## Step B — the fade test (the important measurement)

Still in `posture_selftest`: **lie down and stay completely still**, watching the clock. Time
how long until `lying` flips to `absent`.

That number is the **ceiling on how long the fall alarm can wait**. `bgsub` slowly learns a
motionless person into the background and then calls them `absent` — the exact state the fall
rule needs to see as `lying`. The default hold is **`FALL_HOLD_S = 3` seconds**, chosen to
fire before an expected ~8 s fade. **If your measured fade is much shorter than 8 s, tell
me** — we lower `FALL_HOLD_S`. This one number is what decides whether the simple backend is
good enough or whether the workshop needs the `trt_pose` upgrade (SPEC-05).

## Step C — the full alarm on the dashboard (`mode3_posture`)

**On the laptop**, make sure the relay + dashboard are up. A relay may already be running; if
so, just open the browser. To start one fresh, from the repo root:

```bash
cd src
uv run --with fastapi --with "uvicorn[standard]" --with opencv-python --with numpy --with pydantic \
  uvicorn relay.relay_server:app --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000/** in your browser. (`--host 0.0.0.0` matters — it's what lets
the Jetson reach the relay. `127.0.0.1` would block it.)

**On the Jetson:**

```bash
RELAY_URL=http://192.168.137.1:8000 SENSOR=webcam python3 -m edge.mode3_posture
```

Now watch the **browser on the laptop**:

- Stand / walk in view → status shows `person-active`, the posture line updates.
- **Lie down and stay down** → after `FALL_HOLD_S` (3 s) the banner turns red with
  **"upright→lying held 3s"** and the status reads **FALL?**.
- Get back up → the alarm clears.
- The **video panel stays blank** the whole time ("Mode 3 sent no image — only a posture
  verdict"). That is the privacy point, not a bug: the camera analysis runs on the Jetson and
  only the verdict crosses the cable.

---

## What to report back

So I can tune the thresholds and decide on SPEC-05:

- [ ] The **posture labels** from Step A — did standing / walking / lying each read correctly?
- [ ] The **fade time** from Step B — seconds from lying-still to `absent`.
- [ ] If you tuned any threshold, the **before/after value** and what fixed it.
- [ ] Did the **FALL? banner** fire in Step C, and roughly how many seconds after you lay down?

---

## Troubleshooting

| You see | Meaning / fix |
|---|---|
| `ModuleNotFoundError: No module named 'edge'` | You ran the file directly. Use the module form: `python3 -m edge.posture_selftest`, from `~/EDGE-CAMERA`. |
| `CAMERA ERROR` on the Jetson | The webcam isn't found. Check it's plugged in and is `/dev/video0`. |
| `address already in use` when starting the relay | An old relay is already on `:8000` — that's fine, just open the browser. (Two relays can silently fight over the port; if numbers look wrong, keep only one.) |
| Dashboard never updates in Step C | The Jetson can't reach the laptop. Confirm the relay was started with `--host 0.0.0.0 --port 8000`, and that `RELAY_URL` on the Jetson is `http://192.168.137.1:8000`. |
| A "microphone is recording pure SILENCE" warning | Known, and **harmless for Mode 3** — fall detection uses the camera only. (It matters for Modes 1/2; see [`10-internet-sharing-findings.md`](10-internet-sharing-findings.md) neighbourhood notes on the mic.) |
| Everything reads `absent` with you in frame | You either skipped the ~5 s warm-up, or held still long enough to fade into the background (that *is* Step B). Move, or lower `MIN_FG_FRACTION`. |
