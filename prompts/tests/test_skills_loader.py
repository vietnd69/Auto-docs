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
          "entity component system" in dst.lower(), f"unexpected content: {dst[:40]}")

    # T16: _clear_cache works
    _clear_cache()
    check("integration: _clear_cache runs", True)


# -- few_shot_excludes tests -----------------------------------------------

def run_few_shot_excludes_tests():
    from prompts.skills_loader import few_shot_excludes

    ALL_FEW_SHOTS = {
        "few_shot", "few_shot_brain", "few_shot_behaviour",
        "few_shot_stategraph", "few_shot_widget", "few_shot_screen",
        "few_shot_prefab", "few_shot_data",
    }

    # T-FS1: brains type keeps only few_shot_brain
    excl = set(few_shot_excludes("brains"))
    check("few_shot_excludes brains: excludes 7",
          len(excl) == 7, f"got {len(excl)}")
    check("few_shot_excludes brains: few_shot_brain NOT excluded",
          "few_shot_brain" not in excl, "few_shot_brain was excluded")
    check("few_shot_excludes brains: replica_pattern NOT in excludes",
          "replica_pattern" not in excl, "replica_pattern should never be excluded")

    # T-FS2: data_config keeps only few_shot_data
    excl = set(few_shot_excludes("data_config"))
    check("few_shot_excludes data_config: few_shot_data NOT excluded",
          "few_shot_data" not in excl, "few_shot_data was excluded")
    check("few_shot_excludes data_config: few_shot_brain excluded",
          "few_shot_brain" in excl, "few_shot_brain should be excluded")

    # T-FS3: replica keeps few_shot (general)
    excl = set(few_shot_excludes("replica"))
    check("few_shot_excludes replica: few_shot NOT excluded",
          "few_shot" not in excl, "few_shot was excluded for replica")

    # T-FS4: unknown type keeps few_shot (general fallback)
    excl = set(few_shot_excludes("nonexistent"))
    check("few_shot_excludes unknown: few_shot NOT excluded",
          "few_shot" not in excl, "few_shot was excluded for unknown type")

    # T-FS5: returns a list (not set)
    result = few_shot_excludes("brains")
    check("few_shot_excludes returns list",
          isinstance(result, list), f"got {type(result)}")


# -- load_trimmed_writing_guide tests ----------------------------------------

def run_trimmed_writing_guide_tests():
    from prompts.skills_loader import load_trimmed_writing_guide, _clear_cache
    _clear_cache()

    # T-WG1: brains type contains Brain section
    result = load_trimmed_writing_guide("brains")
    check("writing_guide brains: has Brain section",
          "Brain Files" in result or "brain files" in result.lower(),
          f"Brain section missing")

    # T-WG2: brains type does NOT contain other type sections
    check("writing_guide brains: no Behaviour section",
          "Behaviour Files" not in result, "Behaviour section present for brains")
    check("writing_guide brains: no Widget section",
          "Widget Files" not in result, "Widget section present for brains")
    check("writing_guide brains: no Screen section",
          "Screen Files" not in result, "Screen section present for brains")
    check("writing_guide brains: no Prefab section",
          "Prefab Files" not in result, "Prefab section present for brains")
    check("writing_guide brains: no Replica section",
          "Replica Files" not in result, "Replica section present for brains")

    # T-WG3: replica type contains Replica section only
    result = load_trimmed_writing_guide("replica")
    check("writing_guide replica: has Replica section",
          "Replica Files" in result, "Replica section missing")
    check("writing_guide replica: no Brain section",
          "Brain Files" not in result, "Brain section present for replica")

    # T-WG4: cameras type has no type-specific sections
    result = load_trimmed_writing_guide("cameras")
    for section in ["Brain Files", "Behaviour Files", "Widget Files", "Screen Files", "Prefab Files", "Replica Files"]:
        check(f"writing_guide cameras: no {section}",
              section not in result, f"{section} present for cameras")

    # T-WG5: common content is always present
    result = load_trimmed_writing_guide("brains")
    check("writing_guide brains: Constructor Rule present",
          "Constructor Rule" in result, "Constructor Rule missing")
    check("writing_guide brains: Non-Trivial Mechanics present",
          "Non-Trivial Mechanics" in result, "Non-Trivial Mechanics missing")

    # T-WG6: markers stripped from output (not visible to LLM)
    check("writing_guide markers stripped",
          "<!-- type:" not in result and "<!-- /type -->" not in result,
          "Markers visible in output")


# -- pytest entry points ----------------------------------------------------

def test_few_shot_excludes():
    run_few_shot_excludes_tests()
    assert failed == 0, f"{failed} check(s) failed in run_few_shot_excludes_tests"


def test_trimmed_writing_guide():
    run_trimmed_writing_guide_tests()
    assert failed == 0, f"{failed} check(s) failed in run_trimmed_writing_guide_tests"


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
    print("\n=== few_shot_excludes tests ===")
    run_few_shot_excludes_tests()
    print("\n=== load_trimmed_writing_guide tests ===")
    run_trimmed_writing_guide_tests()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
