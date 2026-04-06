"""
Tests for skills_loader.py — index parsing and skill file loading.
Run: .venv/Scripts/python test_skills_loader.py
"""
import sys, os, tempfile
from pathlib import Path
sys.path.insert(0, os.path.dirname(__file__))

passed = 0
failed = 0

def check(name, condition, msg=""):
    global passed, failed
    if condition:
        print(f"  [PASS] {name}")
        passed += 1
    else:
        print(f"  [FAIL] {name} -- {msg}")
        failed += 1


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_index(dirpath: str, skills: list[dict]) -> str:
    """Write docs_SKILL.md in dirpath. Returns absolute path to the index file."""
    lines = ["---", "version: 1", "---", ""]
    for s in skills:
        targets = ", ".join(s.get("inject_into", []))
        lines += [f"## {s['name']}", f"file: {s['file']}", f"inject_into: [{targets}]", ""]
    index_path = os.path.join(dirpath, "docs_SKILL.md")
    Path(index_path).write_text("\n".join(lines), encoding="utf-8")
    return index_path


def _make_skill(dirpath: str, rel_path: str, content: str) -> str:
    """Create a skill .md file at rel_path inside dirpath. Returns absolute path."""
    full = Path(dirpath) / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return str(full)


# ── load_skill tests ──────────────────────────────────────────────────────────

def run_load_skill_tests():
    from prompts.skills_loader import load_skill

    # T1: returns skill content (header is stripped by loader)
    with tempfile.TemporaryDirectory() as d:
        content = "# Skill: alpha\nHello world"
        _make_skill(d, "skills/alpha.md", content)
        idx = _make_index(d, [{"name": "alpha", "file": "skills/alpha.md", "inject_into": ["single_prompt"]}])
        result = load_skill("alpha", index_path=idx)
        check("load_skill returns file content (header stripped)", result == "Hello world", f"got: {result!r}")

    # T2: unknown name raises KeyError
    with tempfile.TemporaryDirectory() as d:
        idx = _make_index(d, [])
        try:
            load_skill("ghost", index_path=idx)
            check("load_skill unknown name raises KeyError", False, "no exception raised")
        except KeyError as e:
            check("load_skill unknown name raises KeyError", "not found" in str(e), str(e))

    # T3: skill file missing raises FileNotFoundError
    with tempfile.TemporaryDirectory() as d:
        idx = _make_index(d, [{"name": "missing", "file": "skills/missing.md", "inject_into": ["single_prompt"]}])
        try:
            load_skill("missing", index_path=idx)
            check("load_skill missing file raises FileNotFoundError", False, "no exception raised")
        except FileNotFoundError:
            check("load_skill missing file raises FileNotFoundError", True)

    # T4: reads utf-8 content correctly (Vietnamese characters, header stripped)
    with tempfile.TemporaryDirectory() as d:
        content = "# Skill: utf\nViệt Nam — DST"
        _make_skill(d, "skills/utf.md", content)
        idx = _make_index(d, [{"name": "utf_skill", "file": "skills/utf.md", "inject_into": ["single_prompt"]}])
        result = load_skill("utf_skill", index_path=idx)
        check("load_skill reads utf-8 content", "Việt Nam" in result and "# Skill:" not in result, f"got: {result!r}")

    # T5: malformed index — entry has no 'file:' line → ValueError
    with tempfile.TemporaryDirectory() as d:
        bad_index = os.path.join(d, "docs_SKILL.md")
        Path(bad_index).write_text(
            "---\nversion: 1\n---\n\n## bad_skill\ninject_into: [single_prompt]\n",
            encoding="utf-8",
        )
        try:
            load_skill("bad_skill", index_path=bad_index)
            check("load_skill malformed index raises ValueError", False, "no exception raised")
        except ValueError as e:
            check("load_skill malformed index raises ValueError", "missing 'file:'" in str(e), str(e))


# ── load_skills_for tests ─────────────────────────────────────────────────────

def run_load_skills_for_tests():
    from prompts.skills_loader import load_skills_for

    # T6: filters by target, returns matching skills only
    with tempfile.TemporaryDirectory() as d:
        _make_skill(d, "skills/a.md", "content a")
        _make_skill(d, "skills/b.md", "content b")
        _make_skill(d, "skills/c.md", "content c")
        idx = _make_index(d, [
            {"name": "skill_a", "file": "skills/a.md", "inject_into": ["chunk_prompt", "single_prompt"]},
            {"name": "skill_b", "file": "skills/b.md", "inject_into": ["single_prompt"]},
            {"name": "skill_c", "file": "skills/c.md", "inject_into": ["merge_prompt"]},
        ])
        result = load_skills_for("single_prompt", index_path=idx)
        check("load_skills_for returns matching skills",
             set(result.keys()) == {"skill_a", "skill_b"} and result["skill_a"] == "content a",
             f"keys: {set(result.keys())}")

    # T7: no match → returns empty dict (not an error)
    with tempfile.TemporaryDirectory() as d:
        _make_skill(d, "skills/a.md", "content a")
        idx = _make_index(d, [{"name": "skill_a", "file": "skills/a.md", "inject_into": ["chunk_prompt"]}])
        result = load_skills_for("merge_prompt", index_path=idx)
        check("load_skills_for returns empty dict when no match", result == {}, f"got: {result}")

    # T8: all 3 allowed targets work as filters
    with tempfile.TemporaryDirectory() as d:
        for target in ("chunk_prompt", "merge_prompt", "single_prompt"):
            _make_skill(d, f"skills/{target}.md", f"content {target}")
        idx = _make_index(d, [
            {"name": "s1", "file": "skills/chunk_prompt.md",  "inject_into": ["chunk_prompt"]},
            {"name": "s2", "file": "skills/merge_prompt.md",  "inject_into": ["merge_prompt"]},
            {"name": "s3", "file": "skills/single_prompt.md", "inject_into": ["single_prompt"]},
        ])
        ok = (
            set(load_skills_for("chunk_prompt",  index_path=idx).keys()) == {"s1"} and
            set(load_skills_for("merge_prompt",  index_path=idx).keys()) == {"s2"} and
            set(load_skills_for("single_prompt", index_path=idx).keys()) == {"s3"}
        )
        check("load_skills_for all 3 targets work", ok)


# ── combine_skills tests (new API, uses _registry_override) ──────────────────

def run_combine_skills_tests():
    from prompts.skills_loader import combine_skills, _clear_cache

    # Build a mock registry for testing (no filesystem needed)
    mock_registry = {
        "analyst": {
            "name": "analyst",
            "inject_into": ["analyst", "analyst_chunk"],
            "content": "role content",
            "group": 0,
            "path": "roles/analyst.md",
        },
        "dst_conventions": {
            "name": "dst_conventions",
            "inject_into": ["analyst", "analyst_chunk"],
            "content": "knowledge content",
            "group": 1,
            "path": "knowledge/dst_conventions.md",
        },
        "function_format": {
            "name": "function_format",
            "inject_into": ["analyst"],
            "content": "format content",
            "group": 1,
            "path": "knowledge/function_format.md",
        },
        "content_rules": {
            "name": "content_rules",
            "inject_into": ["analyst", "analyst_chunk"],
            "content": "rules content",
            "group": 2,
            "path": "rules/content_rules.md",
        },
        "format_rules": {
            "name": "format_rules",
            "inject_into": ["analyst"],
            "content": "format rules content",
            "group": 2,
            "path": "rules/format_rules.md",
        },
    }

    # T9: combine_skills returns concatenated content in group order
    result = combine_skills("analyst", _registry_override=mock_registry)
    check("combine_skills group order: role -> knowledge -> rules",
          result.startswith("=== SKILL: analyst ==="),
          f"got: {result[:60]!r}")

    # T10: within-group alphabetical ordering
    check("combine_skills alphabetical within knowledge group",
          result.index("dst_conventions") < result.index("function_format"),
          "dst_conventions should come before function_format")

    check("combine_skills alphabetical within rules group",
          result.index("content_rules") < result.index("format_rules"),
          "content_rules should come before format_rules")

    # T11: exclude parameter works
    result_excl = combine_skills("analyst", exclude=["function_format"], _registry_override=mock_registry)
    check("combine_skills exclude removes skill",
          "function_format" not in result_excl and "dst_conventions" in result_excl,
          f"got: {result_excl[:80]!r}")

    # T12: unknown target returns empty string (not error)
    result_empty = combine_skills("nonexistent_target", _registry_override=mock_registry)
    check("combine_skills unknown target returns empty string",
          result_empty == "",
          f"got: {result_empty!r}")

    # T13: exclude with unknown name is silently ignored
    result_unk = combine_skills("analyst", exclude=["no_such_skill"], _registry_override=mock_registry)
    check("combine_skills exclude unknown name silently ignored",
          "analyst" in result_unk,
          "should still return results")

    # T14: separator format is correct
    check("combine_skills separator format",
          "=== SKILL: analyst ===" in result and "=== SKILL: dst_conventions ===" in result,
          "separator markers missing")

    # T15: content is included after separator
    idx = result.index("=== SKILL: analyst ===")
    after_sep = result[idx:idx+40]
    check("combine_skills content after separator",
          "role content" in after_sep,
          f"got: {after_sep!r}")

    # T16: _clear_cache resets module state
    _clear_cache()
    check("_clear_cache runs without error", True)


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n=== load_skill tests ===")
    run_load_skill_tests()
    print("\n=== load_skills_for tests ===")
    run_load_skills_for_tests()
    print("\n=== combine_skills tests ===")
    run_combine_skills_tests()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
