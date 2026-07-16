"""Mode 3 dashboard (server side) -- live pose + activity viewer.

Runs on the PC ("server"). The Jetson edge client POSTs pose data each second;
this dashboard draws the person's bounding box + 17-point skeleton and shows the
current posture and an abnormal-behaviour banner. Pure Python stdlib -- no deps.

Run:
  python mode3_dashboard.py                 # listen on 0.0.0.0:8090
  python mode3_dashboard.py --mock          # + generate fake data to preview the UI
Then open http://localhost:8090 in a browser.

Edge client POSTs JSON to /pose:
  {
    "device": "jetson01",
    "posture": "standing"|"walking"|"lying"|"absent",
    "condition": "normal"|"ABNORMAL",
    "reason": "was upright, now lying 3s",
    "bbox": [x, y, w, h],            # normalised 0..1
    "keypoints": [[x, y, score], ... 17],   # normalised 0..1, COCO/MoveNet order
    "score": 0.0..1.0
  }
"""
import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8090

_state = {"posture": "absent", "condition": "normal", "reason": "",
          "bbox": None, "keypoints": [], "score": 0.0, "ts": 0.0, "device": "-"}
_lock = threading.Lock()

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Mode 3 - Activity Monitor</title>
<style>
  body{margin:0;font-family:system-ui,sans-serif;background:#0f1115;color:#e8eaed}
  header{padding:14px 20px;font-size:18px;font-weight:600;border-bottom:1px solid #2a2e37}
  .wrap{display:flex;gap:24px;padding:24px;flex-wrap:wrap}
  canvas{background:#181b22;border:1px solid #2a2e37;border-radius:8px}
  .panel{min-width:240px}
  .banner{padding:14px 18px;border-radius:8px;font-size:20px;font-weight:700;margin-bottom:16px}
  .normal{background:#12351f;color:#5ce08a;border:1px solid #1e5c37}
  .abnormal{background:#3a1414;color:#ff6b6b;border:1px solid #7a1f1f;animation:pulse 1s infinite}
  @keyframes pulse{50%{opacity:.55}}
  .row{margin:8px 0;font-size:15px} .k{color:#9aa4b2} .v{font-weight:600}
  .stale{opacity:.4}
</style></head><body>
<header>Mode 3 &middot; Edge Pose &amp; Activity Monitor</header>
<div class="wrap">
  <canvas id="cv" width="480" height="360"></canvas>
  <div class="panel">
    <div id="banner" class="banner normal">normal</div>
    <div class="row"><span class="k">Posture:</span> <span class="v" id="posture">-</span></div>
    <div class="row"><span class="k">Reason:</span> <span class="v" id="reason">-</span></div>
    <div class="row"><span class="k">Confidence:</span> <span class="v" id="score">-</span></div>
    <div class="row"><span class="k">Device:</span> <span class="v" id="device">-</span></div>
    <div class="row"><span class="k">Mode:</span> <span class="v" id="mode">-</span></div>
    <div class="row"><span class="k">Upload/frame:</span> <span class="v" id="bytes">-</span></div>
    <div class="row"><span class="k">Last update:</span> <span class="v" id="age">-</span></div>
    <div class="row"><label><input type="checkbox" id="showImage" checked> Show camera image (Mode B)</label></div>
  </div>
</div>
<script>
const EDGES=[[0,1],[0,2],[1,3],[2,4],[0,5],[0,6],[5,7],[7,9],[6,8],[8,10],
             [5,6],[5,11],[6,12],[11,12],[11,13],[13,15],[12,14],[14,16]];
const cv=document.getElementById('cv'), ctx=cv.getContext('2d');
const W=cv.width, H=cv.height;
let bgImg=new Image(), bgReady=false, lastImg=null;
bgImg.onload=()=>{bgReady=true;};
function draw(s){
  ctx.clearRect(0,0,W,H);
  if(document.getElementById('showImage').checked && bgReady){ctx.drawImage(bgImg,0,0,W,H);}
  ctx.strokeStyle='#2a2e37'; ctx.strokeRect(0,0,W,H);
  const abn = s.condition==='ABNORMAL';
  // bounding box
  if(s.bbox){const[bx,by,bw,bh]=s.bbox;
    ctx.strokeStyle=abn?'#ff6b6b':'#4c9aff'; ctx.lineWidth=2;
    ctx.strokeRect(bx*W,by*H,bw*W,bh*H);}
  // skeleton
  const kp=s.keypoints||[];
  ctx.strokeStyle=abn?'#ff6b6b':'#5ce08a'; ctx.lineWidth=3;
  for(const[a,b]of EDGES){const p=kp[a],q=kp[b];
    if(p&&q&&p[2]>0.2&&q[2]>0.2){ctx.beginPath();
      ctx.moveTo(p[0]*W,p[1]*H); ctx.lineTo(q[0]*W,q[1]*H); ctx.stroke();}}
  ctx.fillStyle=abn?'#ff8a8a':'#8ce0ff';
  for(const p of kp){if(p&&p[2]>0.2){ctx.beginPath();
    ctx.arc(p[0]*W,p[1]*H,4,0,7); ctx.fill();}}
}
function render(s){
  draw(s);
  const b=document.getElementById('banner');
  const abn=s.condition==='ABNORMAL';
  b.className='banner '+(abn?'abnormal':'normal');
  b.textContent=abn?('⚠ ABNORMAL BEHAVIOUR'):'normal';
  document.getElementById('posture').textContent=s.posture||'-';
  document.getElementById('reason').textContent=s.reason||'-';
  document.getElementById('score').textContent=(s.score!=null)?s.score.toFixed(2):'-';
  document.getElementById('device').textContent=s.device||'-';
  const age=s.ts?Math.max(0,(Date.now()/1000 - s.ts)):0;
  document.getElementById('age').textContent=age.toFixed(1)+'s ago';
  document.getElementById('cv').classList.toggle('stale', age>5);
  document.getElementById('mode').textContent=(s.mode||'A')+(s.mode==='B'?' (raw image)':' (keypoints only)');
  document.getElementById('bytes').textContent=(s.bytes!=null)?(s.bytes/1024).toFixed(1)+' KB':'-';
}
const es=new EventSource('/stream');
es.onmessage=e=>{try{const s=JSON.parse(e.data);
  if(s.image && s.image!==lastImg){lastImg=s.image; bgImg.src='data:image/jpeg;base64,'+s.image;}
  if(!s.image){bgReady=false; lastImg=null;}
  render(s);}catch(_){}}
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass                                    # quiet

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/state":
            self._json(dict(_get()))
        elif self.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                while True:
                    payload = json.dumps(_get())
                    self.wfile.write(f"data: {payload}\n\n".encode())
                    self.wfile.flush()
                    time.sleep(0.5)
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/pose":
            self.send_error(404)
            return
        n = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            self.send_error(400, "bad json")
            return
        data["ts"] = time.time()
        data["bytes"] = n                       # edge upload size (A vs B contrast)
        with _lock:
            if "image" not in data:             # Mode A: drop any stale Mode-B image
                _state.pop("image", None)
            _state.update(data)
        self._json({"ok": True})

    def _json(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _get():
    with _lock:
        return dict(_state)


def _mock():
    """Cycle standing -> walking -> lying(+ABNORMAL) so you can preview the UI."""
    stand = [[0.50,0.15,.9],[0.48,0.13,.8],[0.52,0.13,.8],[0.46,0.14,.7],[0.54,0.14,.7],
             [0.44,0.28,.9],[0.56,0.28,.9],[0.42,0.42,.8],[0.58,0.42,.8],[0.41,0.55,.7],
             [0.59,0.55,.7],[0.46,0.55,.9],[0.54,0.55,.9],[0.45,0.75,.8],[0.55,0.75,.8],
             [0.45,0.93,.7],[0.55,0.93,.7]]
    lie = [[0.20,0.75,.9],[0.18,0.73,.8],[0.22,0.73,.8],[0.16,0.74,.7],[0.24,0.74,.7],
           [0.34,0.72,.9],[0.34,0.80,.9],[0.48,0.71,.8],[0.48,0.82,.8],[0.60,0.70,.7],
           [0.60,0.83,.7],[0.62,0.73,.9],[0.62,0.80,.9],[0.78,0.73,.8],[0.78,0.80,.8],
           [0.92,0.73,.7],[0.92,0.80,.7]]
    seq = [("standing","normal",stand,[0.40,0.10,0.20,0.86]),
           ("walking","normal",stand,[0.40,0.10,0.20,0.86]),
           ("lying","ABNORMAL",lie,[0.14,0.68,0.82,0.18])]
    i = 0
    while True:
        posture, cond, kp, bbox = seq[i % len(seq)]
        with _lock:
            _state.update({"posture": posture, "condition": cond,
                           "reason": "demo mock feed", "bbox": bbox,
                           "keypoints": kp, "score": 0.9, "device": "mock",
                           "ts": time.time()})
        i += 1
        time.sleep(2.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="generate fake data to preview the UI")
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args()
    if args.mock:
        threading.Thread(target=_mock, daemon=True).start()
        print("[mock] feeding synthetic pose data")
    srv = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(f"[mode3 dashboard] http://localhost:{args.port}   (POST pose -> /pose)")
    srv.serve_forever()


if __name__ == "__main__":
    main()
