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
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>carshorts · review station</title>
<style>
 :root{--bg:#0b0d12;--panel:#141821;--panel2:#1b2130;--txt:#e9ecf2;--mut:#8a93a5;
   --acc:#ffd60a;--ok:#34d399;--warn:#fbbf24;--bad:#f87171;--line:#232a3a}
 *{box-sizing:border-box}body{font:14px/1.45 -apple-system,Inter,sans-serif;margin:0;
   background:var(--bg);color:var(--txt)}
 header{display:flex;align-items:center;gap:12px;padding:14px 22px;
   background:var(--panel);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
 header .logo{font-weight:800;font-size:17px}header .logo em{color:var(--acc);font-style:normal}
 header .hint{margin-left:auto;color:var(--mut);font-size:12px}
 kbd{background:var(--panel2);border:1px solid var(--line);border-radius:5px;padding:1px 6px;font-size:11px}
 .wrap{display:grid;grid-template-columns:270px 330px 1fr;gap:16px;padding:16px;max-width:1500px;margin:0 auto}
 .list .card{background:var(--panel);border:1px solid var(--line);border-radius:12px;
   padding:12px 14px;margin-bottom:10px;cursor:pointer;transition:.15s}
 .card:hover{border-color:var(--acc)}
 .card.sel{border-color:var(--acc);background:var(--panel2)}
 .pill{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.4px;
   border-radius:20px;padding:2px 9px;text-transform:uppercase}
 .pill.awaiting_approval{background:#2b3a55;color:#93c5fd}
 .pill.rework{background:#4a3a12;color:var(--warn)}
 .pill.approved,.pill.published{background:#123a2a;color:var(--ok)}
 .stage{position:sticky;top:74px;align-self:start}
 video{width:100%;border-radius:14px;background:#000;box-shadow:0 8px 30px #0008}
 .stars{margin:12px 0 4px;font-size:26px;cursor:pointer;user-select:none}
 .stars span{color:#3a4256;transition:.1s}.stars span.on{color:var(--acc)}
 .actions{display:flex;gap:10px;margin-top:10px}
 button{flex:1;border:0;border-radius:10px;padding:12px;font-weight:800;font-size:13px;
   cursor:pointer;transition:.15s}button:hover{transform:translateY(-1px)}
 .rework{background:var(--warn);color:#1a1a1a}.approve{background:var(--ok);color:#06281c}
 .beats h3{margin:4px 0 10px;font-size:13px;color:var(--mut);text-transform:uppercase;letter-spacing:.6px}
 .beat{background:var(--panel);border:1px solid var(--line);border-left:4px solid transparent;
   border-radius:12px;padding:12px 14px;margin-bottom:10px;cursor:pointer;transition:.15s}
 .beat.live{border-left-color:var(--acc);background:var(--panel2)}
 .beat .role{font-size:10px;font-weight:800;color:var(--acc);text-transform:uppercase;letter-spacing:.6px}
 .beat .t{float:right;color:var(--mut);font-size:11px}
 .beat p{margin:5px 0 8px}
 .chips{display:flex;flex-wrap:wrap;gap:6px}
 .chip{border:1px solid var(--line);border-radius:20px;padding:3px 11px;font-size:12px;
   color:var(--mut);cursor:pointer;user-select:none;transition:.12s}
 .chip.on{background:var(--bad);border-color:var(--bad);color:#fff}
 textarea{width:100%;background:var(--panel);color:var(--txt);border:1px solid var(--line);
   border-radius:10px;padding:10px;margin-top:6px;resize:vertical}
 .toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:var(--panel2);
   border:1px solid var(--acc);border-radius:12px;padding:12px 22px;font-weight:700;
   opacity:0;pointer-events:none;transition:.25s}.toast.show{opacity:1}
 .empty{color:var(--mut);padding:40px;text-align:center}
</style>
<header><div class="logo">car<em>shorts</em> · review station</div>
 <div class="hint"><kbd>space</kbd> play · <kbd>1–6</kbd> seek beat · <kbd>a</kbd> approve · <kbd>r</kbd> rework</div></header>
<div class="wrap">
 <div class="list" id="list"></div>
 <div class="stage" id="stage"><div class="empty">Select a draft ←</div></div>
 <div class="beats" id="beats"></div>
</div>
<div class="toast" id="toast"></div>
<script>
const ISSUES=["visual mismatch","weak hook","pacing","joke flat","text on screen","audio"];
let cards=[],sel=null,rating=4;
const $=id=>document.getElementById(id);
function toast(m){const t=$('toast');t.textContent=m;t.classList.add('show');
 setTimeout(()=>t.classList.remove('show'),2600);}
async function load(){cards=await(await fetch('/api/queue')).json();renderList();}
function renderList(){
 $('list').innerHTML=cards.map((c,i)=>
  `<div class="card ${sel===i?'sel':''}" onclick="pick(${i})">
    <div style="display:flex;justify-content:space-between;align-items:center">
     <b>${c.car}</b><span class="pill ${c.status}">${c.status.replace('_',' ')}</span></div>
    <div style="color:var(--mut);font-size:12px;margin-top:4px">${c.persona} · ${c.language}</div>
   </div>`).join('')||'<div class="empty">Queue empty.<br>Run <code>pipeline --next</code></div>';
}
function pick(i){
 sel=i;rating=4;renderList();const c=cards[i];
 $('stage').innerHTML=`<video id="vid" src="/video?p=${encodeURIComponent(c.draft)}" controls></video>
  <div class="stars" id="stars"></div>
  <textarea id="notes" rows="3" placeholder="what worked / what didn't…"></textarea>
  <div class="actions">
   <button class="rework" onclick="send('rework')">⟳ Needs rework</button>
   <button class="approve" onclick="send('approve')">✓ Approve → upload</button></div>`;
 $('beats').innerHTML='<h3>Beats — click to seek · tag anything off</h3>'+
  (c.beats||[]).map((b,bi)=>`<div class="beat" id="beat${bi}" onclick="seek(${b.start})">
    <span class="t">${fmt(b.start)}</span><span class="role">${b.role}</span>
    <p>${b.text}</p>
    <div class="chips">${ISSUES.map(t=>
     `<span class="chip" data-beat="${bi}" data-tag="${t}"
        onclick="event.stopPropagation();this.classList.toggle('on')">${t}</span>`).join('')}</div>
   </div>`).join('');
 drawStars();
 const v=$('vid');
 v.addEventListener('timeupdate',()=>{
  (c.beats||[]).forEach((b,bi)=>{
   $('beat'+bi).classList.toggle('live',v.currentTime>=b.start&&v.currentTime<b.start+b.dur);});});
}
function fmt(s){return Math.floor(s/60)+':'+String(Math.floor(s%60)).padStart(2,'0');}
function drawStars(){$('stars').innerHTML=[1,2,3,4,5].map(n=>
 `<span class="${n<=rating?'on':''}" onclick="rating=${n};drawStars()">★</span>`).join('');}
function seek(t){const v=$('vid');if(v){v.currentTime=t;v.play();}}
async function send(verdict){
 if(sel===null)return;const c=cards[sel];
 const tags={};document.querySelectorAll('.chip.on').forEach(x=>{
  (tags[x.dataset.beat]=tags[x.dataset.beat]||[]).push(x.dataset.tag);});
 await fetch('/api/feedback',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({slug:c.slug,verdict,rating,beat_tags:tags,notes:$('notes').value})});
 toast(verdict==='approve'?'Approved — final render + upload started ✓':'Feedback saved — rework queued ⟳');
 sel=null;$('stage').innerHTML='<div class="empty">Select a draft ←</div>';$('beats').innerHTML='';load();
}
document.addEventListener('keydown',e=>{
 if(e.target.tagName==='TEXTAREA')return;
 const v=$('vid');
 if(e.key===' '&&v){e.preventDefault();v.paused?v.play():v.pause();}
 if(/^[1-6]$/.test(e.key)&&sel!==null){const b=cards[sel].beats[+e.key-1];if(b)seek(b.start);}
 if(e.key==='a'&&sel!==null)send('approve');
 if(e.key==='r'&&sel!==null)send('rework');
});
load();
</script>"""


def _queue_cards() -> list[dict]:
    cards = []
    for path in sorted(QUEUE.glob("*.json")) if QUEUE.exists() else []:
        card = json.loads(path.read_text())
        manifest = Path(card.get("draft", "")).with_suffix(".manifest.json")
        beats, cursor = [], 0.0
        if manifest.exists():
            for sec in json.loads(manifest.read_text()).get("sections", []):
                beats.append({"role": sec["role"], "text": sec["text"],
                              "start": round(cursor, 2), "dur": round(sec["duration"], 2)})
                cursor += sec["duration"]
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
