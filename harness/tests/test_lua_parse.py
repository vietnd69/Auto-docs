"""Parser: equivalence classes per DST construct plus boundary/malformed inputs (ISO/IEC/IEEE 29119-4)."""

from __future__ import annotations

from harness.lua_lexer import tokenize
from harness.lua_parse import parse_lua, public_symbols
from helpers import fixture_text


def kinds(source: str, module: str = "") -> dict[str, tuple[str, int, int]]:
    return {s.qualname: (s.kind, s.line_start, s.line_end) for s in parse_lua(source, module).symbols}


def test_class_methods_static_and_local_function() -> None:
    facts = parse_lua(fixture_text("components__health.lua"))
    found = {s.qualname: s for s in facts.symbols}
    assert found["Health"].kind == "class"
    assert found["Health"].signature == "Health(self, inst)"
    assert found["Health:GetPercent"].kind == "method"
    assert (found["Health:DoDelta"].line_start, found["Health:DoDelta"].line_end) == (20, 25)
    assert found["Health:DoDelta"].signature == "Health:DoDelta(amount, overtime, cause)"
    assert found["Health.Static"].kind == "function"
    assert found["onmax"].local is True
    assert facts.events_pushed == ["healthdelta"]
    assert facts.tags == ["health"]


def test_public_symbols_exclude_local_helpers() -> None:
    public = [s.qualname for s in public_symbols(parse_lua(fixture_text("components__health.lua")))]
    assert "onmax" not in public
    assert {"Health", "Health:GetPercent", "Health:DoDelta", "Health.Static"} <= set(public)


def test_stategraph_states_handlers_actions() -> None:
    facts = parse_lua(fixture_text("stategraphs__SGpig.lua"))
    found = kinds(fixture_text("stategraphs__SGpig.lua"))
    assert found["State:idle"][0] == "state"
    assert found["State:hit"][0] == "state"
    assert found["Action:EAT"][0] == "action"
    assert found["EventHandler:attacked"][0] == "event_handler"
    assert "EventHandler:animover" not in found  # nested in a state, belongs to the state
    assert facts.requires == ["stategraphs/commonstates"]
    assert "onhitother" in facts.events_listened


def test_anonymous_class_closure_methods_and_long_brackets() -> None:
    found = kinds(fixture_text("world__ambient.lua"), "Ambient")
    assert found["Ambient"][0] == "class"
    assert found["Ambient:OnUpdate"][0] == "method"
    assert found["Ambient:GetDebugString"][0] == "method"
    assert "Fake" not in found  # inside a long comment


def test_generated_data_file_detection() -> None:
    facts = parse_lua(fixture_text("strings_small.lua"))
    assert facts.generated and facts.is_data
    assert kinds(fixture_text("strings_small.lua"))["STRINGS"][0] == "table"


def test_exports_mark_local_functions_public() -> None:
    src = "local function A() end\nlocal function B() end\nreturn { A = A }\n"
    facts = parse_lua(src)
    assert facts.exports == ["A"]
    public = {s.qualname for s in public_symbols(facts)}
    assert "A" in public and "B" not in public


def test_plain_script_falls_back_to_local_functions() -> None:
    public = {s.qualname for s in public_symbols(parse_lua("local function Only() end\nOnly()\n"))}
    assert public == {"Only"}


def test_empty_and_malformed_sources_do_not_raise() -> None:
    assert parse_lua("").symbols == []
    broken = parse_lua("function A(\n  if x then\n")  # unterminated
    assert broken.symbols[0].qualname == "A"


def test_assigned_function_and_prefab() -> None:
    src = 'M.helper = function(a, b) return a end\nreturn Prefab("pig", fn, assets)\n'
    found = kinds(src)
    assert found["M.helper"][0] == "function"
    assert found["Prefab:pig"][0] == "prefab"


def test_lexer_strings_numbers_and_lines() -> None:
    toks = list(tokenize('local s = "a\\"b" -- c\nx = 0x1F + 1e3\ny=[[z]]'))
    strings = [t for t in toks if t.kind == "string"]
    assert [t.value for t in strings] == ['a\\"b', "z"]
    assert [t.line for t in toks if t.kind == "number"] == [2, 2]
