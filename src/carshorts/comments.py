"""Comment mining — the audience tells you what to make next.

  python -m carshorts.comments            # mine all published videos

For every published video (recipes with a video_id):
  1. fetches comments via the YouTube API (read scope)
  2. an LLM mines them: questions asked, video ideas implied, sentiment,
     comments worth replying to — with DRAFT replies (never auto-posted;
     you copy-paste the ones you like)
  3. topic ideas are appended to data/topic_ideas.json (deduped) — feed for
     the content calendar; report written to data/comments/<date>.md
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

from .adapters.llm import make_llm
from .stages.pipeline import _rows


def _fetch_comments(video_id: str, limit: int = 50) -> list[dict]:
    from .ytauth import service
    yt = service("youtube", "v3")
    try:
        resp = yt.commentThreads().list(
            part="snippet", videoId=video_id, maxResults=min(limit, 100),
            order="relevance", textFormat="plainText").execute()
    except Exception as exc:  # noqa: BLE001 — comments disabled / none yet
        print(f"  {video_id}: no comments readable ({str(exc)[:60]})")
        return []
    out = []
    for item in resp.get("items", []):
        top = item["snippet"]["topLevelComment"]["snippet"]
        out.append({"author": top.get("authorDisplayName", ""),
                    "text": top.get("textDisplay", ""),
                    "likes": top.get("likeCount", 0)})
    return out


def run(provider: str | None = None) -> None:
    videos = []
    for path in sorted(Path("data/recipes").glob("*.json")):
        r = json.loads(path.read_text())
        if r.get("video_id"):
            videos.append((r["subject"], r["video_id"]))
    if not videos:
        print("no published videos with linked ids")
        return

    all_comments = []
    for subject, vid in videos:
        comments = _fetch_comments(vid)
        print(f"  {subject}: {len(comments)} comment(s)")
        for c in comments:
            all_comments.append({"video": subject, **c})
    if not all_comments:
        print("no comments yet — audience still growing; re-run later")
        return

    llm = make_llm(provider or "groq")
    system = (
        "You mine YouTube comments for a car-Shorts channel. Given comments "
        "(with their video), output ONLY JSON:\n"
        '{"questions": ["..."], "topic_ideas": ["<future video idea>", ...], '
        '"sentiment": "<one line>", '
        '"replies": [{"video": "...", "comment": "...", "draft_reply": "..."}]}\n'
        "Draft replies: warm, brief, on-brand (witty, factual), max 5. Never "
        "invent facts; if a question needs data we don't have, the reply "
        "should promise a video on it instead.")
    data = llm.complete_json(system, json.dumps(all_comments, ensure_ascii=False))
    if isinstance(data, list):
        data = data[0] if data else {}

    ideas_path = Path("data/topic_ideas.json")
    existing = json.loads(ideas_path.read_text()) if ideas_path.exists() else []
    for idea in data.get("topic_ideas", []):
        if idea and idea not in existing:
            existing.append(idea)
    ideas_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False))

    report_dir = Path("data/comments"); report_dir.mkdir(parents=True, exist_ok=True)
    lines = [f"# Comment mining — {datetime.date.today()}", "",
             f"Sentiment: {data.get('sentiment', '?')}", "", "## Questions asked"]
    lines += [f"- {q}" for q in data.get("questions", [])] or ["- (none)"]
    lines += ["", "## Topic ideas (also in data/topic_ideas.json)"]
    lines += [f"- {t}" for t in data.get("topic_ideas", [])] or ["- (none)"]
    lines += ["", "## Draft replies (copy-paste what you like — NEVER auto-posted)"]
    for r in data.get("replies", []):
        lines += [f"**On {r.get('video')}** — “{r.get('comment', '')[:80]}”",
                  f"> {r.get('draft_reply')}", ""]
    report = report_dir / f"{datetime.date.today()}.md"
    report.write_text("\n".join(lines))
    print(f"report -> {report}; topic ideas: {len(existing)} total")


if __name__ == "__main__":
    run()
