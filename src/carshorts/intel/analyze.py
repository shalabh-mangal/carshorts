"""The analyst — closes the learning loop from real performance data.

  python -m carshorts.intel.analyze          # run weekly (or whenever)

Joins every recipe card (data/recipes/) with its YouTube analytics (views,
avg view duration, avg view %), asks an LLM to extract what is WORKING vs
FAILING across hook types / personas / lengths / music, and updates
data/learnings.json data_learnings — which the writer injects into every
future script. Small-sample humility is built into the prompt.
Writes a human report to data/reports/<date>.md.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

from carshorts.adapters.llm import make_llm
from carshorts.core import paths
from carshorts.writing.draft import _rows


def _fetch_metrics(video_id: str) -> dict | None:
    try:
        from carshorts.publishing.ytauth import service
        yt = service("youtube", "v3")
        stats = yt.videos().list(part="statistics", id=video_id).execute()
        if not stats.get("items"):
            return None
        st = stats["items"][0]["statistics"]
        yta = service("youtubeAnalytics", "v2")
        ch = yt.channels().list(part="id", mine=True).execute()["items"][0]["id"]
        rep = yta.reports().query(
            ids=f"channel=={ch}", startDate="2005-02-14",
            endDate=datetime.date.today().isoformat(),
            metrics="views,averageViewDuration,averageViewPercentage",
            filters=f"video=={video_id}").execute()
        row = (rep.get("rows") or [[None, None, None]])[0]
        metrics = {"views": int(st.get("viewCount", 0)),
                   "likes": int(st.get("likeCount", 0)),
                   "comments": int(st.get("commentCount", 0)),
                   "avg_view_s": row[1], "avg_view_pct": row[2]}
        try:   # per-second retention curve (elapsed ratio -> audience ratio)
            curve = yta.reports().query(
                ids=f"channel=={ch}", startDate="2005-02-14",
                endDate=datetime.date.today().isoformat(),
                metrics="audienceWatchRatio",
                dimensions="elapsedVideoTimeRatio",
                filters=f"video=={video_id}").execute().get("rows", [])
            metrics["retention_curve"] = [[float(a), float(b)] for a, b in curve]
        except Exception:  # noqa: BLE001 — needs enough views to exist
            pass
        return metrics
    except Exception:  # noqa: BLE001
        return None


def run(provider: str | None = None) -> None:
    recipes = []
    for path in sorted(paths.RECIPES.glob("*.json")):
        r = json.loads(path.read_text())
        if r.get("video_id"):
            m = _fetch_metrics(r["video_id"])
            if m:
                r["metrics"] = m
                path.write_text(json.dumps(r, indent=2, ensure_ascii=False))
        recipes.append(r)
    # map each video's retention curve onto its BEATS via the render manifest:
    # which section was playing when viewers left.
    for r in recipes:
        curve = (r.get("metrics") or {}).get("retention_curve")
        manifest_path = Path(r.get("out", "")).with_suffix(".manifest.json")
        if not curve or not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text())
        total = sum(sec["duration"] for sec in manifest.get("sections", []))
        bounds, acc = [], 0.0
        for sec in manifest.get("sections", []):
            acc += sec["duration"]
            bounds.append((sec["role"], acc))
        beat_drop: dict[str, float] = {}
        prev_ratio = None
        for elapsed, watch in curve:
            t = elapsed * total
            role = next((rl for rl, end in bounds if t <= end), bounds[-1][0])
            if prev_ratio is not None:
                beat_drop[role] = beat_drop.get(role, 0.0) + max(0.0, prev_ratio - watch)
            prev_ratio = watch
        if beat_drop:
            worst = max(beat_drop, key=beat_drop.get)
            r["metrics"]["drop_by_beat"] = {k: round(v, 3) for k, v in beat_drop.items()}
            r["metrics"]["worst_beat"] = worst

    with_data = [r for r in recipes if r.get("metrics")]
    print(f"recipes: {len(recipes)}, with metrics: {len(with_data)}")
    if not with_data:
        print("no analytics yet — upload videos, link ids, retry in 24-48h")
        return

    failures = []
    fj = paths.FAILURES
    if fj.exists():
        failures = [json.loads(l) for l in fj.read_text().splitlines() if l.strip()][-20:]

    llm = make_llm(provider)  # None -> Gemini-first chain
    system = (
        "You are the channel analyst for a car-Shorts factory. Given recipe "
        "cards (creative choices) with their YouTube metrics, plus recent QA "
        "failures, extract 3-6 LEARNINGS: what to keep doing, what to change. "
        "Be humble about small samples (<500 views = weak signal; say so). "
        "Each learning must be actionable for the script writer or renderer. "
        'Output ONLY JSON: [{"learning": "...", "confidence": "low|medium|high"}]')
    payload = json.dumps({"recipes": with_data, "qa_failures": failures}, ensure_ascii=False)
    rows = _rows(llm.complete_json(system, payload))

    ldata = json.loads(paths.LEARNINGS.read_text())
    added = 0
    for row in rows:
        text = row.get("learning", "").strip()
        if text:
            tagged = f"[{row.get('confidence','low')}] {text}"
            if tagged not in ldata["data_learnings"]:
                ldata["data_learnings"].append(tagged)
                added += 1
    ldata["data_learnings"] = ldata["data_learnings"][-12:]
    ldata["updated"] = datetime.date.today().isoformat()
    paths.LEARNINGS.write_text(json.dumps(ldata, indent=2, ensure_ascii=False))

    report_dir = paths.REPORTS; report_dir.mkdir(parents=True, exist_ok=True)
    lines = [f"# Analyst report — {datetime.date.today()}", ""]
    for r in with_data:
        m = r["metrics"]
        lines.append(f"- **{r['subject']}** ({r.get('hook_type')}, {r.get('persona')}): "
                     f"{m['views']} views, {m.get('avg_view_pct') or '?'}% avg view")
    lines += ["", "## New learnings"] + [f"- {row.get('learning')}" for row in rows]
    (report_dir / f"{datetime.date.today()}.md").write_text("\n".join(lines))
    print(f"learnings added: {added}; report -> data/reports/{datetime.date.today()}.md")


if __name__ == "__main__":
    run()
