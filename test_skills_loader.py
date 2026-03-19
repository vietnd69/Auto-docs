"""
Tests for skills_loader.py — index parsing and skill file loading.
Run: .venv/Scripts/python test_skills_loader.py
"""
import sys, os, tempfile
from pathlib import Path
sys.path.insert(0, os.path.dirname(__file__))

passed = 0
failed = 0

def test(name, condition, msg=""):
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
    from skills_loader import load_skill

    # T1: returns skill content (header is stripped by loader)
    with tempfile.TemporaryDirectory() as d:
        content = "# Skill: alpha\nHello world"
        _make_skill(d, "skills/alpha.md", content)
        idx = _make_index(d, [{"name": "alpha", "file": "skills/alpha.md", "inject_into": ["single_prompt"]}])
        result = load_skill("alpha", index_path=idx)
        test("load_skill returns file content (header stripped)", result == "Hello world", f"got: {result!r}")

    # T2: unknown name raises KeyError
    with tempfile.TemporaryDirectory() as d:
        idx = _make_index(d, [])
        try:
            load_skill("ghost", index_path=idx)
            test("load_skill unknown name raises KeyError", False, "no exception raised")
        except KeyError as e:
            test("load_skill unknown name raises KeyError", "not found" in str(e), str(e))

    # T3: skill file missing raises FileNotFoundError
    with tempfile.TemporaryDirectory() as d:
        idx = _make_index(d, [{"name": "missing", "file": "skills/missing.md", "inject_into": ["single_prompt"]}])
        try:
            load_skill("missing", index_path=idx)
            test("load_skill missing file raises FileNotFoundError", False, "no exception raised")
        except FileNotFoundError:
            test("load_skill missing file raises FileNotFoundError", True)

    # T4: reads utf-8 content correctly (Vietnamese characters, header stripped)
    with tempfile.TemporaryDirectory() as d:
        content = "# Skill: utf\nViệt Nam — DST"
        _make_skill(d, "skills/utf.md", content)
        idx = _make_index(d, [{"name": "utf_skill", "file": "skills/utf.md", "inject_into": ["single_prompt"]}])
        result = load_skill("utf_skill", index_path=idx)
        test("load_skill reads utf-8 content", "Việt Nam" in result and "# Skill:" not in result, f"got: {result!r}")

    # T5: malformed index — entry has no 'file:' line → ValueError
    with tempfile.TemporaryDirectory() as d:
        bad_index = os.path.join(d, "docs_SKILL.md")
        Path(bad_index).write_text(
            "---\nversion: 1\n---\n\n## bad_skill\ninject_into: [single_prompt]\n",
            encoding="utf-8",
        )
        try:
            load_skill("bad_skill", index_path=bad_index)
            test("load_skill malformed index raises ValueError", False, "no exception raised")
        except ValueError as e:
            test("load_skill malformed index raises ValueError", "missing 'file:'" in str(e), str(e))


# ── load_skills_for tests ─────────────────────────────────────────────────────

def run_load_skills_for_tests():
    from skills_loader import load_skills_for

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
        test("load_skills_for returns matching skills",
             set(result.keys()) == {"skill_a", "skill_b"} and result["skill_a"] == "content a",
             f"keys: {set(result.keys())}")

    # T7: no match → returns empty dict (not an error)
    with tempfile.TemporaryDirectory() as d:
        _make_skill(d, "skills/a.md", "content a")
        idx = _make_index(d, [{"name": "skill_a", "file": "skills/a.md", "inject_into": ["chunk_prompt"]}])
        result = load_skills_for("merge_prompt", index_path=idx)
        test("load_skills_for returns empty dict when no match", result == {}, f"got: {result}")

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
        test("load_skills_for all 3 targets work", ok)


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n=== load_skill tests ===")
    run_load_skill_tests()
    print("\n=== load_skills_for tests ===")
    run_load_skills_for_tests()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
