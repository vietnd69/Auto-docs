"""
Tests for type_detect.py
Run: .venv/Scripts/pytest prompts/tests/test_type_detect.py -v
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


def run_tests():
    from prompts.type_detect import detect_lua_type

    # Directory-based detection
    check("brains dir", detect_lua_type("./brains/pigbrain.lua") == "brains")
    check("behaviours dir", detect_lua_type("./behaviours/chaseandattack.lua") == "behaviours")
    check("stategraphs dir", detect_lua_type("./stategraphs/SGBeefalo.lua") == "stategraphs")
    check("widgets dir", detect_lua_type("./widgets/badge.lua") == "widgets")
    check("screens dir", detect_lua_type("./screens/DebugMenuScreen.lua") == "screens")
    check("prefabs dir", detect_lua_type("./prefabs/abigail.lua") == "prefabs")
    check("components dir", detect_lua_type("./components/combat.lua") == "components")
    check("cameras dir", detect_lua_type("./cameras/followcamera.lua") == "cameras")

    # Data-config directories
    check("map dir", detect_lua_type("./map/something.lua") == "data_config")
    check("languages dir", detect_lua_type("./languages/strings.lua") == "data_config")
    check("util dir", detect_lua_type("./util/helper.lua") == "data_config")

    # Root-level → data_config
    check("root level", detect_lua_type("achievements.lua") == "data_config")
    check("root level dotslash", detect_lua_type("./achievements.lua") == "data_config")

    # Unknown directory → data_config fallback
    check("unknown dir fallback", detect_lua_type("./unknowndir/foo.lua") == "data_config")

    # Replica suffix wins over directory
    check("replica suffix in components", detect_lua_type("./components/combat_replica.lua") == "replica")
    check("replica suffix in root", detect_lua_type("./container_replica.lua") == "replica")

    # Backslash normalization
    check("backslash normalized", detect_lua_type(".\\brains\\pigbrain.lua") == "brains")

    # Case insensitive directory
    check("uppercase dir", detect_lua_type("./Brains/pigbrain.lua") == "brains")


if __name__ == "__main__":
    print("\n=== type_detect tests ===")
    run_tests()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
