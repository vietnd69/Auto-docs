"""
Structural verification of chunked_prompt.py changes.
Checks that prompt strings contain expected patterns after edits.
Run: python test_chunk_prompts.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from prompts.chunked import build_chunk_prompt, build_merge_prompt
from prompts.pre_synthesis import PreSynthesisResult

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


def _make_presynthesis(**kwargs):
    defaults = dict(
        game_tags=[{"name": "fire", "operation": "check"}],
        external_deps=[{"name": "TheWorld", "usage": "world checks"}],
        system_scope="entity",
        dependencies=[{"component": "health", "usage": "DoDelta"}],
        partial_descriptions=["test description"],
        functions=[],
        events_listens=[],
        events_pushes=[],
        constructor_properties=[],
    )
    defaults.update(kwargs)
    return PreSynthesisResult(**defaults)


# -- build_chunk_prompt --
print("\n-- build_chunk_prompt() schema --")

chunk_prompt = build_chunk_prompt(
    "testcomp", "TestComp", "scripts/test.lua", "-- lua code", 1, 2
)

check("chunk prompt: 'game_tags' field in schema",
     '"game_tags"' in chunk_prompt,
     "game_tags not found in prompt")

check("chunk prompt: 'external_deps' field in schema",
     '"external_deps"' in chunk_prompt,
     "external_deps not found in prompt")

check("chunk prompt: old 'tags' field removed from schema",
     '"tags"' not in chunk_prompt,
     "old 'tags' field still present")

check("chunk prompt: extraction rule mentions TheWorld",
     "TheWorld" in chunk_prompt,
     "TheWorld not mentioned in extraction rules")

check("chunk prompt: extraction rule mentions TheNet",
     "TheNet" in chunk_prompt,
     "TheNet not mentioned in extraction rules")

check("chunk prompt: extraction rule mentions require()",
     "require" in chunk_prompt,
     "require not mentioned in extraction rules")


# -- build_merge_prompt --
print("\n-- build_merge_prompt() --")

presynthesis = _make_presynthesis()
merge_prompt = build_merge_prompt(
    "testcomp", "TestComp", "scripts/test.lua",
    presynthesis,
    today_date="2026-03-14", version="714014",
    category_type="root",
)

# -- format spec included via skills --
print("\n-- format spec in merge prompt --")

check("merge prompt: 'External dependencies' present via skills",
     "External dependencies" in merge_prompt,
     "External dependencies section missing from skills injection")

check("merge prompt: 'Components used' present via skills",
     "Components used" in merge_prompt,
     "Components used section missing from skills injection")

check("merge prompt: 'Tags' label present via skills",
     "Tags" in merge_prompt,
     "Tags section missing from skills injection")

check("merge prompt: old 'copy them exactly' instruction removed",
     "Copy them exactly" not in merge_prompt,
     "old lock instruction still present")

check("merge prompt: YAML tags is a write instruction",
     "WRITE" in merge_prompt,
     "WRITE instruction for YAML tags not found")

check("merge prompt: system_scope has REVIEW hint",
     "REVIEW" in merge_prompt,
     "REVIEW hint for system_scope not found")

check("merge prompt: GAME TAGS section present",
     "GAME TAGS" in merge_prompt,
     "GAME TAGS section not found")

check("merge prompt: EXTERNAL DEPENDENCIES section present",
     "EXTERNAL DEPENDENCIES" in merge_prompt,
     "EXTERNAL DEPENDENCIES section not found")

check("merge prompt: game_tags data injected (fire tag visible)",
     '"fire"' in merge_prompt,
     "fire tag not found in merge prompt")

check("merge prompt: external_deps data injected (TheWorld visible)",
     "TheWorld" in merge_prompt,
     "TheWorld not found in merge prompt")

check("merge prompt: GAME TAGS block appears after DEPENDENCIES block",
     merge_prompt.index("GAME TAGS") > merge_prompt.index("DEPENDENCIES (pre-extracted)"),
     "GAME TAGS not positioned after DEPENDENCIES")

check("merge prompt: GAME TAGS block appears before PROPERTIES block",
     merge_prompt.index("GAME TAGS") < merge_prompt.index("PROPERTIES (pre-extracted)"),
     "GAME TAGS not positioned before PROPERTIES")


# -- empty external_deps --
print("\n-- build_merge_prompt() with empty external_deps --")

presynthesis_no_ext = _make_presynthesis(external_deps=[])
merge_prompt_no_ext = build_merge_prompt(
    "testcomp", "TestComp", "scripts/test.lua",
    presynthesis_no_ext,
    today_date="2026-03-14", version="714014",
    category_type="root",
)
check("empty external_deps: prompt still generated (no crash)",
     len(merge_prompt_no_ext) > 100,
     "prompt unexpectedly short or empty")


# -- ordering and structural completeness --
print("\n-- merge prompt ordering --")

# Confirm EXTERNAL DEPENDENCIES is positioned between GAME TAGS and PROPERTIES
check("merge prompt: EXTERNAL DEPENDENCIES between GAME TAGS and PROPERTIES",
     merge_prompt.index("EXTERNAL DEPENDENCIES") > merge_prompt.index("GAME TAGS") and
     merge_prompt.index("EXTERNAL DEPENDENCIES") < merge_prompt.index("PROPERTIES (pre-extracted)"),
     "EXTERNAL DEPENDENCIES not positioned between GAME TAGS and PROPERTIES")

# Confirm bare system_scope line (old format: "system_scope: entity") is gone.
# New format: system_scope: <REVIEW hint "entity" -- ...> which does NOT match "system_scope: entity\n"
check("merge prompt: bare pre-filled system_scope line removed",
     f"system_scope: {presynthesis.system_scope}\n" not in merge_prompt,
     "bare pre-filled system_scope line still present")

# Confirm task 7 in YOUR TASKS section references External dependencies.
# "Copy them exactly" exact casing confirmed from source line 383: "Copy them exactly."
check("merge prompt: 'Copy them exactly' instruction removed",
     "Copy them exactly" not in merge_prompt,
     "old lock instruction still present (casing: 'Copy them exactly')")

check("merge prompt: task 7 references External dependencies",
     "External dependencies" in merge_prompt and "EXTERNAL DEPENDENCIES JSON" in merge_prompt,
     "task 7 not updated to reference External dependencies")


print(f"\n{'='*40}")
print(f"Results: {passed} passed, {failed} failed")
if failed:
    sys.exit(1)
