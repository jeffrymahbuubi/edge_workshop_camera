"""Mode supervisor -- runs on the Jetson (SPEC-07).

Polls the relay for the student's selected mode and runs the matching client,
ONE at a time. The three mode programs stay separate -- this only starts and
stops them, so a dashboard button can switch modes without any terminal access
to the board. It is the laptop->Jetson control channel the dashboard needs, kept
deliberately dumb: the relay holds the choice, the Jetson polls and obeys.

Run once, and leave it running:
    RELAY_URL=http://192.168.137.1:8000 SENSOR=webcam python3 -u -m edge.supervisor

The laptop IP must be on the Jetson's own subnet: 192.168.137.1 for the workshop
image (Jetson at .137.100), 192.168.1.1 for the voice-assistant class image
(Jetson at .1.100). README Step 6 has the table.
"""
import os
import signal
import subprocess
import time

import requests

from common.config import RELAY_URL

POLL_S = 2.0
MODE_MODULE = {1: "edge.mode1_streamer", 2: "edge.mode2_edge", 3: "edge.mode3_posture"}


def _start(mode):
    print(f"[supervisor] START mode {mode} -> {MODE_MODULE[mode]}")
    # Children inherit our env (RELAY_URL, SENSOR, AUDIO_DEVICE...), so whatever
    # this process was launched with flows straight through to the mode client.
    return subprocess.Popen(["python3", "-u", "-m", MODE_MODULE[mode]],
                            env=os.environ.copy())


def _stop(proc):
    """SIGINT the child (its own Ctrl-C handler closes the camera cleanly), then
    give the USB camera a moment to release before the next mode opens it -- a
    rapid re-open leaves the C270 handing back empty frames."""
    if not proc or proc.poll() is not None:
        return
    print("[supervisor] STOP current mode (SIGINT)")
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=6)
    except subprocess.TimeoutExpired:
        print("[supervisor] child ignored SIGINT; SIGKILL")
        proc.kill()
        proc.wait()
    time.sleep(2)          # let /dev/video0 fully release


def main():
    url = f"{RELAY_URL}/mode"
    current, proc = None, None
    print(f"[supervisor] polling {url} every {POLL_S:.0f}s  (Ctrl-C to stop)")
    try:
        while True:
            try:
                desired = requests.get(url, timeout=4).json().get("mode")
            except requests.RequestException as e:
                print(f"[supervisor] relay unreachable, will retry: {e}")
                time.sleep(POLL_S)
                continue

            child_dead = proc is not None and proc.poll() is not None
            if desired != current or (desired in MODE_MODULE and child_dead):
                if child_dead:
                    print(f"[supervisor] mode {current} client exited; reacting")
                _stop(proc)
                proc = None
                current = desired
                if desired in MODE_MODULE:
                    proc = _start(desired)
                else:
                    print("[supervisor] no mode selected -- idle, camera free")
            time.sleep(POLL_S)
    except KeyboardInterrupt:
        _stop(proc)
        print("\n[supervisor] bye")
    finally:
        _stop(proc)


if __name__ == "__main__":
    main()
