"""
Tests for skills_loader.py -- YAML frontmatter registry and combine_skills API.
Run: .venv/Scripts/pytest prompts/tests/test_skills_loader.py -v
"""
import sys, os
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


# -- Mock registry for unit tests ------------------------------------------

MOCK_REGISTRY = {
    "analyst": {
        "name": "analyst", "inject_into": ["analyst", "analyst_chunk"],
        "content": "role: analyst content", "group": 0, "path": "roles/analyst.md",
    },
    "dst_conventions": {
        "name": "dst_conventions", "inject_into": ["analyst", "analyst_chunk"],
        "content": "knowledge: dst content", "group": 1, "path": "knowledge/dst_conventions.md",
    },
    "function_format": {
        "name": "function_format", "inject_into": ["analyst"],
        "content": "knowledge: format content", "group": 1, "path": "knowledge/function_format.md",
    },
    "content_rules": {
        "name": "content_rules", "inject_into": ["analyst", "analyst_chunk"],
        "content": "rules: content rules", "group": 2, "path": "rules/content_rules.md",
    },
    "format_rules": {
        "name": "format_rules", "inject_into": ["analyst"],
        "content": "rules: format rules", "group": 2, "path": "rules/format_rules.md",
    },
}


# -- combine_skills tests --------------------------------------------------

def run_combine_skills_tests():
    from prompts.skills_loader import combine_skills

    # T1: returns content for matching target
    result = combine_skills("analyst", _registry_override=MOCK_REGISTRY)
    check("combine_skills returns non-empty for valid target",
          len(result) > 0, f"got empty string")

    # T2: group ordering -- role (0) before knowledge (1) before rules (2)
    check("combine_skills: role before knowledge",
          result.index("analyst") < result.index("dst_conventions"),
          "role should come before knowledge")
    check("combine_skills: knowledge before rules",
          result.index("dst_conventions") < result.index("content_rules"),
          "knowledge should come before rules")

    # T3: alphabetical within group
    check("combine_skills: dst_conventions before function_format",
          result.index("dst_conventions") < result.index("function_format"),
          "alphabetical within knowledge group")
    check("combine_skills: content_rules before format_rules",
          result.index("content_rules") < result.index("format_rules"),
          "alphabetical within rules group")

    # T4: separator format
    check("combine_skills: separator present",
          "=== SKILL: analyst ===" in result,
          "separator missing")

    # T5: exclude parameter
    result_excl = combine_skills("analyst", exclude=["function_format"], _registry_override=MOCK_REGISTRY)
    check("combine_skills: exclude removes skill",
          "function_format" not in result_excl and "dst_conventions" in result_excl,
          "exclude did not work")

    # T6: unknown target returns empty string
    result_empty = combine_skills("nonexistent", _registry_override=MOCK_REGISTRY)
    check("combine_skills: unknown target returns ''",
          result_empty == "", f"got: {result_empty!r}")

    # T7: exclude unknown name silently ignored
    result_unk = combine_skills("analyst", exclude=["no_such"], _registry_override=MOCK_REGISTRY)
    check("combine_skills: unknown exclude ignored",
          "analyst" in result_unk, "should still return results")

    # T8: analyst_chunk target only gets matching skills (not function_format/format_rules)
    result_chunk = combine_skills("analyst_chunk", _registry_override=MOCK_REGISTRY)
    check("combine_skills: analyst_chunk excludes non-matching",
          "function_format" not in result_chunk and "format_rules" not in result_chunk,
          "non-matching skills included")
    check("combine_skills: analyst_chunk includes matching",
          "analyst" in result_chunk and "dst_conventions" in result_chunk and "content_rules" in result_chunk,
          "matching skills missing")


# -- load_skill tests -------------------------------------------------------

def run_load_skill_tests():
    from prompts.skills_loader import load_skill

    # T9: returns content by name
    result = load_skill("analyst", _registry_override=MOCK_REGISTRY)
    check("load_skill returns content",
          result == "role: analyst content", f"got: {result!r}")

    # T10: unknown name raises KeyError
    try:
        load_skill("ghost", _registry_override=MOCK_REGISTRY)
        check("load_skill unknown raises KeyError", False, "no exception")
    except KeyError:
        check("load_skill unknown raises KeyError", True)


# -- load_skills_for tests --------------------------------------------------

def run_load_skills_for_tests():
    from prompts.skills_loader import load_skills_for

    # T11: returns matching skills as dict
    result = load_skills_for("analyst_chunk", _registry_override=MOCK_REGISTRY)
    check("load_skills_for returns matching dict",
          set(result.keys()) == {"analyst", "dst_conventions", "content_rules"},
          f"keys: {set(result.keys())}")

    # T12: no match returns empty dict
    result_empty = load_skills_for("nonexistent", _registry_override=MOCK_REGISTRY)
    check("load_skills_for no match returns {}",
          result_empty == {}, f"got: {result_empty}")


# -- integration test with real skill files ---------------------------------

def run_integration_tests():
    from prompts.skills_loader import combine_skills, load_skill, _clear_cache
    _clear_cache()

    # T13: combine_skills on real files returns non-empty
    result = combine_skills("analyst")
    check("integration: analyst target non-empty",
          len(result) > 100, f"got {len(result)} chars")

    # T14: analyst includes expected skill names
    check("integration: analyst has dst_conventions",
          "dst_conventions" in result, "missing dst_conventions")
    check("integration: analyst has function_format",
          "function_format" in result, "missing function_format")
    check("integration: analyst has content_rules",
          "content_rules" in result, "missing content_rules")

    # T15: load_skill on real file
    dst = load_skill("dst_conventions")
    check("integration: load_skill dst_conventions",
          "ENTITY COMPONENT SYSTEM" in dst.upper(), f"unexpected content: {dst[:40]}")

    # T16: _clear_cache works
    _clear_cache()
    check("integration: _clear_cache runs", True)


# -- entry point ------------------------------------------------------------

if __name__ == "__main__":
    print("\n=== combine_skills tests ===")
    run_combine_skills_tests()
    print("\n=== load_skill tests ===")
    run_load_skill_tests()
    print("\n=== load_skills_for tests ===")
    run_load_skills_for_tests()
    print("\n=== integration tests ===")
    run_integration_tests()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
