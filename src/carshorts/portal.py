"""Review portal — Gate 1 as a product. Local-first, zero hosting, zero deps.

  python -m carshorts.portal            # → http://localhost:8787

Shows every draft awaiting approval (data/queue/) with its video, script and
BEATS (from the manifest). You tag feedback per beat (visual mismatch, weak
hook, pacing, flat joke, text, audio), rate, then either:
  - REWORK  → feedback saved to data/feedback/, card marked rework
  - APPROVE → feedback saved, final render + upload kicked off in background

Feedback JSON is machine-readable — the brain folds it into learnings, so
every tap you make teaches the writer/renderer.
"""
from __future__ import annotations

import datetime
import json
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

QUEUE = Path("data/queue")
FEEDBACK = Path("data/feedback")

PAGE = """<!doctype html><meta charset="utf-8">
<title>carshorts — review station</title>
<style>
 body{font:15px -apple-system,sans-serif;margin:0;background:#0f1115;color:#e8e8ea}
 header{padding:14px 22px;background:#171a21;font-weight:700;font-size:18px}
 .wrap{display:flex;gap:18px;padding:18px}
 .list{width:260px}.card{background:#171a21;border-radius:10px;padding:12px;margin-bottom:10px;cursor:pointer}
 .card.sel{outline:2px solid #ffd60a}.muted{color:#9aa0ab;font-size:12px}
 .main{flex:1;display:flex;gap:18px}
 video{width:300px;border-radius:12px;background:#000}
 .beats{flex:1}.beat{background:#171a21;border-radius:10px;padding:10px 14px;margin-bottom:8px}
 .beat b{color:#ffd60a}.tags{margin-top:6px}
 .tags label{margin-right:10px;font-size:12px;color:#c8ccd4}
 textarea{width:100%;background:#0f1115;color:#e8e8ea;border:1px solid #2a2f3a;border-radius:8px;padding:8px}
 .actions{margin-top:12px;display:flex;gap:10px;align-items:center}
 button{border:0;border-radius:8px;padding:10px 18px;font-weight:700;cursor:pointer}
 .approve{background:#2ecc71}.rework{background:#ffd60a}.rate{font-size:20px}
</style>
<header>carshorts — review station</header>
<div class="wrap">
 <div class="list" id="list"></div>
 <div class="main" id="main"><div class="muted">Select a draft.</div></div>
</div>
<script>
const ISSUES=["visual mismatch","weak hook","pacing","joke flat","text on screen","audio"];
let cards=[],sel=null;
async function load(){cards=await (await fetch('/api/queue')).json();render();}
function render(){
 document.getElementById('list').innerHTML=cards.map((c,i)=>
  `<div class="card ${sel===i?'sel':''}" onclick="pick(${i})"><b>${c.car}</b>
   <div class="muted">${c.persona} · ${c.status}</div></div>`).join('')||'<div class="muted">Queue empty — run pipeline.</div>';
 if(sel===null)return;
 const c=cards[sel];
 document.getElementById('main').innerHTML=`
  <div><video src="/video?p=${encodeURIComponent(c.draft)}" controls></video>
   <div class="actions"><span class="rate">Rating:
    <select id="rating">${[5,4,3,2,1].map(n=>`<option>${n}</option>`).join('')}</select></span></div>
   <div class="actions">
    <button class="rework" onclick="send('rework')">Needs rework</button>
    <button class="approve" onclick="send('approve')">Approve → upload</button></div>
  </div>
  <div class="beats"><h3>Beats — tag anything off</h3>
   ${(c.beats||[]).map((b,bi)=>`<div class="beat"><b>${b.role}</b> ${b.text}
     <div class="tags">${ISSUES.map(t=>
      `<label><input type="checkbox" data-beat="${bi}" value="${t}"> ${t}</label>`).join('')}
     </div></div>`).join('')}
   <h3>Notes</h3><textarea id="notes" rows="3" placeholder="what you liked / didn't…"></textarea>
  </div>`;
}
function pick(i){sel=i;render();}
async function send(verdict){
 const c=cards[sel];
 const tags={};document.querySelectorAll('input[type=checkbox]:checked').forEach(x=>{
  (tags[x.dataset.beat]=tags[x.dataset.beat]||[]).push(x.value);});
 await fetch('/api/feedback',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({slug:c.slug,verdict,rating:+document.getElementById('rating').value,
   beat_tags:tags,notes:document.getElementById('notes').value})});
 alert(verdict==='approve'?'Approved — final render + upload started.':'Feedback saved for rework.');
 sel=null;load();
}
load();
</script>"""


def _queue_cards() -> list[dict]:
    cards = []
    for path in sorted(QUEUE.glob("*.json")) if QUEUE.exists() else []:
        card = json.loads(path.read_text())
        manifest = Path(card.get("draft", "")).with_suffix(".manifest.json")
        beats = []
        if manifest.exists():
            for sec in json.loads(manifest.read_text()).get("sections", []):
                beats.append({"role": sec["role"], "text": sec["text"]})
        card["beats"] = beats
        cards.append(card)
    return cards


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str = "application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        elif self.path.startswith("/api/queue"):
            self._send(200, json.dumps(_queue_cards()).encode())
        elif self.path.startswith("/video"):
            m = re.search(r"p=([^&]+)", self.path)
            from urllib.parse import unquote
            fp = Path(unquote(m.group(1))) if m else None
            if not fp or not fp.exists() or fp.suffix != ".mp4" or ".." in str(fp):
                self._send(404, b"{}")
                return
            data = fp.read_bytes()
            rng = self.headers.get("Range")
            if rng:
                m2 = re.match(r"bytes=(\d+)-(\d*)", rng)
                start = int(m2.group(1))
                end = int(m2.group(2)) if m2.group(2) else len(data) - 1
                chunk = data[start:end + 1]
                self.send_response(206)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
                self.send_header("Content-Length", str(len(chunk)))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                self.wfile.write(chunk)
            else:
                self._send(200, data, "video/mp4")
        else:
            self._send(404, b"{}")

    def do_POST(self):
        if not self.path.startswith("/api/feedback"):
            self._send(404, b"{}")
            return
        length = int(self.headers.get("Content-Length", 0))
        fb = json.loads(self.rfile.read(length))
        FEEDBACK.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        (FEEDBACK / f"{fb['slug']}-{stamp}.json").write_text(json.dumps(fb, indent=2, ensure_ascii=False))
        card_path = QUEUE / f"{fb['slug']}.json"
        if card_path.exists():
            card = json.loads(card_path.read_text())
            card["status"] = "approved" if fb["verdict"] == "approve" else "rework"
            card_path.write_text(json.dumps(card, indent=2))
            if fb["verdict"] == "approve":
                threading.Thread(target=subprocess.call, args=(
                    [sys.executable, "-m", "carshorts.pipeline", "--approve", fb["slug"]],),
                    daemon=True).start()
        self._send(200, b'{"ok": true}')


def main() -> None:
    port = 8787
    print(f"review station -> http://localhost:{port}   (Ctrl-C to stop)")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
