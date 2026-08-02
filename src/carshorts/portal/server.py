"""Review portal — Gate 1 as a product. Local-first, zero hosting, zero deps.

  python -m carshorts.portal            # → http://localhost:8787

Shows every draft awaiting approval (data/queue/) with its video, script and
BEATS (from the manifest). You tag feedback per beat (visual mismatch, weak
hook, pacing, flat joke, text, audio), rate, then either:
  - REWORK  → feedback saved to data/feedback/, card marked rework
  - APPROVE → feedback saved, final render + upload kicked off in background

script_review cards get the SCRIPT BUILDER: mix-and-match beats across every
option (hook from OPT 1, spec from OPT 3, ...), inline text editing, a live
merged-script preview with word/duration checks, one click to generate 3 fresh
options, and "Lock & produce" which renders the mix into a draft automatically.

Feedback JSON is machine-readable — the brain folds it into learnings, so
every tap you make teaches the writer/renderer.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from carshorts.core import paths

QUEUE = paths.QUEUE
FEEDBACK = paths.FEEDBACK

# Per-card write locks: the portal is multi-threaded (ThreadingHTTPServer) and
# several endpoints do read-modify-write on the same card file. Without a lock
# two concurrent clicks can interleave bytes mid-file and corrupt the JSON —
# seen in the wild: "Extra data" in data/queue/*.json.
_CARD_LOCKS: dict[str, threading.Lock] = {}
_CARD_LOCKS_GUARD = threading.Lock()


def _card_lock(slug: str) -> threading.Lock:
    with _CARD_LOCKS_GUARD:
        return _CARD_LOCKS.setdefault(slug, threading.Lock())


def _write_card(card_path: Path, card: dict) -> None:
    """Atomic card write (temp file + rename) — readers never see half a file."""
    tmp = card_path.with_name(card_path.name + ".tmp")
    tmp.write_text(json.dumps(card, indent=2), encoding="utf-8")
    os.replace(tmp, card_path)

PAGE = """<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>carshorts · review station</title>
<style>
 :root{--bg:#07090f;--ink:#eef1f8;--mut:#94a0b8;--acc:#ffd60a;--acc2:#ff9f0a;
   --violet:#8b5cf6;--cyan:#22d3ee;--rose:#fb7185;--green:#34d399;--amber:#fbbf24;
   --red:#f87171;--line:rgba(255,255,255,.09);--panel:rgba(255,255,255,.04);
   --panel2:rgba(255,255,255,.075)}
 *{box-sizing:border-box}html,body{height:100%}
 body{font:14px/1.45 system-ui,'Segoe UI',Roboto,-apple-system,sans-serif;margin:0;
   color:var(--ink);background:var(--bg);overflow:hidden}
 .orbs{position:fixed;inset:0;pointer-events:none;z-index:0;overflow:hidden}
 .orbs i{position:absolute;border-radius:50%;filter:blur(90px);opacity:.34;animation:drift 26s ease-in-out infinite alternate}
 .orbs i:nth-child(1){width:560px;height:560px;background:#ffd60a22;top:-160px;left:-120px}
 .orbs i:nth-child(2){width:620px;height:620px;background:#8b5cf630;top:20%;right:-220px;animation-delay:-9s}
 .orbs i:nth-child(3){width:480px;height:480px;background:#22d3ee24;bottom:-180px;left:30%;animation-delay:-17s}
 @keyframes drift{to{transform:translate(40px,-30px) scale(1.08)}}
 ::-webkit-scrollbar{width:9px;height:9px}::-webkit-scrollbar-thumb{background:#ffffff1c;border-radius:9px}
 ::-webkit-scrollbar-thumb:hover{background:#ffffff2e}::-webkit-scrollbar-track{background:transparent}
 header{position:sticky;top:0;z-index:9;display:flex;align-items:center;gap:14px;padding:12px 20px;
   background:rgba(9,11,20,.82);backdrop-filter:blur(14px);border-bottom:1px solid var(--line)}
 .logo{font-weight:800;font-size:17px;letter-spacing:.3px;
   background:linear-gradient(92deg,#fff 10%,var(--acc) 45%,var(--cyan) 80%);
   -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
 .logo em{font-style:normal;color:var(--acc)}
 .nav{display:flex;gap:4px;margin-left:14px}
 .nav b{font-weight:700;font-size:13px;color:var(--mut);cursor:pointer;padding:6px 14px;
   border-radius:10px;transition:.15s;border:1px solid transparent}
 .nav b:hover{color:var(--ink)}
 .nav b.on{color:var(--acc);background:var(--panel2);border-color:var(--line)}
 .hint{margin-left:auto;color:var(--mut);font-size:12px;display:flex;gap:10px;flex-wrap:wrap}
 kbd{background:var(--panel2);border:1px solid var(--line);border-radius:6px;padding:1px 7px;font-size:11px;font-family:inherit}
 .wrap{position:relative;z-index:1;display:grid;grid-template-columns:248px minmax(0,1fr) 372px;
   gap:14px;padding:16px 20px;max-width:1720px;margin:0 auto;height:calc(100vh - 66px)}
 .list{overflow-y:auto;padding-right:4px}
 .list .card{background:linear-gradient(180deg,var(--panel),rgba(255,255,255,.02));
   border:1px solid var(--line);border-radius:14px;padding:12px 14px;margin-bottom:10px;
   cursor:pointer;transition:.15s}
 .card:hover{border-color:#ffffff2e;transform:translateY(-1px)}
 .card.sel{border-color:var(--acc);box-shadow:0 0 0 1px var(--acc),0 6px 26px #ffd60a1f;background:var(--panel2)}
 .chead{display:flex;justify-content:space-between;align-items:center;gap:8px}
 .chead b{font-size:14px}.csub{color:var(--mut);font-size:12px;margin-top:4px}
 .csub2{color:#b8c3d9;font-size:11.5px;margin-top:3px}
 .cnote{margin-top:8px;font-size:11px;color:var(--green);line-height:1.4}
 .busyline{display:flex;align-items:center;gap:8px;margin-top:8px;font-size:12px;color:var(--amber)}
 .busyline .since{color:var(--mut);font-size:10.5px}
 .pill{display:inline-block;font-size:9.5px;font-weight:800;letter-spacing:.5px;border-radius:20px;
   padding:3px 10px;text-transform:uppercase;white-space:nowrap}
 .pill.awaiting_approval{background:#23375a;color:#93c5fd}
 .pill.rework,.pill.reworking{background:#4a3a12;color:var(--amber)}
 .pill.rendering{background:#173a52;color:#7dd3fc}
 .pill.reworking::after,.pill.rendering::after,.pill.approved::after,.pill.publishing::after{content:"…";animation:p 1s infinite}
 @keyframes p{50%{opacity:.3}}
 .pill.approved,.pill.published{background:#123a2a;color:var(--green)}
 .pill.final_review{background:#3a1d52;color:#d8b4fe}
 .pill.publishing{background:#3a1d52;color:#d8b4fe}
 .pill.script_review{background:#3a2f12;color:var(--acc)}
 .pill.rework_failed{background:#4a1d1d;color:var(--red)}
 .stage{overflow-y:auto;padding-right:4px;scrollbar-gutter:stable}
 .rail{position:sticky;top:0;align-self:start;max-height:calc(100vh - 98px);overflow-y:auto;padding-right:4px}
 video{display:block;margin:2px auto;height:min(80vh,calc(100vh - 120px));width:auto;max-width:100%;
   aspect-ratio:9/16;object-fit:contain;border-radius:16px;background:#000;border:1px solid var(--line);
   box-shadow:0 0 0 1px #ffffff12,0 0 44px #8b5cf61f,0 18px 50px #0009}
 .busy{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;
   gap:14px;text-align:center}
 .ring{width:64px;height:64px;border-radius:50%;border:4px solid #ffffff14;border-top-color:var(--acc);
   border-right-color:var(--violet);animation:spin 1s linear infinite}
 @keyframes spin{to{transform:rotate(360deg)}}
 .busy .step{font-weight:800;color:var(--amber);font-size:15px}
 .busy .sub{color:var(--mut);font-size:12.5px;max-width:420px}
 .stars{margin:12px 0 4px;font-size:26px;cursor:pointer;user-select:none;letter-spacing:3px}
 .stars span{color:#3a4256;transition:.12s;text-shadow:0 0 0 transparent}
 .stars span.on{color:var(--acc);text-shadow:0 0 18px #ffd60a66}
 .actions{display:flex;gap:10px;margin-top:10px}
 .dropzone{border:2px dashed #3a4256;border-radius:12px;padding:16px;text-align:center;font-size:13px;
   color:var(--mut);cursor:pointer;transition:.15s;margin-bottom:8px}
 .dropzone:hover{border-color:#55607a}
 .dropzone.over{border-color:var(--acc);background:#ffd60a14;color:#fff}
 .dropzone b{color:#e5e7eb}
 .dzlink{color:var(--acc);text-decoration:underline}
 .insights{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px;margin:12px 0}
 .ins{background:#151a24;border:1px solid var(--line);border-radius:12px;padding:12px;font-size:13px}
 .insh{font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px}
 .playbook{background:#12161f;border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin-bottom:14px;font-size:13px}
 .playbook ul{margin:8px 0 0;padding-left:18px}.playbook li{margin:4px 0}
 button{border:0;border-radius:11px;padding:12px 14px;font-weight:800;font-size:13px;
   cursor:pointer;transition:.15s;font-family:inherit}
 button:hover{transform:translateY(-1px);filter:brightness(1.07)}
 .rework{background:linear-gradient(135deg,#fbbf24,#f97316);color:#1a1206}
 .approve{background:linear-gradient(135deg,#34d399,#10b981);color:#06281c}
 .publish{background:linear-gradient(135deg,#a855f7,#7c3aed);color:#fff}
 .savebar{display:none;margin-top:10px}
 .savebar button{background:linear-gradient(135deg,var(--acc),var(--acc2));color:#1a1a1a;width:100%}
 textarea{width:100%;background:#0d1019;color:var(--ink);border:1px solid var(--line);
   border-radius:11px;padding:10px;margin-top:6px;resize:vertical;font:13px/1.5 ui-monospace,SFMono-Regular,monospace}
 textarea:focus{outline:none;border-color:var(--acc)}
 .beats h3,.rail h3{margin:4px 0 10px;font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.8px}
 .beat{background:linear-gradient(180deg,var(--panel),rgba(255,255,255,.02));
   border:1px solid var(--line);border-left:3px solid transparent;border-radius:13px;
   padding:11px 13px;margin-bottom:10px;cursor:pointer;transition:.15s}
 .beat:hover{border-color:#ffffff2e}
 .beat.live{border-left-color:var(--acc);background:var(--panel2);box-shadow:0 0 22px #ffd60a12}
 .beat.edited{border-left-color:#7dd3fc}
 .beat .role{font-size:9.5px;font-weight:800;color:var(--acc);text-transform:uppercase;letter-spacing:.7px}
 .beat .t{float:right;color:var(--mut);font-size:11px;margin-left:8px}
 .beat .edit{float:right;color:var(--mut);cursor:pointer;font-size:13px;padding:0 4px}
 .beat .edit:hover{color:var(--acc)}
 .beat p{margin:5px 0 8px;line-height:1.5}
 .chips{display:flex;flex-wrap:wrap;gap:6px}
 .lbl{font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:.5px;width:100%;margin-top:2px}
 .chip{border:1px solid var(--line);border-radius:20px;padding:3px 11px;font-size:11.5px;
   color:var(--mut);cursor:pointer;user-select:none;transition:.12s;background:transparent}
 .chip:hover{border-color:#ffffff40}
 .chip.issue.on{background:linear-gradient(135deg,#f87171,#ef4444);border-color:transparent;color:#fff}
 .chip.win.on{background:linear-gradient(135deg,#34d399,#10b981);border-color:transparent;color:#06281c}
 .toast{position:fixed;bottom:26px;left:50%;transform:translateX(-50%) translateY(8px);
   background:#141a2aee;border:1px solid var(--acc);border-radius:14px;padding:13px 26px;
   font-weight:700;opacity:0;pointer-events:none;transition:.25s;z-index:99;
   box-shadow:0 10px 40px #0009,0 0 30px #ffd60a22}
 .toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
 .empty{color:var(--mut);padding:44px 18px;text-align:center}
 .empty code{background:var(--panel2);border-radius:5px;padding:1px 6px}
 /* ---------------- script builder ---------------- */
 .builder{display:flex;flex-direction:column;gap:14px}
 .bhead{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;
   background:linear-gradient(135deg,#ffffff0a,#ffffff02);border:1px solid var(--line);
   border-radius:16px;padding:16px 18px}
 .bhead h1{margin:0;font-size:21px;letter-spacing:.2px;display:flex;align-items:center;gap:10px}
 .bsub{color:var(--mut);font-size:12.5px;margin-top:6px}
 .bscore{text-align:right;white-space:nowrap}
 .bscore .big{font-size:26px;font-weight:900;
   background:linear-gradient(92deg,var(--acc),var(--cyan));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
 .bscore span{display:block;color:var(--mut);font-size:10.5px;text-transform:uppercase;letter-spacing:.6px;margin-top:2px}
 .optstrip{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
 .optstrip .mini{background:var(--panel2);color:var(--ink);border:1px solid var(--line)}
 .stepbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:12px}
 .stepbar i{color:#ffffff1a;font-style:normal}
 .step{padding:6px 14px;border-radius:20px;border:1px solid var(--line);color:var(--mut);
   font-weight:700;letter-spacing:.4px;text-transform:uppercase;font-size:10.5px;
   background:var(--panel);box-shadow:inset 0 -2px 0 transparent}
 .step.done{color:#0b1220;border-color:transparent;background:linear-gradient(135deg,var(--h),#ffffff55);
   box-shadow:0 0 18px var(--h)}
 .progbar{display:flex;align-items:center;gap:10px;background:#173a52;border:1px solid #2279a830;
   color:#7dd3fc;border-radius:12px;padding:10px 14px;font-size:13px;font-weight:600}
 .progbar .spin{width:16px;height:16px;border-radius:50%;border:3px solid #7dd3fc33;
   border-top-color:#7dd3fc;animation:spin .9s linear infinite}
 .lib{display:flex;flex-direction:column;gap:12px}
 .rolecard{background:linear-gradient(180deg,var(--panel),rgba(255,255,255,.02));
   border:1px solid var(--line);border-radius:16px;padding:14px 16px}
 .rolecard.hot{border-color:var(--acc);box-shadow:0 0 24px #ffd60a14}
 .rchead{display:flex;align-items:center;gap:10px;margin-bottom:10px}
 .rcname{font-weight:900;font-size:12px;text-transform:uppercase;letter-spacing:1px}
 .rcset{color:var(--green);font-size:10.5px;font-weight:700}
 .rcmiss{color:var(--mut);font-size:10.5px}
 .cand{position:relative;border:1px solid var(--line);border-radius:12px;padding:10px 34px 10px 12px;
   margin-bottom:8px;cursor:pointer;transition:.13s;background:rgba(0,0,0,.16)}
 .cand:hover{border-color:#ffffff30;transform:translateX(2px)}
 .cand.sel{border-color:var(--acc);background:#ffd60a0d;box-shadow:0 0 0 1px #ffd60a55,0 0 20px #ffd60a14}
 .cand .ck{position:absolute;right:10px;top:10px;color:var(--acc);font-weight:900;font-size:15px}
 .copt{display:inline-block;font-size:9px;font-weight:900;letter-spacing:.6px;border-radius:6px;
   padding:2px 8px;color:#0b1220;margin-bottom:6px}
 .copt.o0{background:#ffd60a}.copt.o1{background:#22d3ee}.copt.o2{background:#8b5cf6;color:#fff}
 .copt.o3{background:#fb7185;color:#2b0a10}.copt.o4{background:#34d399}.copt.o5{background:#fbbf24}
 .ctext{font-size:13.5px;line-height:1.5}
 .cchips{display:flex;flex-wrap:wrap;gap:5px;margin-top:7px}
 .cc{font-size:9.5px;border-radius:6px;padding:1px 7px;background:var(--panel2);color:var(--mut)}
 .cc.fact{color:#7dd3fc}.cc.pop{color:#d8b4fe}
 .cedit{position:absolute;right:10px;bottom:10px;color:var(--mut);font-size:14px;padding:2px 6px}
 .cedit:hover{color:var(--acc)}
 .ceditbtns{display:flex;gap:8px;margin-top:8px}
 .mini{background:var(--panel2);color:var(--ink);border:1px solid var(--line);border-radius:10px;
   padding:8px 14px;font-size:12px;font-weight:700}
 .mini.ok{background:linear-gradient(135deg,#34d399,#10b981);color:#06281c;border:none}
 .mini.full{width:100%;padding:11px;font-size:12.5px;margin-top:14px}
 .custom{margin-top:6px;padding-top:10px;border-top:1px dashed #ffffff14}
 .custom textarea{margin-top:0}
 /* ---------------- builder rail ---------------- */
 .railcard{background:linear-gradient(180deg,var(--panel),rgba(255,255,255,.02));
   border:1px solid var(--line);border-radius:16px;padding:14px 16px}
 .railt{display:flex;align-items:baseline;justify-content:space-between;margin:2px 0 10px}
 .railt h3{margin:0}
 .stc{font-size:12px;font-weight:800;color:var(--mut)}
 .stc.warn{color:var(--amber)}.stc.bad{color:var(--red)}.stc.ok{color:var(--green)}
 .mixrow{display:grid;grid-template-columns:52px 1fr;gap:10px;padding:9px 10px;border-radius:11px;
   border:1px solid var(--line);margin-bottom:8px;background:rgba(0,0,0,.16)}
 .mixrow.set{border-left:3px solid var(--h)}
 .mixrow.empty{border-style:dashed;opacity:.7}
 .mixrole{font-size:9px;font-weight:900;letter-spacing:.7px;color:var(--h);text-transform:uppercase;padding-top:3px}
 .mixbody{font-size:12.5px;line-height:1.45;position:relative;padding-right:22px}
 .mixbody i{color:var(--mut);font-style:normal;font-size:12px}
 .mxact{position:absolute;right:0;top:0;color:var(--mut);cursor:pointer;font-size:13px;padding:0 3px}
 .mxact:hover{color:var(--acc)}
 .okbar,.warnbar{font-size:11.5px;border-radius:10px;padding:8px 12px;margin:10px 0;font-weight:700}
 .okbar{background:#123a2a;color:var(--green)}
 .warnbar{background:#4a3a12;color:var(--amber)}
 .warnbar.bad{background:#4a1d1d;color:var(--red)}
 .rvvoice{border:1px solid var(--line);border-radius:13px;padding:11px 13px;margin-bottom:9px;
   background:rgba(0,0,0,.16);transition:.13s}
 .rvvoice.on{border-color:var(--green);box-shadow:0 0 18px #34d39914}
 .rvhd{display:flex;align-items:center;gap:10px;margin-bottom:8px}
 .rvname{font-weight:800;font-size:13px}
 .rvtick{color:var(--green);font-size:11px;font-weight:800}
 .ruse{margin-left:auto;width:auto;padding:6px 16px;font-size:11.5px;background:var(--panel2);color:var(--ink)}
 .ruse.done{background:linear-gradient(135deg,#34d399,#10b981);color:#06281c}
 .rvvoice audio{width:100%;height:36px}
 .lock{width:100%;margin-top:10px;padding:14px;font-size:14px;
   background:linear-gradient(135deg,var(--acc),var(--acc2) 55%,#ff6a00);color:#1a1206;
   box-shadow:0 6px 30px #ff9f0a3d}
 .lock:hover{filter:brightness(1.08)}
 .lock.off{background:#ffffff12;color:#ffffff55;box-shadow:none;cursor:not-allowed}
 /* ---------------- analytics ---------------- */
 .an{position:relative;z-index:1;max-width:1180px;margin:0 auto;padding:20px;height:calc(100vh - 66px);overflow-y:auto}
 .an table{width:100%;border-collapse:collapse;font-size:13px;background:linear-gradient(180deg,var(--panel),rgba(255,255,255,.02));
   border:1px solid var(--line);border-radius:16px;overflow:hidden}
 .an th{text-align:left;color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.5px;
   padding:11px 12px;border-bottom:1px solid var(--line);background:rgba(255,255,255,.02)}
 .an td{padding:11px 12px;border-bottom:1px solid #ffffff0d}
 .an tr:hover td{background:#ffffff05}
 .an .num{text-align:right;font-variant-numeric:tabular-nums}
 .an .car{font-weight:800}
 .an .pill{font-size:9.5px;padding:2px 9px;border-radius:20px;background:var(--panel2);color:var(--mut)}
 .an .bad{color:var(--red)} .an .ok{color:var(--green)} .an .mut{color:var(--mut)}
 .an .beatbar{display:inline-block;height:8px;border-radius:4px;vertical-align:middle;
   background:linear-gradient(90deg,var(--red),var(--amber))}
 .an .note{color:var(--mut);font-size:12px;margin:4px 0 16px;line-height:1.5}
</style>
<header><div class="logo">car<em>shorts</em> · review station</div>
 <span class="nav"><b id="nav-review" class="on" onclick="showView('review')">Review</b><b id="nav-analytics" onclick="showView('analytics')">Analytics</b></span>
 <div class="hint"><span><kbd>space</kbd> play</span><span><kbd>1–6</kbd> seek</span><span><kbd>a</kbd> approve</span><span><kbd>r</kbd> rework</span><span><kbd>m</kbd> more options</span></div></header>
<div class="orbs"><i></i><i></i><i></i></div>
<div class="wrap" id="review">
 <div class="list" id="list"></div>
 <div class="stage" id="stage"><div class="empty">Select a draft ←</div></div>
 <div class="rail" id="beats"></div>
</div>
<div class="an" id="analytics" style="display:none"></div>
<div class="toast" id="toast"></div>
<script>
const ISSUES=["visual mismatch","weak hook","pacing","joke flat","text on screen","audio",
  "music","voice","wrong info","too long","boring","cut timing"];
const WINS=["🔥 loved it","great joke","great visual","great pacing"];
const ROLES=[{k:"hook",n:"Hook"},{k:"spec",n:"Spec"},{k:"value",n:"Value"},{k:"peak",n:"Peak"},{k:"cta",n:"CTA"}];
const RHUE={hook:"#fbbf24",spec:"#22d3ee",value:"#8b5cf6",peak:"#fb7185",cta:"#34d399"};
const BUSY=s=>["reworking","rendering","approved","publishing"].includes(s);
let cards=[],sel=null,rating=4,edits={},build={},editing=null,selWasBusy=false;
const $=id=>document.getElementById(id);
const esc=s=>String(s??"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
const fmt=s=>Math.floor(s/60)+":"+String(Math.floor(s%60)).padStart(2,"0");
function toast(m){const t=$("toast");t.textContent=m;t.classList.add("show");
 setTimeout(()=>t.classList.remove("show"),3000);}
async function load(){cards=await(await fetch("/api/queue")).json();renderList();}
function renderList(){
 $("list").innerHTML=cards.map((c,i)=>{
  const busy=BUSY(c.status);
  return `<div class="card ${sel===i?"sel":""}" onclick="pick(${i})">
    <div class="chead"><b>${esc(c.car)}</b><span class="pill ${c.status}">${c.status.replace(/_/g," ")}</span></div>
    <div class="csub">${esc(c.persona)} · ${esc(c.language)}${c.voice?" · 🎙 "+esc(c.voice):""}</div>
    ${c.target?`<div class="csub2">🎯 ${esc(String(c.target.views??""))} views · ${esc(String(c.target.likes??""))} likes${c.target.comments?` · ${esc(String(c.target.comments))} cmts`:""}</div>`:""}
    ${busy?`<div class="busyline"><span class="ring" style="width:13px;height:13px;border-width:2px;display:inline-block"></span> ${esc(c.progress&&c.progress.step||"working…")}${c.progress&&c.progress.at?` <span class="since">· since ${c.progress.at.slice(11,16)}</span>`:""}</div>`:""}
    ${c.note&&["awaiting_approval","final_review"].includes(c.status)?`<div class="cnote">${esc(c.note.slice(0,110))}</div>`:""}
   </div>`;}).join("")||`<div class="empty">Queue empty.<br>Run <code>pipeline --next</code></div>`;
}
/* ================= SCRIPT BUILDER ================= */
function fillState(){const filled=()=>ROLES.filter(r=>build[r.k]&&build[r.k].text&&build[r.k].text.trim()).length;
 const words=()=>ROLES.reduce((n,r)=>n+(build[r.k]&&build[r.k].text?build[r.k].text.trim().split(/\\s+/).length:0),0);
 const est=()=>Math.round(words()*0.5+filled()*1.2);
 const canLock=()=>{const f=filled();return build.hook&&build.hook.text.trim()&&build.cta&&build.cta.text.trim()&&f>=4;};
 return {filled,words,est,canLock};}
function persistBuild(role){
 const b=build[role];if(!b)return;
 fetch("/api/build",{method:"POST",headers:{"Content-Type":"application/json"},
  body:JSON.stringify({slug:cards[sel].slug,role,beat:b})}).catch(()=>{});
}
function renderBuilder(c){
 const st=fillState();const opts=c.options||[];const voices=c.voice_options||[];
 const {filled,words,est,canLock}=st;
 const both=(c.script_choice?1:0)+(c.voice?1:0);
 const candRow=(role,oi,bi,b)=>{
  const key=role+":"+oi+":"+bi;
  const isSel=build[role]&&build[role].text===b.text;
  const chips=[];
  (b.cited_spec_names||[]).forEach(x=>chips.push(`<span class="cc fact">✓ ${esc(x)}</span>`));
  (b.pops||[]).forEach(p=>chips.push(`<span class="cc pop">${esc(typeof p==="string"?p:(p.show||p.anchor||""))}</span>`));
  const ctr=`<div class="cand ${isSel?"sel":""}" onclick="pickBeat('${role}',${oi},${bi})">
   <span class="copt o${oi%6}">OPT ${oi+1}</span>${isSel?'<span class="ck">✓</span>':""}
   <div class="ctext">${esc(b.text)}</div>
   ${chips.length?`<div class="cchips">${chips.join("")}</div>`:""}
   <span class="cedit" title="edit this line" onclick="event.stopPropagation();pickBeat('${role}',${oi},${bi},true)">✎</span>
  </div>`;
  if(editing===key)return `<div class="cand sel">
   <span class="copt o${oi%6}">OPT ${oi+1} · EDIT</span>
   <textarea id="ce-${role}" rows="3">${esc(b.text)}</textarea>
   <div class="ceditbtns"><button class="mini ok" onclick="saveBeat('${role}',${oi},${bi})">Save to mix</button>
   <button class="mini" onclick="cancelEdit()">Cancel</button></div></div>`;
  return ctr;};
 $("stage").innerHTML=`<div class="builder">
  <div class="bhead">
   <div><h1>${esc(c.car)} <span class="pill ${c.status}">${c.status.replace(/_/g," ")}</span></h1>
    <div class="bsub">${esc(c.persona)} · ${esc(c.language)}${c.target?` · 🎯 ${esc(String(c.target.views??""))} views / ${esc(String(c.target.likes??""))} likes${c.target.comments?` / ${esc(String(c.target.comments))} cmts`:""}`:""}</div>
    ${opts.length?`<div class="optstrip">${opts.map((o,oi)=>`<button class="mini" onclick="useWhole(${oi})">Use OPT ${oi+1} as-is</button>`).join("")}</div>`:""}</div>
   <div class="bscore"><span class="big">${both}/2</span><span>script + voice</span></div>
  </div>
  ${c.progress?`<div class="progbar"><span class="spin"></span>${esc(c.progress.step)}</div>`:""}
  <div class="stepbar">${ROLES.map(r=>{
   const set=build[r.k]&&build[r.k].text&&build[r.k].text.trim();
   return `<span class="step ${set?"done":""}" style="--h:${RHUE[r.k]}">${set?"✓ ":""}${r.n}</span>`;}).join("<i>→</i>")}</div>
  <div class="lib">
   ${ROLES.map(r=>{const set=build[r.k]&&build[r.k].text&&build[r.k].text.trim();
    return `<div class="rolecard ${!set?"hot":""}" id="role-${r.k}">
     <div class="rchead"><span class="rcname" style="color:${RHUE[r.k]}">${r.n}</span>
      ${set?`<span class="rcset">picked ✓</span><span class="cedit" style="position:static" onclick="clearRole('${r.k}')">✕ clear</span>`
           :`<span class="rcmiss">pick one ↓</span>`}</div>
     ${opts.map((o,oi)=>o.beats.filter(b=>b.role===r.k).map((b,bi)=>candRow(r.k,oi,bi,b)).join("")).join("")}
     <div class="custom"><textarea id="ct-${r.k}" rows="2" placeholder="or type your own ${r.n} beat…"></textarea>
      <button class="mini" style="margin-top:6px" onclick="addCustom('${r.k}')">Use my text</button></div>
    </div>`;}).join("")}
  </div>
 </div>`;
 $("beats").innerHTML=`<div class="railcard">
  <div class="railt"><h3>Your script</h3><span class="stc ${est()>63?"bad":words()>120?"warn":"ok"}">${words()}w · ~${est()}s</span></div>
  ${ROLES.map(r=>{const v=build[r.k];
   if(editing==="mix:"+r.k)return `<div class="mixrow set" style="--h:${RHUE[r.k]}"><span class="mixrole">${r.n}</span>
    <div><textarea id="mx-${r.k}" rows="3">${esc(v?v.text:"")}</textarea>
     <div class="ceditbtns"><button class="mini ok" onclick="saveMix('${r.k}')">Save</button>
     <button class="mini" onclick="cancelEdit()">Cancel</button></div></div></div>`;
   return `<div class="mixrow ${v?"set":"empty"}" style="--h:${RHUE[r.k]}">
    <span class="mixrole">${r.n}</span>
    <div class="mixbody">${v?`<span>${esc(v.text)}</span><span class="mxact" onclick="editMix('${r.k}')">✎</span>`:`<i>pick from the library ←</i>`}</div></div>`;}).join("")}
  ${est()>63?`<div class="warnbar bad">⚠ ~${est()}s — over the 63s QA cap, trim words before locking</div>`
   :words()>120?`<div class="warnbar">${words()} words — above the comfort cap, consider trimming</div>`
   :`<div class="okbar">✓ ${words()} words · ~${est()}s — inside the Shorts sweet spot</div>`}
  <div class="railt"><h3>Voice</h3></div>
  ${voices.length?voices.map((v,vi)=>`<div class="rvvoice ${c.voice===v.label?"on":""}">
    <div class="rvhd"><span class="rvname">🎙 ${esc(v.label.charAt(0).toUpperCase()+v.label.slice(1))}${c.voice===v.label?' <span class="rvtick">✓</span>':""}</span>
     <button class="ruse ${c.voice===v.label?"done":""}" onclick="pickVoice(${vi})">${c.voice===v.label?"Using":"Use"}</button></div>
    <audio controls preload="none" src="/video?p=${encodeURIComponent(v.file)}"></audio></div>`).join("")
  :`<div class="empty">No voice samples yet — generating.</div>`}
  <button class="mini full" onclick="moreOpts()">↻ Generate 3 more options</button>
  <button class="lock ${canLock()?"":"off"}" onclick="lockScript()">🔒 Lock &amp; produce draft${canLock()?"":` (${5-filled()} beats left)`}</button>
 </div>`+contentDropHTML(c,"builder");
}
function pickBeat(role,oi,bi,editIt){
 const c=cards[sel];const b=c.options[oi].beats.filter(x=>x.role===role)[bi];
 if(!b)return;
 if(editIt){editing=role+":"+oi+":"+bi;renderBuilder(c);const ta=$("ce-"+role);if(ta)ta.focus();return;}
 editing=null;
 build[b.role]={role:b.role,text:b.text,cited_spec_names:b.cited_spec_names||[],pops:b.pops||[]};
 persistBuild(b.role);renderBuilder(c);
}
function saveBeat(role,oi,bi){
 const c=cards[sel];const b=c.options[oi].beats.filter(x=>x.role===role)[bi];const ta=$("ce-"+role);
 if(!b)return;
 build[b.role]={role:b.role,text:ta?ta.value.trim():b.text,cited_spec_names:b.cited_spec_names||[],pops:b.pops||[]};
 editing=null;persistBuild(b.role);renderBuilder(c);toast("beat edited ✓");
}
function addCustom(role){
 const ta=$("ct-"+role);const t=ta?ta.value.trim():"";if(!t){toast("type something first");return;}
 build[role]={role,text:t,cited_spec_names:[],pops:[]};editing=null;persistBuild(role);renderBuilder(cards[sel]);
}
function clearRole(role){delete build[role];editing=null;persistBuild(role);renderBuilder(cards[sel]);}
function cancelEdit(){editing=null;renderBuilder(cards[sel]);}
function useWhole(oi){
 const c=cards[sel];editing=null;
 c.options[oi].beats.forEach(b=>{build[b.role]={role:b.role,text:b.text,cited_spec_names:b.cited_spec_names||[],pops:b.pops||[]};});
 Object.keys(build).forEach(r=>persistBuild(r));renderBuilder(c);toast("OPT "+(oi+1)+" loaded into your mix ✓");
}
function editMix(role){editing="mix:"+role;renderBuilder(cards[sel]);const ta=$("mx-"+role);if(ta)ta.focus();}
function saveMix(role){
 const ta=$("mx-"+role);if(!ta)return;
 if(build[role])build[role].text=ta.value.trim();else build[role]={role,text:ta.value.trim(),cited_spec_names:[],pops:[]};
 editing=null;persistBuild(role);renderBuilder(cards[sel]);toast("script updated ✓");
}
function moreOpts(){
 if(sel===null)return;
 fetch("/api/scripts/more",{method:"POST",headers:{"Content-Type":"application/json"},
  body:JSON.stringify({slug:cards[sel].slug})}).then(()=>toast("generating 3 fresh options — they appear in the library in ~1 min ⟳"));
}
function lockScript(){
 const c=cards[sel];const st=fillState();if(!st.canLock()){toast("lock needs Hook + CTA + at least 4 beats");return;}
 fetch("/api/build/lock",{method:"POST",headers:{"Content-Type":"application/json"},
  body:JSON.stringify({slug:c.slug,build})})
  .then(r=>{if(!r.ok)throw 0;toast("mix locked — producing the free draft ⟳");})
  .catch(()=>toast("lock failed — see portal.log"));
}
function pickVoice(vi){
 const c=cards[sel];const v=c.voice_options[vi];
 c.voice=v.label;c.voice_file=v.file;      // optimistic: reflect in the panel instantly
 renderBuilder(c);                          // (load() only refreshes the LEFT list, not this panel)
 fetch("/api/pick",{method:"POST",headers:{"Content-Type":"application/json"},
  body:JSON.stringify({slug:c.slug,kind:"voice",choice:v.file,label:v.label})})
  .then(r=>{if(!r.ok)throw 0;toast("voice chosen ✓");})
  .catch(()=>toast("voice save failed — see portal.log"));
}
/* ================= VIDEO REVIEW ================= */
function renderReview(c){
 const isFinal=c.status==="final_review";
 $("stage").innerHTML=`<video id="vid" src="/video?p=${encodeURIComponent(c.play||c.draft)}&v=${c.draft_v||0}" controls></video>
  ${isFinal?`<div style="margin:10px 2px;font-size:12.5px;color:#d8b4fe;font-weight:700">🎙 PREMIUM FINAL — this exact file ships to YouTube</div>`:""}
  <div class="stars" id="stars"></div>
  <textarea id="notes" rows="3" placeholder="what worked / what didn't…"></textarea>
  <div class="savebar" id="savebar"><button onclick="saveScript()">💾 Save script &amp; re-render</button></div>
  <div class="actions">
   ${!isFinal?`<button class="mini" onclick="reopen()">← Change script / voice</button>`:""}
   <button class="rework" onclick="send('rework')">⟳ Needs rework</button>
   ${isFinal?`<button class="publish" onclick="send('publish')">🚀 Publish to YouTube</button>`
            :`<button class="approve" onclick="send('approve')">✓ Approve → premium final</button>`}</div>`;
 $("beats").innerHTML=`<div class="railcard"><h3>Beats — click to seek · ✎ to rewrite · tag red (fix) / green (keep)</h3>`+
  (c.beats||[]).map((b,bi)=>`<div class="beat" id="beat${bi}" onclick="seek(${b.start})">
    <span class="t">${fmt(b.start)}</span>
    <span class="edit" title="rewrite this line" onclick="event.stopPropagation();editBeat(${bi})">✎</span>
    <span class="role">${b.role}</span>
    <p id="btxt${bi}"></p>
    <div class="chips">${ISSUES.map(t=>
     `<span class="chip issue" data-beat="${bi}" data-tag="${t}"
        onclick="event.stopPropagation();this.classList.toggle('on')">${t}</span>`).join("")}
     <span class="lbl"></span>${WINS.map(t=>
     `<span class="chip win" data-beat="${bi}" data-tag="${t}"
        onclick="event.stopPropagation();this.classList.toggle('on')">${t}</span>`).join("")}</div>
   </div>`).join("")+"</div>"+contentDropHTML(c,"review");
 (c.beats||[]).forEach((b,bi)=>{const el=$("btxt"+bi);if(el)el.textContent=b.text;});
 drawStars();
 const v=$("vid");
 if(v)v.addEventListener("timeupdate",()=>{
  (c.beats||[]).forEach((b,bi)=>{const el=$("beat"+bi);
   if(el)el.classList.toggle("live",v.currentTime>=b.start&&v.currentTime<b.start+b.dur);});});
}
/* ============ CONTENT DROP (owner footage + jokes) ============ */
function contentDropHTML(c,mode){
 const clips=c.own_clips||[];
 const rerender=(mode!=="builder")
   ?`<button class="lock" style="flex:1;min-width:180px" onclick="reRender()">🔒 Re-render with my footage + fresh B-roll</button>`
   :`<span class="mut" style="font-size:11.5px;align-self:center">used automatically when you Lock ↓</span>`;
 return `<div class="railcard" style="margin-top:12px">
   <h3>🎬 Your footage &amp; jokes</h3>
   <div class="mut" style="font-size:12px;margin-bottom:8px">Add real ${esc(c.car)} clips at any step — they auto-fit vertical and replace stock. Jokes/notes guide the edit.</div>
   <div id="ownlist" style="font-size:12px;margin-bottom:8px">${clips.length?clips.map(f=>`<span class="cc fact">🎞 ${esc(f)}</span>`).join(" "):'<i class="mut">no clips yet — stock B-roll will be used</i>'}</div>
   <div id="dropzone" class="dropzone" onclick="document.getElementById('dropfiles').click()"
        ondragover="dzOver(event)" ondragleave="dzLeave(event)" ondrop="dzDrop(event)">
     ⬇ <b>Drag &amp; drop clips here</b> — or <span class="dzlink">browse</span><br>
     <span class="mut" style="font-size:11px">mp4 / mov / webm · multiple at once</span>
     <input id="dropfiles" type="file" accept="video/*,.mp4,.mov,.m4v,.webm,.mkv" multiple style="display:none" onchange="uploadFiles(this.files)">
   </div>
   <textarea id="dropnotes" rows="3" placeholder="jokes / notes / what to emphasise…">${esc(c.content_notes||"")}</textarea>
   <div style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap">
    <button class="mini ok" onclick="uploadFiles([])">💬 Save notes</button>
    ${rerender}
   </div>
 </div>`;
}
function dzOver(e){e.preventDefault();e.currentTarget.classList.add("over");}
function dzLeave(e){e.currentTarget.classList.remove("over");}
function dzDrop(e){e.preventDefault();e.currentTarget.classList.remove("over");
 uploadFiles((e.dataTransfer&&e.dataTransfer.files)||[]);}
function uploadFiles(fileList){       // drag-drop OR browse OR notes-only; multiple OK
 const c=cards[sel];const fd=new FormData();
 fd.append("slug",c.slug);fd.append("notes",($("dropnotes")?$("dropnotes").value:"")||"");
 let n=0;for(const f of (fileList||[])){fd.append("files",f);n++;}
 toast(n?("uploading "+n+" clip(s)…"):"saving notes…");
 fetch("/api/upload",{method:"POST",body:fd}).then(r=>r.json()).then(j=>{
  const s=(j.saved||[]).length, sk=(j.skipped||[]).length;
  toast(s?("added "+s+" clip(s) ✓"+(sk?(" · "+sk+" skipped (not video)"):"")):"notes saved ✓");
  load().then(()=>{if(sel!==null)pick(sel);});
 }).catch(()=>toast("upload failed — see portal.log"));
}
function reRender(){
 const c=cards[sel];
 fetch("/api/build/lock",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({slug:c.slug})})
  .then(r=>{if(!r.ok)throw 0;toast("re-rendering with your footage + fresh B-roll ⟳");})
  .catch(()=>toast("re-render failed — see portal.log"));
}
function reopen(){    // back to the script + voice builder, keeping the current mix
 const c=cards[sel];
 fetch("/api/reopen",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({slug:c.slug})})
  .then(r=>{if(!r.ok)throw 0;toast("back to script & voice — your mix is preserved ✎");
            load().then(()=>{if(sel!==null)pick(sel);});})
  .catch(()=>toast("couldn't reopen — see portal.log"));
}
function pick(i){
 sel=i;rating=4;edits={};editing=null;build={};renderList();const c=cards[i];
 selWasBusy=BUSY(c.status);
 if(c.status==="script_review"){
  build=JSON.parse(JSON.stringify(c.script_build||{}));renderBuilder(c);return;}
 if(selWasBusy){
  $("stage").innerHTML=`<div class="busy"><div class="ring"></div>
   <div class="step">${c.progress&&c.progress.step||"working…"}</div>
   <div class="sub">the video is being written right now —<br>
    player and actions unlock automatically when it lands</div></div>`;
  $("beats").innerHTML="";
 }else renderReview(c);
}
function editBeat(bi){
 if(sel!==null&&BUSY(cards[sel].status)){toast("Wait — a render is in flight for this draft");return;}
 const el=$("btxt"+bi);if(!el||el.tagName==="TEXTAREA")return;
 const c=cards[sel];const cur=edits[bi]!==undefined?edits[bi]:c.beats[bi].text;
 const ta=document.createElement("textarea");
 ta.id="btxt"+bi;ta.rows=3;ta.value=cur;
 ta.onclick=e=>e.stopPropagation();
 ta.oninput=()=>{edits[bi]=ta.value;$("beat"+bi).classList.add("edited");
  const s=$("savebar");if(s)s.style.display="block";};
 el.replaceWith(ta);ta.focus();
}
async function saveScript(){
 if(sel===null||!Object.keys(edits).length)return;const c=cards[sel];
 await fetch("/api/script",{method:"POST",headers:{"Content-Type":"application/json"},
  body:JSON.stringify({slug:c.slug,texts:edits})});
 toast("Script saved — re-rendering with your words ⟳");
 edits={};sel=null;
 $("stage").innerHTML='<div class="empty">Select a draft ←</div>';$("beats").innerHTML="";load();
}
function drawStars(){$("stars").innerHTML=[1,2,3,4,5].map(n=>
 `<span class="${n<=rating?"on":""}" onclick="rating=${n};drawStars()">★</span>`).join("");}
function seek(t){const v=$("vid");if(v){v.currentTime=t;v.play();}}
async function send(verdict){
 if(sel===null)return;const c=cards[sel];
 if(BUSY(c.status)){toast("Hold on — a render is in flight for this draft");return;}
 const tags={},wins={};
 document.querySelectorAll(".chip.issue.on").forEach(x=>{
  (tags[x.dataset.beat]=tags[x.dataset.beat]||[]).push(x.dataset.tag);});
 document.querySelectorAll(".chip.win.on").forEach(x=>{
  (wins[x.dataset.beat]=wins[x.dataset.beat]||[]).push(x.dataset.tag);});
 await fetch("/api/feedback",{method:"POST",headers:{"Content-Type":"application/json"},
  body:JSON.stringify({slug:c.slug,verdict,rating,beat_tags:tags,beat_wins:wins,
   notes:$("notes")?$("notes").value:""})});
 toast(verdict==="approve"?"Approved — premium final rendering, it comes back here for a last look ✓"
      :verdict==="publish"?"Publishing to YouTube 🚀"
      :"Feedback saved — rework queued ⟳");
 sel=null;$("stage").innerHTML='<div class="empty">Select a draft ←</div>';$("beats").innerHTML="";load();
}
document.addEventListener("keydown",e=>{
 if(e.target.tagName==="TEXTAREA")return;
 const v=$("vid");
 if(e.key===" "&&v){e.preventDefault();v.paused?v.play():v.pause();}
 if(/^[1-6]$/.test(e.key)&&sel!==null&&cards[sel].status!=="script_review"){const b=cards[sel].beats[+e.key-1];if(b)seek(b.start);}
 if(e.key==="m"&&sel!==null&&cards[sel].status==="script_review")moreOpts();
 if(e.key==="a"&&sel!==null&&!BUSY(cards[sel].status)&&cards[sel].status!=="script_review")
  send(cards[sel].status==="final_review"?"publish":"approve");
 if(e.key==="r"&&sel!==null&&!BUSY(cards[sel].status)&&cards[sel].status!=="script_review")send("rework");
});
function showView(v){
 $("review").style.display=v==="review"?"":"none";
 $("analytics").style.display=v==="analytics"?"block":"none";
 $("nav-review").classList.toggle("on",v==="review");
 $("nav-analytics").classList.toggle("on",v==="analytics");
 if(v==="analytics")loadAnalytics();
}
async function loadAnalytics(){
 const rows=await(await fetch("/api/analytics")).json();
 const el=$("analytics");
 if(!rows.length){el.innerHTML='<div class="note">No linked videos yet. Publish a video (or link a recipe video_id), then metrics appear after YouTube processes them (~24-48h).</div>';return;}
 const drops=rows.map(r=>r.drop_by_beat?Math.max(...Object.values(r.drop_by_beat)):0);
 const maxDrop=Math.max(0.001,...drops);
 const num=v=>v==null?'<span class="mut">—</span>':v;
 const wd=rows.filter(r=>r.views!=null);
 let ins='';
 if(wd.length){
  const top=[...wd].sort((a,b)=>(b.views||0)-(a.views||0))[0];
  const rets=wd.filter(r=>r.avg_view_pct!=null);
  const avgRet=rets.length?Math.round(rets.reduce((s,r)=>s+r.avg_view_pct,0)/rets.length):null;
  const totL=wd.reduce((s,r)=>s+(r.likes||0),0), totC=wd.reduce((s,r)=>s+(r.comments||0),0), totV=wd.reduce((s,r)=>s+(r.views||0),0);
  const avgV=a=>a.length?Math.round(a.reduce((s,r)=>s+(r.views||0),0)/a.length):null;
  const shortW=wd.filter(r=>r.word_count&&r.word_count<=100), longW=wd.filter(r=>r.word_count&&r.word_count>100);
  const byHook={}; wd.forEach(r=>{const k=r.hook_type||'?';(byHook[k]=byHook[k]||[]).push(r.views||0);});
  const hookRank=Object.entries(byHook).map(([k,v])=>[k,Math.round(v.reduce((a,b)=>a+b,0)/v.length)]).sort((a,b)=>b[1]-a[1]);
  ins=`<div class="insights">
    <div class="ins"><div class="insh">🏆 Top performer</div><b>${esc(top.subject||'?')}</b> · ${top.views} views${top.avg_view_pct!=null?' · '+top.avg_view_pct.toFixed(0)+'% avg-view':''}<div class="mut">${top.word_count||'?'}w · ${esc(top.hook_type||'?')} hook · ${esc(top.persona||'?')}</div></div>
    <div class="ins"><div class="insh">📉 Engagement gap</div><b>${totL}</b> likes · <b>${totC}</b> comments<div class="mut">across ${totV} views — CTAs barely convert; #1 fixable lever</div></div>
    <div class="ins"><div class="insh">⏱ Length → reach</div>≤100w: <b>${avgV(shortW)??'—'}</b> · &gt;100w: <b>${avgV(longW)??'—'}</b><div class="mut">avg views — shorter reaches further</div></div>
    <div class="ins"><div class="insh">🪝 Hook type (avg views)</div>${hookRank.map(([k,v])=>esc(k)+': <b>'+v+'</b>').join(' · ')||'—'}<div class="mut">avg retention ${avgRet!=null?avgRet+'%':'—'}</div></div>
   </div>
   <div class="playbook"><b>▶ Playbook from the data</b><ul>
    <li>Target <b>~90 words / ~35s</b> — the top video's length; longer scripts lose reach.</li>
    <li>Open on a <b>curiosity / question hook</b> in the first 2s, not a flat news line.</li>
    <li><b>Loop-back close</b> to drive replays (the top video passed 100% avg-view).</li>
    <li>Attack the <b>engagement gap</b>: like-at-peak pop + a binary poll comment.</li>
   </ul></div>`;
 }
 let h='<div class="note">Per-video performance from recipe cards (refreshed by the retention watcher). Avg-view% needs ~24-48h + enough views; likes/comments are immediate.</div>'+ins;
 h+='<table><thead><tr><th>Video</th><th>Format</th><th class="num">Views</th><th class="num">Likes</th><th class="num">Cmts</th><th class="num">Avg view %</th><th class="num">Like %</th><th>Weakest beat</th></tr></thead><tbody>';
 for(const r of rows){
  const pct=r.avg_view_pct,pc=pct==null?"mut":(pct<50?"bad":"ok");
  let beat='<span class="mut">—</span>';
  if(r.worst_beat&&r.drop_by_beat){const w=Math.round(90*(r.drop_by_beat[r.worst_beat]||0)/maxDrop);
   beat=`<span class="beatbar" style="width:${w}px"></span> <b>${r.worst_beat}</b>`;}
  h+=`<tr><td class="car">${esc(r.subject||"?")}<div class="mut" style="font-size:11px">${esc(r.video_id)}</div></td>`
   +`<td><span class="pill">${esc(r.hook_type||"?")} · ${esc(r.persona||"?")}</span><div class="mut" style="font-size:11px">${r.duration_s?r.duration_s+"s ":""}${r.word_count?"· "+r.word_count+"w":""}</div></td>`
   +`<td class="num">${num(r.views)}</td><td class="num">${num(r.likes)}</td><td class="num">${num(r.comments)}</td>`
   +`<td class="num ${pc}">${pct==null?'<span class="mut">—</span>':pct.toFixed(1)+"%"} </td>`
   +`<td class="num">${r.like_rate==null?'<span class="mut">—</span>':r.like_rate+"%"}</td><td>${beat}</td></tr>`;
 }
 el.innerHTML=h+"</tbody></table>";
}
load();
setInterval(async()=>{   // live: reworking/rendering -> fresh video/options appear by itself
 const fresh=await(await fetch("/api/queue")).json();
 const sig=x=>JSON.stringify(x.map(c=>[c.status,c.progress&&c.progress.step,c.draft_v,(c.options||[]).length,c.voice||"",c.script_choice||""]));
 if(sig(fresh)!==sig(cards)){
  const prevV=sel!==null&&cards[sel]?cards[sel].draft_v:null;
  const wasBuilder=sel!==null&&cards[sel].status==="script_review";
  const moreOpts=sel!==null&&fresh[sel]&&(fresh[sel].options||[]).length>(cards[sel].options||[]).length;
  cards=fresh;renderList();
  if(sel!==null&&cards[sel]){
   const c=cards[sel];
   if(wasBuilder&&c.status==="script_review"){renderBuilder(c);if(moreOpts)toast("3 fresh options ✓ — rebuild your mix");}
   else if(selWasBusy&&!BUSY(c.status)){toast("Fresh render landed — player unlocked ✓");pick(sel);}
   else if(!selWasBusy&&BUSY(c.status))pick(sel);
   else if(prevV!==null&&c.draft_v!==prevV&&!BUSY(c.status)){toast("This draft was re-rendered — reloading it ✓");pick(sel);}
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
    rec_dir = paths.RECIPES
    for path in sorted(rec_dir.glob("*.json")) if rec_dir.exists() else []:
        try:
            r = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — skip an unreadable record, never crash the portal
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
        # a render lock (draft OR final) overrides everything: file mid-write.
        # NB: a fresh card (script_review) has NO draft/final yet — treat empty
        # as None, never Path("") (which is Path('.') and blows up .with_suffix,
        # crashing the WHOLE queue for every card).
        def _pathy(v):
            return Path(v) if v else None
        draft = _pathy(card.get("draft") or f"out/{card.get('slug','')}_draft.mp4")
        final = _pathy(card.get("final") or f"out/{card.get('slug','')}_final.mp4")

        def _lock_held(p):
            return p is not None and p.name != "" and p.with_suffix(".lock").exists()
        if _lock_held(draft) or _lock_held(final):
            card["status"] = "rendering"
            card.setdefault("progress", {"step": "encoding video…", "at": ""})
        # play the FINAL whenever it exists and is the freshest render — a
        # finished render must ALWAYS load, regardless of the card's status label.
        # Fall back to the draft only when there's no final, or the draft is newer.
        if final is not None and final.exists() and (
                draft is None or not draft.exists()
                or final.stat().st_mtime >= draft.stat().st_mtime):
            card["play"] = str(final)
        else:
            card["play"] = str(draft) if (draft and draft.exists()) else ""
        play = _pathy(card["play"])
        card["draft_v"] = int(play.stat().st_mtime) if (play and play.exists()) else 0
        # SELF-HEAL: a card stuck in legacy 'rework' (submitted to an old
        # server process) gets its worker spawned right here
        if card.get("status") == "rework" and card["slug"] not in _healing:
            _healing.add(card["slug"])
            card["status"] = "reworking"
            with _card_lock(card["slug"]):
                _write_card(path, card)
            subprocess.Popen([sys.executable, "-m", "carshorts.agents.rework",
                              card["slug"]], start_new_session=True)
        _mp = card.get("play") or card.get("draft") or ""
        manifest = Path(_mp).with_suffix(".manifest.json") if _mp else None
        beats, cursor = [], 0.0
        if manifest and manifest.exists():
            for sec in json.loads(manifest.read_text()).get("sections", []):
                beats.append({"role": sec["role"], "text": sec["text"],
                              "start": round(cursor, 2), "dur": round(sec["duration"], 2)})
                cursor += sec["duration"]
        card["beats"] = beats
        # script_review: attach the script options + any voice samples so the
        # owner mixes beats and picks a voice from the portal before we produce.
        if card.get("status") == "script_review":
            opts = []
            for sp in sorted(paths.SCRIPTS.glob(f"{card.get('slug','')}_opt*.script.json")):
                try:
                    d = json.loads(sp.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001 — skip an unreadable option file
                    continue
                opts.append({"file": str(sp), "label": d.get("_angle", sp.stem),
                             "beats": [{"role": s.get("role", ""), "text": s.get("text", ""),
                                        "cited_spec_names": s.get("cited_spec_names", []),
                                        "pops": s.get("pops", [])}
                                       for s in d.get("segments", [])]})
            card["options"] = opts
            vopts = []
            if paths.VOICE_OPTIONS.exists():
                for vp in sorted(paths.VOICE_OPTIONS.glob(f"{card.get('slug','')}_*.mp3")):
                    vopts.append({"file": str(vp), "label": vp.stem.split("_")[-1]})
            card["voice_options"] = vopts
        # owner-dropped footage + notes (content-drop), so the FE can show what's
        # in the pool and the render can use it.
        try:
            _own = paths.car_dir(card.get("slug", "")) / "own"
            card["own_clips"] = sorted(p.name for p in _own.glob("*.mp4")) if _own.exists() else []
        except Exception:  # noqa: BLE001 — never let a listing error break the queue
            card["own_clips"] = []
        _cn = paths.DATA / "content" / f"{card.get('slug', '')}.json"
        try:
            card["content_notes"] = json.loads(_cn.read_text()).get("notes", "") if _cn.exists() else ""
        except Exception:  # noqa: BLE001
            card["content_notes"] = ""
        cards.append(card)
    return cards


def _spawn_worker(slug: str, python_code: str) -> None:
    """Run `python_code` (a -c script) in a detached child that outlives the
    portal process. The child's stdout/stderr tail lands in out/portal.log so
    render/generation failures are diagnosable without the console."""
    log = paths.OUT / "portal.log"
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        logfd = log.open("ab")
    except OSError:
        logfd = None
    code = (
        "import subprocess,sys,json,pathlib,traceback,os\n"
        "try:\n"
        + "\n".join("  " + ln for ln in python_code.splitlines())
        + "\nexcept Exception as e:\n"
        "  sys.stderr.write(traceback.format_exc())"
    )
    if logfd is not None:
        subprocess.Popen([sys.executable, "-c", code], start_new_session=True,
                         stdout=logfd, stderr=logfd)
    else:
        subprocess.Popen([sys.executable, "-c", code], start_new_session=True)


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
            if not fp or not fp.exists() or fp.suffix not in (".mp4", ".mp3") or ".." in str(fp):
                self._send(404, b"{}")
                return
            data = fp.read_bytes()
            ctype = "audio/mpeg" if fp.suffix == ".mp3" else "video/mp4"
            rng = self.headers.get("Range")
            if rng and fp.suffix == ".mp4":          # range only for the video player
                m2 = re.match(r"bytes=(\d+)-(\d*)", rng)
                start = int(m2.group(1))
                end = int(m2.group(2)) if m2.group(2) else len(data) - 1
                chunk = data[start:end + 1]
                self.send_response(206)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
                self.send_header("Content-Length", str(len(chunk)))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                self.wfile.write(chunk)
            else:
                self._send(200, data, ctype)
        else:
            self._send(404, b"{}")

    def do_POST(self):
        def read_json():
            length = int(self.headers.get("Content-Length", 0))
            try:
                return json.loads(self.rfile.read(length))
            except (ValueError, UnicodeDecodeError):
                return None
        if self.path.startswith("/api/upload"):     # owner drops footage + jokes
            ctype = self.headers.get("Content-Type", "")
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b""
            if "multipart/form-data" not in ctype or "boundary=" not in ctype:
                self._send(400, b'{"error":"expected multipart form"}')
                return
            boundary = ctype.split("boundary=", 1)[1].strip().strip('"').encode()
            fields, files = {}, []
            for part in raw.split(b"--" + boundary):
                if b"\r\n\r\n" not in part:
                    continue
                head, body = part.split(b"\r\n\r\n", 1)
                if body.endswith(b"\r\n"):
                    body = body[:-2]
                hs = head.decode("utf-8", "ignore")
                mn = re.search(r'name="([^"]+)"', hs)
                if not mn:
                    continue
                fn = re.search(r'filename="([^"]*)"', hs)
                if fn and fn.group(1):
                    files.append((os.path.basename(fn.group(1)), body))
                else:
                    fields[mn.group(1)] = body.decode("utf-8", "ignore").strip()
            slug = fields.get("slug", "")
            if not slug or not (QUEUE / f"{slug}.json").exists():
                self._send(400, b'{"error":"unknown slug"}')
                return
            from carshorts.core import paths as _p
            own = _p.car_dir(slug) / "own"
            own.mkdir(parents=True, exist_ok=True)
            vids = (".mp4", ".mov", ".m4v", ".webm", ".mkv")
            saved, skipped = [], []
            for fname, data in files:
                safe = re.sub(r"[^A-Za-z0-9._-]", "_", fname) or "clip.mp4"
                if not safe.lower().endswith(vids):
                    skipped.append(safe)
                    continue                     # only video clips join the pool
                dest = own / safe
                k = 1
                while dest.exists():
                    dest = own / f"{dest.stem}_{k}{dest.suffix}"
                    k += 1
                dest.write_bytes(data)
                saved.append(dest.name)
            notes = fields.get("notes", "")
            if notes:
                cdir = _p.DATA / "content"
                cdir.mkdir(parents=True, exist_ok=True)
                (cdir / f"{slug}.json").write_text(json.dumps(
                    {"slug": slug, "notes": notes,
                     "updated": datetime.datetime.now().isoformat(timespec="seconds")},
                    indent=2, ensure_ascii=False), encoding="utf-8")
            self._send(200, json.dumps({"ok": True, "saved": saved,
                                        "skipped": skipped, "notes_saved": bool(notes)}).encode())
            return
        if self.path.startswith("/api/reopen"):     # back to the script/voice builder
            body = read_json()
            if not body:
                self._send(400, b'{"error":"bad json"}')
                return
            card_path = QUEUE / f"{body['slug']}.json"
            if not card_path.exists():
                self._send(404, b"{}")
                return
            with _card_lock(body["slug"]):
                card = json.loads(card_path.read_text())
                card["status"] = "script_review"
                card["note"] = "reopened — change the script mix or voice, then lock again"
                _write_card(card_path, card)
            (QUEUE / f"{body['slug']}.progress.json").unlink(missing_ok=True)
            self._send(200, b'{"ok": true}')
            return
        if self.path.startswith("/api/pick"):
            body = read_json()
            if not body:
                self._send(400, b'{"error":"bad json"}')
                return
            card_path = QUEUE / f"{body['slug']}.json"
            if not card_path.exists():
                self._send(404, b"{}")
                return
            with _card_lock(body["slug"]):
                card = json.loads(card_path.read_text())
                if body.get("kind") == "script":
                    card["script"] = body["choice"]            # chosen option becomes the script
                    card["script_choice"] = body.get("label", "")
                elif body.get("kind") == "voice":
                    card["voice"] = body.get("label", body["choice"])
                    card["voice_file"] = body["choice"]
                _write_card(card_path, card)
            self._send(200, b'{"ok": true}')
            return
        if self.path.startswith("/api/build/lock"):     # assemble the mixed beats + produce
            body = read_json()
            if not body:
                self._send(400, b'{"error":"bad json"}')
                return
            card_path = QUEUE / f"{body['slug']}.json"
            with _card_lock(body["slug"]):
                card = json.loads(card_path.read_text())
                if body.get("build"):
                    card["script_build"] = body["build"]
                build = card.get("script_build", {})
                order = ["hook", "spec", "value", "peak", "cta"]
                segs = [build[r] for r in order
                        if r in build and build[r].get("text") and build[r]["text"].strip()]
                if len(segs) < 4 or not (build.get("hook", {}).get("text", "").strip()
                                         and build.get("cta", {}).get("text", "").strip()):
                    self._send(400, b'{"error":"hook + cta and at least 4 beats required"}')
                    return
                from carshorts.core import paths as _p
                out = _p.SCRIPTS / f"{body['slug']}_built.script.json"
                out.write_text(json.dumps({"subject": card.get("car", ""), "segments": segs},
                                          indent=2, ensure_ascii=False), encoding="utf-8")
                card["script"] = str(out)
                card["script_choice"] = "custom mix"
                card["status"] = "rendering"
                card["note"] = "your mix locked — producing the free draft"
                _write_card(card_path, card)
            # Render with the owner's CLONED voice and the persona they PICKED in
            # the portal (voice label → chatterbox persona), never the generic
            # edge fallback. calm→deadpan, natural→default(""), hype→hype.
            _voice2persona = {"calm": "deadpan", "natural": "", "hype": "hype", "bhai": "bhai"}
            _persona = _voice2persona.get(card.get("voice", ""), card.get("persona", "deadpan"))
            pf = QUEUE / f"{body['slug']}.progress.json"
            pf.write_text(json.dumps({"step": "rendering your mix (cloned voice, free)…",
                                      "at": datetime.datetime.now().isoformat(timespec="seconds")}))
            draft_out = card.get("draft") or f"out/{body['slug']}_draft.mp4"
            _spawn_worker(body["slug"], (
                f"r=subprocess.run([sys.executable,'-m','carshorts.rendering.produce',"
                f"'--script-file',{str(out)!r},'--spec',{card['spec']!r},'--skip-factcheck','--stock',"
                f"'--voice-engine','chatterbox','--language',{card.get('language','english')!r},"
                f"'--persona',{_persona!r},'--out',{draft_out!r}]"
                f"+{card.get('render_flags', [])!r},capture_output=True,text=True);"
                f"cp=pathlib.Path({str(card_path)!r});c=json.loads(cp.read_text());"
                "c['status']='awaiting_approval' if r.returncode==0 else 'rework_failed';"
                "c['note']=('your mix rendered — watch the draft' if r.returncode==0 "
                "else 'render failed — see out/portal.log');"
                "_t=cp.with_name(cp.name+'.tmp');_t.write_text(json.dumps(c,indent=2));"
                "os.replace(_t,cp);"
                f"pathlib.Path({str(pf)!r}).unlink(missing_ok=True);"
                "sys.stderr.write('--- build/lock stdout ---\\n'+(r.stdout or '')[-2000:]);"
                "sys.stderr.write('--- stderr ---\\n'+(r.stderr or '')[-2000:])"))
            self._send(200, b'{"ok": true}')
            return
        if self.path.startswith("/api/build"):          # record one picked/edited beat
            body = read_json()
            if not body:
                self._send(400, b'{"error":"bad json"}')
                return
            card_path = QUEUE / f"{body['slug']}.json"
            with _card_lock(body["slug"]):
                card = json.loads(card_path.read_text())
                card.setdefault("script_build", {})[body["role"]] = body["beat"]
                _write_card(card_path, card)
            self._send(200, b'{"ok": true}')
            return
        if self.path.startswith("/api/scripts/more"):   # generate 3 fresh options
            body = read_json()
            if not body:
                self._send(400, b'{"error":"bad json"}')
                return
            card_path = QUEUE / f"{body['slug']}.json"
            card = json.loads(card_path.read_text())
            pf = QUEUE / f"{body['slug']}.progress.json"
            pf.write_text(json.dumps({"step": "generating 3 more script options…",
                                      "at": datetime.datetime.now().isoformat(timespec="seconds")}))
            _spawn_worker(body["slug"], (
                f"r=subprocess.run([sys.executable,'-m','carshorts.writing.writescript',"
                f"'--spec',{card['spec']!r},'--persona',{card.get('persona','deadpan')!r},"
                f"'--options','3'],capture_output=True,text=True);"
                f"pathlib.Path({str(pf)!r}).unlink(missing_ok=True);"
                "sys.stderr.write('--- scripts/more stdout ---\\n'+(r.stdout or '')[-1500:]);"
                "sys.stderr.write('--- stderr ---\\n'+(r.stderr or '')[-1500:])"))
            self._send(200, b'{"ok": true}')
            return
        if self.path.startswith("/api/script"):
            body = read_json()
            if not body:
                self._send(400, b'{"error":"bad json"}')
                return
            card_path = QUEUE / f"{body['slug']}.json"
            if not card_path.exists():
                self._send(404, b"{}")
                return
            with _card_lock(body["slug"]):
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
                _write_card(card_path, card)
            pf = QUEUE / f"{body['slug']}.progress.json"
            pf.write_text(json.dumps({"step": "re-rendering your edited script",
                                      "at": datetime.datetime.now().isoformat(timespec='seconds')}))
            _spawn_worker(body["slug"], (
                f"r=subprocess.run([sys.executable,'-m','carshorts.rendering.produce','--script-file',{card['script']!r},"
                f"'--spec',{card['spec']!r},'--skip-factcheck','--persona',{card.get('persona','deadpan')!r},"
                f"'--out',{card['draft']!r}]+{card.get('render_flags', [])!r},"
                "capture_output=True,text=True);"
                f"cp=pathlib.Path({str(card_path)!r});c=json.loads(cp.read_text());"
                "c['status']='awaiting_approval' if r.returncode==0 else 'rework_failed';"
                "c['note']=('edited script rendered' if r.returncode==0 "
                "else 'render failed — see out/portal.log');"
                "_t=cp.with_name(cp.name+'.tmp');_t.write_text(json.dumps(c,indent=2));"
                "os.replace(_t,cp);"
                f"pathlib.Path({str(pf)!r}).unlink(missing_ok=True);"
                "sys.stderr.write('--- script edit stdout ---\\n'+(r.stdout or '')[-2000:]);"
                "sys.stderr.write('--- stderr ---\\n'+(r.stderr or '')[-2000:])"))
            self._send(200, b'{"ok": true}')
            return
        if not self.path.startswith("/api/feedback"):
            self._send(404, b"{}")
            return
        fb = read_json()
        if not fb:
            self._send(400, b'{"error":"bad json"}')
            return
        FEEDBACK.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        (FEEDBACK / f"{fb['slug']}-{stamp}.json").write_text(json.dumps(fb, indent=2, ensure_ascii=False))
        card_path = QUEUE / f"{fb['slug']}.json"
        if card_path.exists():
            with _card_lock(fb["slug"]):
                card = json.loads(card_path.read_text())
                card["status"] = {"approve": "approved",
                                  "publish": "publishing"}.get(fb["verdict"], "reworking")
                _write_card(card_path, card)
            if fb["verdict"] in ("approve", "publish"):
                flag = "--approve" if fb["verdict"] == "approve" else "--publish"
                subprocess.Popen(
                    [sys.executable, "-m", "carshorts.orchestration.pipeline", flag, fb["slug"]],
                    start_new_session=True)
            else:   # auto-rework picks the feedback up immediately
                subprocess.Popen([sys.executable, "-m", "carshorts.agents.rework",
                                  fb["slug"]], start_new_session=True)
        self._send(200, b'{"ok": true}')


def main() -> None:
    port = 8787
    print(f"review station -> http://localhost:{port}   (Ctrl-C to stop)")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
