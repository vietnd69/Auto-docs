# test_file_type_detection.py
"""
Tests for _detect_file_type() in prompts/standard.py.
Run: .venv/Scripts/python test_file_type_detection.py
"""
import sys, os
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

from prompts.standard import _detect_file_type

print("=== _detect_file_type ===")

# Root-level files (no subdir) → data_config
test("root ./achievements.lua",     _detect_file_type("./achievements.lua")     == "data_config")
test("root ./actions.lua",          _detect_file_type("./actions.lua")          == "data_config")
test("root no-prefix achievements", _detect_file_type("achievements.lua")       == "data_config")

# map/ tree → data_config
test("map top-level",               _detect_file_type("./map/archive_worldgen.lua") == "data_config")
test("map nested levels/",          _detect_file_type("./map/levels/caves.lua")     == "data_config")
test("map nested tasks/",           _detect_file_type("./map/tasks/caves.lua")      == "data_config")
test("map nested static_layouts/",  _detect_file_type("./map/static_layouts/abandonedboat.lua") == "data_config")

# languages/ and util/ → data_config
test("languages/",                  _detect_file_type("./languages/language.lua") == "data_config")
test("util/",                       _detect_file_type("./util/emoji.lua")          == "data_config")

# Component-like dirs → component
test("components/",                 _detect_file_type("./components/combat.lua")       == "component")
test("brains/",                     _detect_file_type("./brains/abigailbrain.lua")     == "component")
test("prefabs/",                    _detect_file_type("./prefabs/abigail.lua")         == "component")
test("stategraphs/",                _detect_file_type("./stategraphs/SGabigail.lua")   == "component")
test("screens/",                    _detect_file_type("./screens/bigpopupdialog.lua")  == "component")
test("widgets/",                    _detect_file_type("./widgets/animbutton.lua")      == "component")
test("behaviours/",                 _detect_file_type("./behaviours/approach.lua")     == "component")
test("scenarios/",                  _detect_file_type("./scenarios/archive_cookpot.lua") == "component")
test("screens redux/",              _detect_file_type("./screens/redux/achievementspopup.lua") == "component")

# Windows backslash paths
test("backslash components/",       _detect_file_type(".\\components\\combat.lua")   == "component")
test("backslash map/",              _detect_file_type(".\\map\\levels\\caves.lua")   == "data_config")
test("backslash root",              _detect_file_type(".\\achievements.lua")         == "data_config")

print(f"\n{passed} passed, {failed} failed")
if failed:
    sys.exit(1)
