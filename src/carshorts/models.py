"""Typed contracts that cross stage boundaries.

These are the DDD value objects of the pipeline. Every stage consumes one
model and produces another; nothing crosses a boundary as a loose dict.
Pydantic gives us validation of LLM output (which is the whole point of using
it here) plus self-documenting interfaces.

The factual-accuracy design lives in these types: a Spec is never just a
number, it is a number *plus the source it came from*. A Claim in a script is
linked back to the Spec that backs it, or it is flagged. That linkage is what
makes Gate 1 a 2-minute check instead of a from-scratch reread.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


# ---------------------------------------------------------------------------
# Stage 1: discover + rank
# ---------------------------------------------------------------------------
class NewsItem(BaseModel):
    """A candidate story surfaced by the discovery stage."""

    title: str
    url: HttpUrl
    source_name: str
    published_at: Optional[datetime] = None
    summary: str = ""
    # Set by the ranking stage. Higher = more viral potential.
    virality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    virality_reasons: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Stage 2: collect specs + sources
# ---------------------------------------------------------------------------
class Spec(BaseModel):
    """A single verifiable fact, bound to the exact source it was pulled from.

    The source_sentence is the literal text the figure was extracted from. At
    Gate 1 the human reads this one sentence to confirm the figure, rather than
    re-researching the car. This is the linchpin of the accuracy design.
    """

    name: str               # e.g. "power", "price_ex_showroom", "0-100 kmph"
    value: str              # kept as string: "152 bhp", "Rs 12.99 lakh"
    source_url: HttpUrl
    source_sentence: str    # the exact sentence the value was extracted from
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class SpecSheet(BaseModel):
    """All collected facts for one story. The script writer may use ONLY these."""

    subject: str            # e.g. "Mahindra Thar Roxx 2024"
    specs: list[Spec] = Field(default_factory=list)

    def fact_index(self) -> dict[str, Spec]:
        return {s.name: s for s in self.specs}


# ---------------------------------------------------------------------------
# Stage 3: draft script
# ---------------------------------------------------------------------------
class ScriptSegment(BaseModel):
    """One spoken beat of the 60s script."""

    role: str               # "hook" | "body" | "cta"
    text: str
    # Names of the Specs (Spec.name) this segment relies on. Empty = no factual
    # claim (pure narration/opinion). The writer is prompted to fill this in.
    cited_spec_names: list[str] = Field(default_factory=list)


class Script(BaseModel):
    subject: str
    segments: list[ScriptSegment]

    @property
    def full_text(self) -> str:
        return " ".join(seg.text for seg in self.segments)

    def approx_word_count(self) -> int:
        return len(self.full_text.split())


# ---------------------------------------------------------------------------
# Stage 4: fact-check (the skeptic pass)
# ---------------------------------------------------------------------------
class Verdict(str, Enum):
    SUPPORTED = "supported"       # claim is backed by a spec in the sheet
    UNSUPPORTED = "unsupported"   # claim has no backing spec -> hallucination risk
    CONTRADICTED = "contradicted"  # claim disagrees with a spec -> serious flag
    OPINION = "opinion"           # not a factual claim, no backing needed


class ClaimCheck(BaseModel):
    claim_text: str               # the specific claim extracted from the script
    verdict: Verdict
    backing_spec_name: Optional[str] = None
    note: str = ""                # why the checker reached this verdict


class FactCheckReport(BaseModel):
    subject: str
    checks: list[ClaimCheck]

    @property
    def needs_human_attention(self) -> bool:
        return any(
            c.verdict in (Verdict.UNSUPPORTED, Verdict.CONTRADICTED)
            for c in self.checks
        )

    @property
    def flag_count(self) -> int:
        return sum(
            1 for c in self.checks
            if c.verdict in (Verdict.UNSUPPORTED, Verdict.CONTRADICTED)
        )
