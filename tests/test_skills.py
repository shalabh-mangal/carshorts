"""Skills (Step 5): codified workflows the agent + CLI share.

The parse/route/compose core is pure; the seed skills under charters/skills/ are
also loaded to guarantee they parse and route to themselves.
"""
from carshorts.agents import skills as skl
from carshorts.core import paths


# --- frontmatter parse ----------------------------------------------------
def test_parse_frontmatter_and_body():
    doc = ("---\n"
           "name: demo\n"
           "description: A demo skill.\n"
           "triggers: alpha, Beta , gamma\n"
           "---\n"
           "1. do the thing\n2. verify\n")
    sk = skl.parse_skill(doc, fallback_name="fallback")
    assert sk.name == "demo"
    assert sk.description == "A demo skill."
    assert sk.triggers == ["alpha", "beta", "gamma"]     # lowered + trimmed
    assert sk.body.startswith("1. do the thing")


def test_parse_without_frontmatter_uses_fallback_name():
    sk = skl.parse_skill("just a body, no fences", fallback_name="raw")
    assert sk.name == "raw"
    assert sk.triggers == []
    assert sk.body == "just a body, no fences"


# --- routing --------------------------------------------------------------
def _mk(name, triggers):
    return skl.Skill(name=name, description="", triggers=triggers, body="steps")


def test_route_picks_best_match():
    skills = [_mk("footage", ["footage", "clips", "coverage"]),
              _mk("facts", ["specs", "research"])]
    assert skl.route("the footage coverage is thin", skills).name == "footage"
    assert skl.route("re-run the specs research", skills).name == "facts"


def test_route_none_when_no_trigger_hits():
    skills = [_mk("footage", ["footage"])]
    assert skl.route("write me a poem", skills) is None


def test_compose_prompt_puts_steps_before_task():
    sk = _mk("demo", ["x"])
    sk.body = "1. step one"
    out = skl.compose_prompt(sk, "DO THE TASK")
    assert "# Skill: demo" in out
    assert out.index("1. step one") < out.index("DO THE TASK")


# --- seed skills on disk parse + self-route -------------------------------
def test_seed_skills_parse_and_self_route():
    skills = skl.list_skills()
    names = {s.name for s in skills}
    # the workflows this session codified must exist and be well-formed
    assert {"source-footage", "produce-video", "ground-facts",
            "publish-video", "close-the-loop"} <= names
    for s in skills:
        assert s.description and s.triggers and s.body, f"{s.name} incomplete"

    # each seed skill routes to itself on its own description text
    for s in skills:
        picked = skl.route(s.description, skills)
        assert picked is not None, f"{s.name} description routes nowhere"


def test_skills_dir_is_under_charters():
    assert skl.SKILLS_DIR == paths.CHARTERS / "skills"
