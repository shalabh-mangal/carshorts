"""Experiment ledger — turns hypotheses into knowledge, or refuses to.

  python -m carshorts.intel.experiments                      # status board
  python -m carshorts.intel.experiments --new "..." --variable length_s \
      --metric avg_view_pct --control 58 --treatment 35
  python -m carshorts.intel.experiments --assign exp-001 --arm treatment --video VID
  python -m carshorts.intel.experiments --evaluate exp-001

WHY THIS EXISTS: data/learnings.json is a flat list that an LLM appends to, and
every entry is injected into the writer prompt for EVERY future script. There is
no confidence, no evidence link, no expiry. That means one lucky video can teach
the system a superstition it then follows forever. On 2026-07-23 the analytics
pull showed why the risk is real: our "42.2% retention" was computed from 7
processed views.

So this ledger's default answer is NO. A hypothesis becomes a lesson only when:
  1. both arms have >= min_samples videos, AND
  2. every sampled video clears a views floor (below it the metric is noise), AND
  3. the observed effect is at least min_effect, AND
  4. a Welch t-test on the two arms clears alpha.
Anything else returns INSUFFICIENT — which is the honest answer almost always,
early on, and is far more valuable than a confident guess.

It measures ONE variable per experiment. Confounded evidence is not evidence.
"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import statistics
from pathlib import Path

LEDGER = Path("data/experiments.json")
RECIPES = Path("data/recipes")

# Defaults chosen to be conservative. The analyst prompt already treats <500
# views as a weak signal; a metric computed on a handful of views is noise.
DEFAULT_MIN_SAMPLES = 3
DEFAULT_MIN_VIEWS = 500
DEFAULT_ALPHA = 0.10          # generous for a tiny channel, still a real bar
DEFAULT_MIN_EFFECT = 0.0


# --------------------------------------------------------------------------
# statistics — Welch's t-test with a real t-distribution p-value.
# Implemented here (regularized incomplete beta, Lentz continued fraction) so
# the project keeps its "no heavy deps" stance; verified against known values
# in tests/test_experiments.py.
# --------------------------------------------------------------------------
def _betacf(a: float, b: float, x: float, iters: int = 200) -> float:
    tiny = 1e-30
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, iters + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        c = 1.0 + aa / c
        if abs(d) < tiny:
            d = tiny
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        c = 1.0 + aa / c
        if abs(d) < tiny:
            d = tiny
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-16:
            break
    return h


def _betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
             + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(lbeta) * _betacf(a, b, x) / a
    return 1.0 - math.exp(lbeta) * _betacf(b, a, 1.0 - x) / b


def t_two_tailed_p(t: float, df: float) -> float:
    """Two-tailed p-value for Student's t."""
    if df <= 0 or math.isnan(t):
        return 1.0
    return _betainc(df / 2.0, 0.5, df / (df + t * t))


def welch(a: list[float], b: list[float]) -> dict:
    """Welch's unequal-variance t-test. Returns means, diff, t, df, p."""
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return {"n_a": na, "n_b": nb, "mean_a": (statistics.fmean(a) if a else None),
                "mean_b": (statistics.fmean(b) if b else None),
                "diff": None, "t": None, "df": None, "p": None}
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    va, vb = statistics.variance(a), statistics.variance(b)
    se2 = va / na + vb / nb
    if se2 <= 0:
        return {"n_a": na, "n_b": nb, "mean_a": ma, "mean_b": mb,
                "diff": mb - ma, "t": None, "df": None, "p": 1.0}
    t = (mb - ma) / math.sqrt(se2)
    df = se2 ** 2 / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))
    return {"n_a": na, "n_b": nb, "mean_a": ma, "mean_b": mb, "diff": mb - ma,
            "t": t, "df": df, "p": t_two_tailed_p(t, df)}


# --------------------------------------------------------------------------
# the gate
# --------------------------------------------------------------------------
def evaluate(control: list[float], treatment: list[float],
             min_samples: int = DEFAULT_MIN_SAMPLES,
             alpha: float = DEFAULT_ALPHA,
             min_effect: float = DEFAULT_MIN_EFFECT) -> dict:
    """Decide whether these two arms justify a lesson. Defaults to refusing."""
    stats = welch(control, treatment)
    if len(control) < min_samples or len(treatment) < min_samples:
        return {**stats, "status": "insufficient",
                "reason": (f"need >={min_samples} per arm, have "
                           f"{len(control)} control / {len(treatment)} treatment")}
    if stats["p"] is None:
        return {**stats, "status": "insufficient", "reason": "variance undefined"}
    if abs(stats["diff"]) < min_effect:
        return {**stats, "status": "no_effect",
                "reason": (f"effect {stats['diff']:.2f} below min_effect {min_effect}")}
    if stats["p"] > alpha:
        return {**stats, "status": "no_effect",
                "reason": (f"p={stats['p']:.3f} > alpha={alpha} — cannot distinguish "
                           f"from chance")}
    return {**stats, "status": ("supported" if stats["diff"] > 0 else "refuted"),
            "reason": f"p={stats['p']:.3f} <= alpha={alpha}, effect {stats['diff']:+.2f}"}


def may_become_lesson(verdict: dict) -> bool:
    """The gate learnings.json must pass. Only decided verdicts teach."""
    return verdict.get("status") in ("supported", "refuted")


# --------------------------------------------------------------------------
# ledger
# --------------------------------------------------------------------------
def load() -> dict:
    if LEDGER.exists():
        try:
            return json.loads(LEDGER.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {"experiments": []}


def save(data: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def new_experiment(hypothesis: str, variable: str, metric: str, control: str,
                   treatment: str, source: str = "", min_samples: int = DEFAULT_MIN_SAMPLES,
                   min_views: int = DEFAULT_MIN_VIEWS, min_effect: float = DEFAULT_MIN_EFFECT) -> dict:
    data = load()
    exp = {
        "id": f"exp-{len(data['experiments']) + 1:03d}",
        "hypothesis": hypothesis, "variable": variable, "metric": metric,
        "control": control, "treatment": treatment, "source": source,
        "min_samples": min_samples, "min_views": min_views, "min_effect": min_effect,
        "status": "running",
        "created": datetime.date.today().isoformat(),
        "arms": {"control": [], "treatment": []},
        "verdict": None,
    }
    data["experiments"].append(exp)
    save(data)
    return exp


def assign(exp_id: str, arm: str, video_id: str) -> dict:
    """Tag a published video as belonging to one arm. ONE variable per video."""
    data = load()
    for exp in data["experiments"]:
        if exp["id"] != exp_id:
            continue
        if arm not in ("control", "treatment"):
            raise ValueError("arm must be control or treatment")
        other = "treatment" if arm == "control" else "control"
        if video_id in exp["arms"][other]:
            raise ValueError(f"{video_id} is already in the {other} arm — a video "
                             f"cannot serve both sides")
        if video_id not in exp["arms"][arm]:
            exp["arms"][arm].append(video_id)
        save(data)
        return exp
    raise KeyError(exp_id)


def _metric_values(video_ids: list[str], metric: str, min_views: int) -> tuple[list[float], list[str]]:
    """Pull `metric` from recipe cards, dropping videos under the views floor."""
    values, skipped = [], []
    by_id = {}
    for path in RECIPES.glob("*.json"):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if rec.get("video_id"):
            by_id[rec["video_id"]] = rec
    for vid in video_ids:
        rec = by_id.get(vid)
        m = (rec or {}).get("metrics") or {}
        val, views = m.get(metric), m.get("views", 0)
        if val is None:
            skipped.append(f"{vid}: no {metric} yet")
            continue
        if views < min_views:
            skipped.append(f"{vid}: {views} views < floor {min_views}")
            continue
        values.append(float(val))
    return values, skipped


def evaluate_experiment(exp_id: str) -> dict:
    data = load()
    exp = next((e for e in data["experiments"] if e["id"] == exp_id), None)
    if not exp:
        raise KeyError(exp_id)
    ctrl, skip_c = _metric_values(exp["arms"]["control"], exp["metric"], exp["min_views"])
    treat, skip_t = _metric_values(exp["arms"]["treatment"], exp["metric"], exp["min_views"])
    verdict = evaluate(ctrl, treat, exp["min_samples"], min_effect=exp["min_effect"])
    verdict["skipped"] = skip_c + skip_t
    exp["verdict"] = verdict
    if may_become_lesson(verdict):
        exp["status"] = "concluded"
        exp["concluded_at"] = datetime.date.today().isoformat()
    save(data)
    return exp


def board() -> str:
    data = load()
    if not data["experiments"]:
        return ("no experiments yet — create one:\n"
                '  python -m carshorts.intel.experiments --new "shorter Shorts retain better" '
                "--variable length_s --metric avg_view_pct --control 58 --treatment 35")
    lines = [f"{'ID':<9} {'STATUS':<11} {'VAR':<12} {'C/T':<8} HYPOTHESIS"]
    lines.append("-" * 78)
    for e in data["experiments"]:
        v = e.get("verdict") or {}
        arms = f"{len(e['arms']['control'])}/{len(e['arms']['treatment'])}"
        status = v.get("status") or e["status"]
        lines.append(f"{e['id']:<9} {status:<11} {e['variable'][:11]:<12} {arms:<8} "
                     f"{e['hypothesis'][:38]}")
        if v.get("reason"):
            lines.append(f"          └─ {v['reason']}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Experiment ledger + significance gate.")
    ap.add_argument("--new", metavar="HYPOTHESIS")
    ap.add_argument("--variable", default="")
    ap.add_argument("--metric", default="avg_view_pct")
    ap.add_argument("--control", default="")
    ap.add_argument("--treatment", default="")
    ap.add_argument("--source", default="")
    ap.add_argument("--min-samples", type=int, default=DEFAULT_MIN_SAMPLES)
    ap.add_argument("--min-views", type=int, default=DEFAULT_MIN_VIEWS)
    ap.add_argument("--min-effect", type=float, default=DEFAULT_MIN_EFFECT)
    ap.add_argument("--assign", metavar="EXP_ID")
    ap.add_argument("--arm", choices=["control", "treatment"])
    ap.add_argument("--video", metavar="VIDEO_ID")
    ap.add_argument("--evaluate", metavar="EXP_ID")
    args = ap.parse_args()

    if args.new:
        exp = new_experiment(args.new, args.variable, args.metric, args.control,
                             args.treatment, args.source, args.min_samples,
                             args.min_views, args.min_effect)
        print(f"created {exp['id']}: {exp['hypothesis']}")
    elif args.assign:
        if not (args.arm and args.video):
            raise SystemExit("--assign needs --arm and --video")
        exp = assign(args.assign, args.arm, args.video)
        print(f"{exp['id']}: {args.video} -> {args.arm} arm "
              f"({len(exp['arms']['control'])} control / {len(exp['arms']['treatment'])} treatment)")
    elif args.evaluate:
        exp = evaluate_experiment(args.evaluate)
        v = exp["verdict"]
        print(f"{exp['id']}  {exp['hypothesis']}")
        print(f"  status : {v['status'].upper()} — {v['reason']}")
        print(f"  arms   : control n={v['n_a']} mean={v['mean_a']}  "
              f"treatment n={v['n_b']} mean={v['mean_b']}")
        if v.get("p") is not None:
            print(f"  stats  : diff={v['diff']:+.2f}  t={v['t']:.3f}  df={v['df']:.1f}  p={v['p']:.4f}")
        for s in v.get("skipped", []):
            print(f"  skipped: {s}")
        print(f"  lesson allowed: {may_become_lesson(v)}")
    else:
        print(board())


if __name__ == "__main__":
    main()
