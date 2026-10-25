from __future__ import annotations

from harness.lua_tables import call_histogram, table_shape
from helpers import fixture_text


def test_table_shape_keys_nested_and_samples() -> None:
    shape = table_shape(fixture_text("strings_small.lua"), 2, 9)
    assert shape is not None
    assert shape.entries == 2 and shape.keyed == 2
    assert shape.value_kinds["table"] == 2
    assert shape.nested_keys["PIG"] == 1
    assert "table X" in shape.render("X")


def test_table_shape_positional_and_missing() -> None:
    shape = table_shape('T = { "a", "b", 3, true, nil, function() end }', 1, 1)
    assert shape is not None and shape.positional == 6
    assert set(shape.value_kinds) == {"string", "number", "boolean", "nil", "function"}
    assert table_shape("x = 1", 1, 1) is None


def test_bracket_keys_and_unclosed_table() -> None:
    shape = table_shape('T = { ["a b"] = 1, c = 2', 1, 1)
    assert shape is not None and shape.keyed == 2


def test_call_histogram_counts_method_calls() -> None:
    src = "Inv:Add('a')\nInv:Add('b')\nfoo(1)\n"
    top = call_histogram(src)
    assert top[0][:2] == ("Inv:Add", 2)
