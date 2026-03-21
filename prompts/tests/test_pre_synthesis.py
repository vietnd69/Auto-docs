"""
Tests for pre_synthesis.py schema changes:
- tags field removed, game_tags + external_deps added
- _aggregate() reads from game_tags / external_deps keys
- _empty_result() has correct defaults
Run: python test_pre_synthesis.py
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))

from prompts.pre_synthesis import pre_synthesize, _empty_result

passed = 0
failed = 0

def test(name, condition, msg=""):
    global passed, failed
    if condition:
        print(f"  [PASS] {name}")
        passed += 1
    else:
        print(f"  [FAIL] {name} — {msg}")
        failed += 1


def _chunk(**kwargs):
    """Build a minimal valid chunk JSON dict."""
    base = {
        "partial_description": "test chunk",
        "suggested_scope": "entity",
        "constructor_properties": [],
        "functions": [],
        "events": {"listens_to": [], "pushes": []},
        "dependencies": [],
        "game_tags": [],
        "external_deps": [],
    }
    base.update(kwargs)
    return json.dumps(base)


# ── _empty_result ──────────────────────────────────────────────
print("\n── _empty_result() ──")

result = _empty_result()

test("no 'tags' attribute",
     not hasattr(result, "tags"),
     "PreSynthesisResult still has deprecated 'tags' field")

test("has 'game_tags' attribute",
     hasattr(result, "game_tags"),
     "game_tags field missing")

test("has 'external_deps' attribute",
     hasattr(result, "external_deps"),
     "external_deps field missing")

test("game_tags default is []",
     result.game_tags == [],
     f"got {result.game_tags!r}")

test("external_deps default is []",
     result.external_deps == [],
     f"got {result.external_deps!r}")

test("system_scope default is 'entity'",
     result.system_scope == "entity",
     f"got {result.system_scope!r}")


# ── pre_synthesize: game_tags ──────────────────────────────────
print("\n── pre_synthesize: game_tags ──")

chunks_game_tags = {
    1: _chunk(game_tags=[
        {"name": "player", "operation": "check"},
        {"name": "fire", "operation": "check"},
    ]),
    2: _chunk(game_tags=[
        {"name": "fire", "operation": "add"},   # duplicate name — should be deduped
        {"name": "heavy", "operation": "check"},
    ]),
}
r, malformed = pre_synthesize(chunks_game_tags)

test("no malformed chunks", malformed == [], f"malformed: {malformed}")

names = {t["name"] for t in r.game_tags}
test("game_tags: all unique names collected",
     names == {"player", "fire", "heavy"},
     f"got names {names}")

fire_entries = [t for t in r.game_tags if t["name"] == "fire"]
test("game_tags: 'fire' deduped to one entry",
     len(fire_entries) == 1,
     f"got {len(fire_entries)} entries for 'fire'")

test("game_tags: first-seen operation preserved for 'fire'",
     fire_entries[0]["operation"] == "check",
     f"got {fire_entries[0]['operation']!r}")


# ── pre_synthesize: external_deps ─────────────────────────────
print("\n── pre_synthesize: external_deps ──")

chunks_ext = {
    1: _chunk(external_deps=[
        {"name": "TheWorld", "usage": "TheWorld:HasTag() — checks world state"},
        {"name": "class",    "usage": "Class() constructor"},
    ]),
    2: _chunk(external_deps=[
        {"name": "TheWorld", "usage": "duplicate — should be discarded"},
        {"name": "TheNet",   "usage": "TheNet:GetIsServer()"},
    ]),
}
r2, malformed2 = pre_synthesize(chunks_ext)

test("no malformed chunks", malformed2 == [], f"malformed: {malformed2}")

ext_names = {d["name"] for d in r2.external_deps}
test("external_deps: all unique names collected",
     ext_names == {"TheWorld", "class", "TheNet"},
     f"got {ext_names}")

theworld = next((d for d in r2.external_deps if d["name"] == "TheWorld"), None)
test("external_deps: first-seen usage preserved for TheWorld",
     theworld is not None and theworld["usage"].startswith("TheWorld:HasTag()"),
     f"got {theworld!r}")


# ── pre_synthesize: old 'tags' key silently ignored ────────────
print("\n── pre_synthesize: backward compatibility ──")

chunk_old_format = {
    "partial_description": "old format chunk",
    "suggested_scope": "entity",
    "constructor_properties": [],
    "functions": [],
    "events": {"listens_to": [], "pushes": []},
    "dependencies": [],
    "game_tags": [],
    "external_deps": [],
    "tags": [{"name": "legacy_tag", "operation": "check"}],  # old key
}
r3, m3 = pre_synthesize({1: json.dumps(chunk_old_format)})

test("old 'tags' key in chunk JSON does not populate game_tags",
     r3.game_tags == [],
     f"game_tags unexpectedly populated: {r3.game_tags}")


# ── pre_synthesize: None-filtered entries ─────────────────────
print("\n── pre_synthesize: None filtering ──")

chunks_none = {
    1: _chunk(
        game_tags=[{"name": "None", "operation": "check"}],
        external_deps=[{"name": "None", "usage": "None"}],
    ),
}
r4, _ = pre_synthesize(chunks_none)
test("game_tags: 'None' string filtered out",
     r4.game_tags == [],
     f"got {r4.game_tags}")
test("external_deps: 'None' string filtered out",
     r4.external_deps == [],
     f"got {r4.external_deps}")


# ── summary ───────────────────────────────────────────────────
print(f"\n{'='*40}")
print(f"Results: {passed} passed, {failed} failed")
if failed:
    sys.exit(1)
