from __future__ import annotations

from pathlib import Path

import pytest

from harness.codeindex import build_file_index
from harness.plan import load_plan, owned_symbols, require_executable, save_plan, validate_plan
from harness.structureplan import build_structure, destination, source_signals


def test_registry_and_env_signals_ignore_comments_and_strings() -> None:
    source = """-- AddTask("fake", {})
local text = 'env.Fake = function() end'
env.AddPrefabPostInit = function(name, fn) end
AddTask("Forest", {})
CommonStates.AddWalkStates(states)
return MakeAxe("goldenaxe", nil)
"""
    signals = source_signals(source)
    assert {o["name"] for o in signals["candidate_objects"]} == {
        "env.AddPrefabPostInit",
        "AddTask:Forest",
        "goldenaxe",
    }
    assert signals["injected_states"] == [{"helper": "AddWalkStates", "line": 5}]


def test_catalog_family_and_mixed_data_routes() -> None:
    assert destination("map/static_layouts/foo.lua") == ("data/layouts/catalog", "catalog")
    assert destination("map/static_layouts/bar.lua") == destination("map/static_layouts/foo.lua")
    assert destination("preparedfoods.lua")[1] == "mixed-data"
    assert destination("prefabs/axe.lua") == ("reference/prefabs/tools/axes", "prefab-family")


def test_structure_owns_every_symbol_and_preserves_metadata(tmp_path: Path) -> None:
    source = "\n".join(f"function Health:Attack{i}() end" for i in range(32))
    source += "\nfunction Health:Save() end"
    sources = {"components/health.lua": source, "components/health_replica.lua": "function Health:Get() end"}
    index = {p: build_file_index(p, s) for p, s in sources.items()}
    plan = build_structure(index, sources)
    assert validate_plan(plan, index) == []
    assert plan.page("reference/components/health/replica")
    assert plan.page("reference/components/health/server/combat")
    for page in plan.pages:
        units = plan.structure["pages"][page.id]["work_units"]
        actual = [(s["file"], s["symbol"]) for u in units for s in u["symbols"]]
        assert sorted(actual) == sorted(owned_symbols(page, index))
        assert all(len(u["symbols"]) <= 8 for u in units)
    path = tmp_path / "doc-plan.json"
    save_plan(plan, path)
    loaded = load_plan(path)
    assert loaded.to_json() == plan.to_json()
    with pytest.raises(ValueError, match="not executable"):
        require_executable(loaded)


def test_giant_symbol_is_explicitly_unresolved() -> None:
    source = "function Giant()\n" + "value = value + 1000000000000\n" * 2000 + "end"
    index = {"giant.lua": build_file_index("giant.lua", source)}
    plan = build_structure(index, {"giant.lua": source})
    details = plan.structure["pages"][plan.pages[0].id]
    assert details["work_units"][0]["needs_range_split"] is True
    assert plan.structure["execution_ready"] is False
