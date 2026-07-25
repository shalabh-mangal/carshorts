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
 .pill.rework,.pill.reworking{background:#4a3a12;color:var(--warn)}
 .pill.rendering{background:#173a52;color:#7dd3fc}
 .pill.reworking::after,.pill.rendering::after{content:"…";animation:p 1s infinite}
 @keyframes p{50%{opacity:.3}}
 .pill.approved,.pill.published{background:#123a2a;color:var(--ok)}
 .pill.approved::after,.pill.publishing::after{content:"…";animation:p 1s infinite}
 .pill.final_review{background:#3a1d52;color:#d8b4fe}
 .pill.publishing{background:#3a1d52;color:#d8b4fe}
 .publish{background:#a855f7;color:#fff}
 .stage{position:sticky;top:74px;align-self:start}
 video{width:100%;border-radius:14px;background:#000;box-shadow:0 8px 30px #0008}
 .busy{background:var(--panel);border:1px dashed var(--warn);border-radius:14px;
   padding:34px 22px;text-align:center}
 .busy .gear{font-size:34px;display:inline-block;animation:spin 2.4s linear infinite}
 @keyframes spin{to{transform:rotate(360deg)}}
 .busy .step{margin-top:10px;font-weight:700;color:var(--warn)}
 .busy .sub{margin-top:6px;color:var(--mut);font-size:12px}
 .stars{margin:12px 0 4px;font-size:26px;cursor:pointer;user-select:none}
 .stars span{color:#3a4256;transition:.1s}.stars span.on{color:var(--acc)}
 .actions{display:flex;gap:10px;margin-top:10px}
 button{flex:1;border:0;border-radius:10px;padding:12px;font-weight:800;font-size:13px;
   cursor:pointer;transition:.15s}button:hover{transform:translateY(-1px)}
 .rework{background:var(--warn);color:#1a1a1a}.approve{background:var(--ok);color:#06281c}
 .savebar{display:none;margin-top:10px}
 .savebar button{background:var(--acc);color:#1a1a1a;width:100%}
 .beats h3{margin:4px 0 10px;font-size:13px;color:var(--mut);text-transform:uppercase;letter-spacing:.6px}
 .beat{background:var(--panel);border:1px solid var(--line);border-left:4px solid transparent;
   border-radius:12px;padding:12px 14px;margin-bottom:10px;cursor:pointer;transition:.15s}
 .beat.live{border-left-color:var(--acc);background:var(--panel2)}
 .beat.edited{border-left-color:#7dd3fc}
 .beat .role{font-size:10px;font-weight:800;color:var(--acc);text-transform:uppercase;letter-spacing:.6px}
 .beat .t{float:right;color:var(--mut);font-size:11px;margin-left:8px}
 .beat .edit{float:right;color:var(--mut);cursor:pointer;font-size:13px;padding:0 4px}
 .beat .edit:hover{color:var(--acc)}
 .beat p{margin:5px 0 8px}
 .beat textarea{font:13px/1.5 ui-monospace,SFMono-Regular,monospace;margin:5px 0 8px}
 .chips{display:flex;flex-wrap:wrap;gap:6px}
 .lbl{font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:.5px;
   width:100%;margin-top:2px}
 .chip{border:1px solid var(--line);border-radius:20px;padding:3px 11px;font-size:12px;
   color:var(--mut);cursor:pointer;user-select:none;transition:.12s}
 .chip.issue.on{background:var(--bad);border-color:var(--bad);color:#fff}
 .chip.win.on{background:var(--ok);border-color:var(--ok);color:#06281c}
 textarea{width:100%;background:var(--panel);color:var(--txt);border:1px solid var(--line);
   border-radius:10px;padding:10px;margin-top:6px;resize:vertical}
 .toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:var(--panel2);
   border:1px solid var(--acc);border-radius:12px;padding:12px 22px;font-weight:700;
   opacity:0;pointer-events:none;transition:.25s}.toast.show{opacity:1}
 .empty{color:var(--mut);padding:40px;text-align:center}
 .nav{display:flex;gap:4px;margin-left:18px}
 .nav b{font-weight:700;font-size:13px;color:var(--mut);cursor:pointer;padding:5px 12px;
   border-radius:8px;transition:.12s}
 .nav b.on{background:var(--panel2);color:var(--acc)}
 .an{max-width:1100px;margin:0 auto;padding:18px}
 .an table{width:100%;border-collapse:collapse;font-size:13px}
 .an th{text-align:left;color:var(--mut);font-size:11px;text-transform:uppercase;
   letter-spacing:.5px;padding:8px 10px;border-bottom:1px solid var(--line)}
 .an td{padding:9px 10px;border-bottom:1px solid var(--line)}
 .an tr:hover td{background:var(--panel)}
 .an .num{text-align:right;font-variant-numeric:tabular-nums}
 .an .car{font-weight:700}
 .an .pill{font-size:10px;padding:1px 7px;border-radius:20px;background:var(--panel2);color:var(--mut)}
 .an .bad{color:var(--bad)} .an .ok{color:var(--ok)} .an .mut{color:var(--mut)}
 .an .beatbar{display:inline-block;height:8px;border-radius:4px;background:var(--bad);
   vertical-align:middle}
 .an .note{color:var(--mut);font-size:12px;margin:6px 0 16px}
</style>
<header><div class="logo">car<em>shorts</em> · review station</div>
 <span class="nav"><b id="nav-review" class="on" onclick="showView('review')">Review</b><b id="nav-analytics" onclick="showView('analytics')">Analytics</b></span>
 <div class="hint"><kbd>space</kbd> play · <kbd>1–6</kbd> seek beat · <kbd>✎</kbd> edit script ·
  <kbd>a</kbd> approve · <kbd>r</kbd> rework</div></header>
<div class="wrap" id="review">
 <div class="list" id="list"></div>
 <div class="stage" id="stage"><div class="empty">Select a draft ←</div></div>
 <div class="beats" id="beats"></div>
</div>
<div class="an" id="analytics" style="display:none"></div>
<div class="toast" id="toast"></div>
<script>
const ISSUES=["visual mismatch","weak hook","pacing","joke flat","text on screen","audio",
  "music","voice","wrong info","too long","boring","cut timing"];
const WINS=["🔥 loved it","great joke","great visual","great pacing"];
const BUSY=s=>['reworking','rendering','approved','publishing'].includes(s);
let cards=[],sel=null,rating=4,edits={},selWasBusy=false;
const $=id=>document.getElementById(id);
function toast(m){const t=$('toast');t.textContent=m;t.classList.add('show');
 setTimeout(()=>t.classList.remove('show'),2600);}
async function load(){cards=await(await fetch('/api/queue')).json();renderList();}
function renderList(){
 $('list').innerHTML=cards.map((c,i)=>
  `<div class="card ${sel===i?'sel':''}" onclick="pick(${i})">
    <div style="display:flex;justify-content:space-between;align-items:center">
     <b>${c.car}</b><span class="pill ${c.status}">${c.status.replace(/_/g,' ')}</span></div>
    <div style="color:var(--mut);font-size:12px;margin-top:4px">${c.persona} · ${c.language}</div>
    ${BUSY(c.status)?`<div style="margin-top:8px;font-size:12px;color:var(--warn)">
      ⚙️ ${c.progress?c.progress.step:'starting…'}<br>
      <span style="color:var(--mut)">${c.progress&&c.progress.at?'since '+c.progress.at.slice(11,16):''}</span></div>`:''}
    ${c.note&&['awaiting_approval','final_review'].includes(c.status)?`<div style="margin-top:8px;font-size:11px;color:var(--ok)">${c.note.slice(0,90)}</div>`:''}
   </div>`).join('')||'<div class="empty">Queue empty.<br>Run <code>pipeline --next</code></div>';
}
function pick(i){
 sel=i;rating=4;edits={};renderList();const c=cards[i];
 selWasBusy=BUSY(c.status);
 if(selWasBusy){
  $('stage').innerHTML=`<div class="busy"><span class="gear">⚙️</span>
   <div class="step">${c.progress?c.progress.step:'working…'}</div>
   <div class="sub">the video file is being rewritten right now —<br>
    player and actions unlock automatically when it lands</div></div>`;
 }else{
  const isFinal=c.status==='final_review';
  $('stage').innerHTML=`<video id="vid" src="/video?p=${encodeURIComponent(c.play||c.draft)}&v=${c.draft_v||0}" controls></video>
   ${isFinal?`<div style="margin-top:8px;font-size:12px;color:#d8b4fe">🎙 PREMIUM FINAL — this exact file ships to YouTube</div>`:''}
   <div class="stars" id="stars"></div>
   <textarea id="notes" rows="3" placeholder="what worked / what didn't…"></textarea>
   <div class="savebar" id="savebar">
    <button onclick="saveScript()">💾 Save script & re-render</button></div>
   <div class="actions">
    <button class="rework" onclick="send('rework')">⟳ Needs rework</button>
    ${isFinal?`<button class="publish" onclick="send('publish')">🚀 Publish to YouTube</button>`
             :`<button class="approve" onclick="send('approve')">✓ Approve → premium final</button>`}</div>`;
 }
 $('beats').innerHTML='<h3>Beats — click to seek · ✎ to rewrite · tag red (fix) or green (keep)</h3>'+
  (c.beats||[]).map((b,bi)=>`<div class="beat" id="beat${bi}" onclick="seek(${b.start})">
    <span class="t">${fmt(b.start)}</span>
    <span class="edit" title="rewrite this line"
      onclick="event.stopPropagation();editBeat(${bi})">✎</span>
    <span class="role">${b.role}</span>
    <p id="btxt${bi}"></p>
    <div class="chips">${ISSUES.map(t=>
     `<span class="chip issue" data-beat="${bi}" data-tag="${t}"
        onclick="event.stopPropagation();this.classList.toggle('on')">${t}</span>`).join('')}
     <span class="lbl"></span>${WINS.map(t=>
     `<span class="chip win" data-beat="${bi}" data-tag="${t}"
        onclick="event.stopPropagation();this.classList.toggle('on')">${t}</span>`).join('')}</div>
   </div>`).join('');
 (c.beats||[]).forEach((b,bi)=>{$('btxt'+bi).textContent=b.text;});
 if(!selWasBusy){
  drawStars();
  const v=$('vid');
  v.addEventListener('timeupdate',()=>{
   (c.beats||[]).forEach((b,bi)=>{const el=$('beat'+bi);
    if(el)el.classList.toggle('live',v.currentTime>=b.start&&v.currentTime<b.start+b.dur);});});
 }
}
function editBeat(bi){
 if(sel!==null&&BUSY(cards[sel].status)){toast('Wait — a render is in flight for this draft');return;}
 const el=$('btxt'+bi);if(!el||el.tagName==='TEXTAREA')return;
 const c=cards[sel];const cur=edits[bi]!==undefined?edits[bi]:c.beats[bi].text;
 const ta=document.createElement('textarea');
 ta.id='btxt'+bi;ta.rows=3;ta.value=cur;
 ta.onclick=e=>e.stopPropagation();
 ta.oninput=()=>{edits[bi]=ta.value;$('beat'+bi).classList.add('edited');
  const s=$('savebar');if(s)s.style.display='block';};
 el.replaceWith(ta);ta.focus();
}
async function saveScript(){
 if(sel===null||!Object.keys(edits).length)return;const c=cards[sel];
 await fetch('/api/script',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({slug:c.slug,texts:edits})});
 toast('Script saved — re-rendering with your words ⟳');
 edits={};sel=null;
 $('stage').innerHTML='<div class="empty">Select a draft ←</div>';$('beats').innerHTML='';load();
}
function fmt(s){return Math.floor(s/60)+':'+String(Math.floor(s%60)).padStart(2,'0');}
function drawStars(){$('stars').innerHTML=[1,2,3,4,5].map(n=>
 `<span class="${n<=rating?'on':''}" onclick="rating=${n};drawStars()">★</span>`).join('');}
function seek(t){const v=$('vid');if(v){v.currentTime=t;v.play();}}
async function send(verdict){
 if(sel===null)return;const c=cards[sel];
 if(BUSY(c.status)){toast('Hold on — a render is in flight for this draft');return;}
 const tags={},wins={};
 document.querySelectorAll('.chip.issue.on').forEach(x=>{
  (tags[x.dataset.beat]=tags[x.dataset.beat]||[]).push(x.dataset.tag);});
 document.querySelectorAll('.chip.win.on').forEach(x=>{
  (wins[x.dataset.beat]=wins[x.dataset.beat]||[]).push(x.dataset.tag);});
 await fetch('/api/feedback',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({slug:c.slug,verdict,rating,beat_tags:tags,beat_wins:wins,
   notes:$('notes')?$('notes').value:''})});
 toast(verdict==='approve'?'Approved — premium final rendering, it comes back here for a last look ✓'
      :verdict==='publish'?'Publishing to YouTube 🚀'
      :'Feedback saved — rework queued ⟳');
 sel=null;$('stage').innerHTML='<div class="empty">Select a draft ←</div>';$('beats').innerHTML='';load();
}
document.addEventListener('keydown',e=>{
 if(e.target.tagName==='TEXTAREA')return;
 const v=$('vid');
 if(e.key===' '&&v){e.preventDefault();v.paused?v.play():v.pause();}
 if(/^[1-6]$/.test(e.key)&&sel!==null){const b=cards[sel].beats[+e.key-1];if(b)seek(b.start);}
 if(e.key==='a'&&sel!==null)send(cards[sel].status==='final_review'?'publish':'approve');
 if(e.key==='r'&&sel!==null)send('rework');
});
function showView(v){
 $('review').style.display = v==='review'?'':'none';
 $('analytics').style.display = v==='analytics'?'block':'none';
 $('nav-review').classList.toggle('on', v==='review');
 $('nav-analytics').classList.toggle('on', v==='analytics');
 if(v==='analytics') loadAnalytics();
}
async function loadAnalytics(){
 const rows = await (await fetch('/api/analytics')).json();
 const el = $('analytics');
 if(!rows.length){ el.innerHTML='<div class="note">No linked videos yet. Publish a video (or link a recipe video_id), then metrics appear after YouTube processes them (~24-48h).</div>'; return; }
 const drops = rows.map(r=> r.drop_by_beat? Math.max(...Object.values(r.drop_by_beat)):0);
 const maxDrop = Math.max(0.001, ...drops);
 const num=v=> v==null?'<span class="mut">—</span>':v;
 let h='<div class="note">Per-video performance from recipe cards (refreshed by the retention watcher). Avg-view% needs ~24-48h and enough views; likes/comments are immediate.</div>';
 h+='<table><thead><tr><th>Video</th><th>Format</th><th class="num">Views</th><th class="num">Likes</th><th class="num">Cmts</th><th class="num">Avg view %</th><th class="num">Like %</th><th>Weakest beat</th></tr></thead><tbody>';
 for(const r of rows){
  const pct=r.avg_view_pct, pc=pct==null?'mut':(pct<50?'bad':'ok');
  let beat='<span class="mut">—</span>';
  if(r.worst_beat && r.drop_by_beat){const w=Math.round(90*(r.drop_by_beat[r.worst_beat]||0)/maxDrop);
   beat=`<span class="beatbar" style="width:${w}px"></span> <b>${r.worst_beat}</b>`;}
  h+=`<tr><td class="car">${r.subject||'?'}<div class="mut" style="font-size:11px">${r.video_id}</div></td>`
   +`<td><span class="pill">${r.hook_type||'?'} · ${r.persona||'?'}</span><div class="mut" style="font-size:11px">${r.duration_s?r.duration_s+'s ':''}${r.word_count?'· '+r.word_count+'w':''}</div></td>`
   +`<td class="num">${num(r.views)}</td><td class="num">${num(r.likes)}</td><td class="num">${num(r.comments)}</td>`
   +`<td class="num ${pc}">${pct==null?'<span class="mut">—</span>':pct.toFixed(1)+'%'}</td>`
   +`<td class="num">${r.like_rate==null?'<span class="mut">—</span>':r.like_rate+'%'}</td><td>${beat}</td></tr>`;
 }
 el.innerHTML=h+'</tbody></table>';
}
load();
setInterval(async()=>{   // live: reworking/rendering -> fresh video appears by itself
 const fresh=await(await fetch('/api/queue')).json();
 const sig=x=>JSON.stringify(x.map(c=>[c.status,c.progress&&c.progress.step,c.draft_v]));
 if(sig(fresh)!==sig(cards)){
  const prevV=sel!==null&&cards[sel]?cards[sel].draft_v:null;
  cards=fresh;renderList();
  if(sel!==null&&cards[sel]){
   const c=cards[sel];
   if(selWasBusy&&!BUSY(c.status)){toast('Fresh render landed — player unlocked ✓');pick(sel);}
   else if(!selWasBusy&&BUSY(c.status))pick(sel);
   else if(prevV!==null&&c.draft_v!==prevV&&!BUSY(c.status)){
    toast('This draft was re-rendered — reloading it ✓');pick(sel);}
  }
 }
},6000);
</script>"""


_healing: set = set()


def _analytics() -> list[dict]:
    """Per-video performance for the analytics tab, read from recipe cards (whose
    metrics are refreshed by retention_watch/analyze). No live API call on page
    load — fast, and works offline once metrics have been fetched at least once."""
    out = []
    rec_dir = Path("data/recipes")
    for path in sorted(rec_dir.glob("*.json")) if rec_dir.exists() else []:
        try:
            r = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not r.get("video_id"):
            continue
        m = r.get("metrics") or {}
        out.append({
            "subject": r.get("subject"), "video_id": r["video_id"],
            "published": r.get("published_at") or r.get("rendered_at"),
            "hook_type": r.get("hook_type"), "persona": r.get("persona"),
            "word_count": r.get("word_count"), "duration_s": r.get("duration_s"),
            "views": m.get("views"), "likes": m.get("likes"),
            "comments": m.get("comments"), "avg_view_pct": m.get("avg_view_pct"),
            "like_rate": m.get("like_rate"), "comment_rate": m.get("comment_rate"),
            "worst_beat": m.get("worst_beat"),
            "drop_by_beat": m.get("drop_by_beat"),
        })
    # highest views first; unknown views sink to the bottom
    out.sort(key=lambda x: (x["views"] is None, -(x["views"] or 0)))
    return out


def _queue_cards() -> list[dict]:
    cards = []
    for path in sorted(QUEUE.glob("*.json")) if QUEUE.exists() else []:
        if path.name.endswith(".progress.json"):
            continue
        card = json.loads(path.read_text())
        # live progress for the FE
        pf = path.with_name(path.stem + ".progress.json")
        if pf.exists():
            card["progress"] = json.loads(pf.read_text())
        # a render lock (draft OR final) overrides everything: file mid-write
        draft = Path(card.get("draft", ""))
        final = Path(card.get("final") or f"out/{card.get('slug','')}_final.mp4")
        if draft.with_suffix(".lock").exists() or final.with_suffix(".lock").exists():
            card["status"] = "rendering"
            card.setdefault("progress", {"step": "encoding video…", "at": ""})
        # the portal plays the FINAL once it exists and the card is past draft
        if card.get("status") in ("final_review", "publishing", "published") \
                and final.exists():
            card["play"] = str(final)
        else:
            card["play"] = card.get("draft", "")
        play = Path(card["play"])
        card["draft_v"] = int(play.stat().st_mtime) if play.exists() else 0
        # SELF-HEAL: a card stuck in legacy 'rework' (submitted to an old
        # server process) gets its worker spawned right here
        if card.get("status") == "rework" and card["slug"] not in _healing:
            _healing.add(card["slug"])
            card["status"] = "reworking"
            path.write_text(json.dumps(card, indent=2))
            subprocess.Popen([sys.executable, "-m", "carshorts.rework",
                              card["slug"]], start_new_session=True)
        manifest = Path(card.get("play") or card.get("draft", "")).with_suffix(".manifest.json")
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
        elif self.path.startswith("/api/analytics"):
            self._send(200, json.dumps(_analytics()).encode())
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
        if self.path.startswith("/api/script"):
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            card_path = QUEUE / f"{body['slug']}.json"
            if not card_path.exists():
                self._send(404, b"{}")
                return
            card = json.loads(card_path.read_text())
            sp = Path(card["script"])
            script = json.loads(sp.read_text())
            for i, text in body.get("texts", {}).items():
                idx = int(i)
                if 0 <= idx < len(script["segments"]) and text.strip():
                    script["segments"][idx]["text"] = text.strip()
            sp.write_text(json.dumps(script, ensure_ascii=False, indent=2))
            card["status"] = "reworking"
            card["note"] = "script edited in portal — re-rendering"
            card_path.write_text(json.dumps(card, indent=2))
            pf = QUEUE / f"{body['slug']}.progress.json"
            pf.write_text(json.dumps({"step": "re-rendering your edited script",
                                      "at": datetime.datetime.now().isoformat(timespec='seconds')}))
            proc_cmd = [sys.executable, "-c", (
                "import subprocess,sys,json,pathlib;"
                f"r=subprocess.run([sys.executable,'-m','carshorts.produce','--script-file',{card['script']!r},"
                f"'--spec',{card['spec']!r},'--skip-factcheck','--persona',{card.get('persona','deadpan')!r},"
                f"'--out',{card['draft']!r}]+{card.get('render_flags', [])!r},"
                "capture_output=True,text=True);"
                f"cp=pathlib.Path({str(card_path)!r});c=json.loads(cp.read_text());"
                "c['status']='awaiting_approval' if r.returncode==0 else 'rework_failed';"
                "c['note']=('edited script rendered'+(' — ⚠ QA flagged' if 'QA FAILED' in (r.stdout or '') else ''));"
                "cp.write_text(json.dumps(c,indent=2));"
                f"pathlib.Path({str(pf)!r}).unlink(missing_ok=True)")]
            subprocess.Popen(proc_cmd, start_new_session=True)
            self._send(200, b'{"ok": true}')
            return
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
            card["status"] = {"approve": "approved",
                              "publish": "publishing"}.get(fb["verdict"], "reworking")
            card_path.write_text(json.dumps(card, indent=2))
            if fb["verdict"] in ("approve", "publish"):
                flag = "--approve" if fb["verdict"] == "approve" else "--publish"
                subprocess.Popen(
                    [sys.executable, "-m", "carshorts.pipeline", flag, fb["slug"]],
                    start_new_session=True)
            else:   # auto-rework picks the feedback up immediately
                subprocess.Popen([sys.executable, "-m", "carshorts.rework",
                                  fb["slug"]], start_new_session=True)
        self._send(200, b'{"ok": true}')


def main() -> None:
    port = 8787
    print(f"review station -> http://localhost:{port}   (Ctrl-C to stop)")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
