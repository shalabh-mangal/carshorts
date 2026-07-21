"""Central config: loads .env once so keys never live in shell commands/chat.

.env (gitignored) format — KEY=value lines:
    GROQ_API_KEY=...
    GEMINI_API_KEY=...
    PEXELS_API_KEY=...
    ELEVENLABS_API_KEY=...
    ELEVENLABS_VOICE_ID=...
Existing environment variables always win over .env values.
"""
from __future__ import annotations

import os
from pathlib import Path

_loaded = False


def load_env() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    for candidate in (Path(".env"), Path(__file__).resolve().parents[2] / ".env"):
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())
            break
