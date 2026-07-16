# 13 — ngrok: showing the dashboard to someone who is not in the room

> **Demo transport only. It changes nothing about the project.**
>
> The architecture is untouched: the Jetson still senses, the laptop still runs the relay,
> and the LAN cable still carries the Mode 1/2/3 traffic that the whole lesson measures.
> ngrok only lets a **remote viewer** see the dashboard the laptop was already serving.
> Nothing about the edge/cloud split, the byte accounting, or the privacy argument depends
> on it — and none of it changes when the tunnel is off.

| | |
|---|---|
| **Status** | 🟢 **Verified END TO END on hardware 2026-07-16** — remote browser → tunnel → relay → **real Jetson**, all three modes driven from the tunnel |
| **Tier** | **PAID** — a custom domain works. `https://edge-sensing.ngrok.app` is reserved on this account |
| **Version** | `3.39.8-msix-stable`, installed via MSIX (`WindowsApps\ngrok.exe`), already authenticated |
| **Use it for** | Showing the live dashboard to someone remote — a boss, a co-instructor, a colleague |
| **Do NOT use it for** | The workshop itself. Students sit next to the laptop; `http://127.0.0.1:8000` is right there |

> ⚠️ **The tunnel currently runs with NO authentication — Jeffry's explicit decision**
> (2026-07-16), made after being shown the specific risk below. Anyone with the URL can
> watch the camera and turn the Mode 3 preview on. **Start it only for a demo, and stop it
> after** (§3). If you want it protected again, `--basic-auth` still works (§1).

## 0. The commands, once you know what you are doing

```powershell
# 1. relay (leave running)
uv run uvicorn relay.relay_server:app --app-dir src --host 0.0.0.0 --port 8000

# 2. tunnel -- custom domain, works on this account
ngrok http 8000 --url=https://edge-sensing.ngrok.app

# 3. when the demo is over -- DO NOT SKIP
Get-Process ngrok | Stop-Process -Force
```

---

## 1. ⚠️ Read this before you open a tunnel

**The dashboard has no authentication of its own.** The *ingest* endpoints require
`X-Device-Token`, but everything a viewer touches is wide open:

| Endpoint | What anyone with the URL can do |
|---|---|
| `GET /latest.jpg` | **watch the room's camera** while Mode 1 is running |
| `POST /preview` | **turn the Mode 3 setup camera ON** — starts real pixels flowing |
| `POST /mode` | switch modes underneath you, mid-demo |
| `POST /config` | move the fall thresholds |
| `POST /reset` | wipe the byte totals the demo is built on |

A bare `ngrok http 8000` publishes all of that to anyone who has the link. The URL is random
and unguessable, but a link that lands in a chat thread stops being a secret.

> **So: always pass `--basic-auth`.** It is one flag, it works on the free tier (verified),
> and it turns "anyone with the link" into "anyone with the link *and* the password".

---

## 2. Start it

The relay must already be running (see the README). Then, in a **second** terminal:

```powershell
ngrok http 8000 --basic-auth "workshop:PICK-A-PASSPHRASE"
```

ngrok prints a `Forwarding` line with a `https://<random>.ngrok-free.dev` URL. Send that URL
**and** the passphrase to your viewer; the browser will prompt them for it.

**Check it worked** — from any machine, no credentials, must be **401**:

```powershell
curl.exe -o NUL -w "%{http_code}\n" https://<your>.ngrok-free.dev/health
# 401
```

If that prints `200`, **the tunnel is unprotected — stop it now** and re-read §1.

### Where the URL comes from, if you missed it

ngrok runs a local API on `:4040` (its web inspector is at <http://127.0.0.1:4040>):

```powershell
(Invoke-RestMethod http://127.0.0.1:4040/api/tunnels).tunnels[0].public_url
```

---

## 3. Stop it

**The tunnel outlives the terminal window's scrollback, not your attention.** When the demo
is over, close it — an ngrok agent left running keeps the room's camera one click away.

```powershell
Get-Process ngrok | Stop-Process -Force
# prove it: the local API should be gone
try { Invoke-RestMethod http://127.0.0.1:4040/api/tunnels -TimeoutSec 3 } catch { "no tunnel" }
```

---

## 4. Findings, and one that cost time

### ✅ It works, and SSE survives the tunnel

The dashboard renders through ngrok and the connection badge reads **connected** — so the
`EventSource` stream at `/events` is proxied fine. That was the real risk: SSE is a
long-lived streaming response, and plenty of proxies buffer it into uselessness. ngrok
does not.

### ✅ `--basic-auth` works on the free tier

Verified end to end: `401` without credentials, `200 {"ok":true}` with them. No paid plan
needed for this.

### ⚠️ Do NOT put the credentials in the URL — it silently breaks the dashboard

`https://user:pass@host` looks like a convenient shortcut. It is a trap:

> **Chrome refuses to build a `fetch()` from a page whose URL carries credentials**
> (`TypeError: Request cannot be constructed from a URL that includes credentials`).

The page still *loads* and SSE still connects — but every `fetch()` in `app.js` throws, so
`GET /config` never runs and **the Fall-sensitivity sliders sit at `—`** instead of their
real values. It looks exactly like a broken dashboard or a broken tunnel. It is neither.

**Use the bare URL** and let the browser prompt for the password. Then the page origin is
clean and `fetch` behaves normally.

*(This was diagnosed here after the sliders read `—` through the tunnel and read correctly
on localhost. The cause was the test method, not the code — worth an entry so nobody
"fixes" `app.js` chasing it.)*

### ⚠️ playwright-cli cannot log into a basic-auth tunnel

It has no `--http-credentials` equivalent, and the URL trick above breaks the page under
test. **Consequence: the through-the-tunnel dashboard could not be automatically verified
end to end** the way `verify-webpages-with-playwright-cli` normally requires. The manual
check is ten seconds: open the URL, type the password, confirm the sliders read `0.050` /
`0.006` rather than `—`.

> **Do not "solve" this by dropping `--basic-auth` to make the test pass.** That trades a
> real control for a green check, and it was tried here and reverted.

---

## 5. What ngrok does not change

Worth stating plainly, because a tunnel *looks* like it moves the architecture:

- The **relay still runs on the laptop**. ngrok forwards to `localhost:8000`; it does not
  host anything.
- The **Jetson still talks to the laptop over the LAN cable**, at `192.168.137.1:8000`. It
  neither knows nor cares that a tunnel exists.
- The **byte accounting is unaffected** — it measures what the Jetson sent over the cable,
  which is the number the workshop is about. A remote viewer's traffic is not counted and
  should not be.
- **Mode 1 is still the mode that ships pixels.** The tunnel does not add or remove a
  privacy problem; it changes who can watch the one the demo already has.

---

## 6. End-to-end on hardware — 2026-07-16 ✅

Driven **entirely from the remote browser** through `https://edge-sensing.ngrok.app`,
against the real Jetson + C270 over the LAN cable. Every mode button clicked in the tunnel;
the Jetson's supervisor swapped clients each time.

| | Through the tunnel | Verdict |
|---|---|---|
| `GET /config` | 200, sliders read **0.050 / 0.006** | ✅ *(this is what the URL-credentials trap breaks)* |
| SSE `/events` | badge **connected**, live updates | ✅ streaming survives the proxy |
| **Mode 1** | `▶ Mode 1 live`, **139 KB/s**, frame rendering, `audio 0.0100` | ✅ real JPEG stream proxies fine |
| **Mode 2** | `▶ Mode 2 live`, **60 B/s**, **panel blanked** | ✅ the privacy lesson survives the tunnel |
| **Mode 3** | `▶ Mode 3 live`, **521 B/s**, **live MoveNet skeleton** | ✅ |
| **Setup preview** | ON → real frame + banner + 14.8 KB/s; OFF → dropped instantly | ✅ Mode 3's own total **unmoved** |

**The Mode 1 question is answered: a real ~139 KB/s JPEG stream goes through the free-tier
tunnel without trouble** — that was the open item, and it was the case most likely to strain it.

> ⚠️ **The Jetson's `~/EDGE-CAMERA/` is a MANUAL COPY, not a git clone**, and it was
> **months of commits stale** — it silently ran the pre-SPEC-08 Mode 3 with no audio at all.
> Nothing warned; the logs just lacked an `rms=` field. **A clone of `main` at
> `~/edge_workshop_camera/` is now the live one** (`cd ~/edge_workshop_camera/src`). If a
> feature you just pushed "does not work on the Jetson", check *which copy is running*
> before you debug the code.

## 7. Open

- [ ] ngrok free shows a **browser interstitial** on first visit for some accounts. It did
      not appear here (the dashboard loaded straight through), but if a viewer reports a
      "You are about to visit…" page, they click through once and it sticks.
- [ ] The `setup camera` **rate does not decay** after the preview is switched off (it
      froze at 15.0 KB/s). Same cosmetic issue as Mode 1's rate column — the EWMA has no
      idle input. Totals and the ratio are correct.
