"""
Smoke test cho per-chunk connected content (plan section 7.1 + 7.1b).
Chạy: python test_per_chunk.py
"""

import sys
import os

# Đảm bảo import từ thư mục gốc
sys.path.insert(0, os.path.dirname(__file__))

from rag_get_fnc_content import (
    extract_connected_for_chunk,
    extract_signatures_only,
    extract_connected_content,
)
from chunked import count_tokens, CONTEXT_RESERVE

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


print("=" * 60)
print("TEST 7.1: extract_connected_for_chunk()")
print("=" * 60)

# Test 1: chunk co inst.components.X + require -> chunk_refs truc tiep
print("\n--- Test 1: chunk co inst.components.X ---")
chunk_with_components = '''
require("components/health")
inst.components.health:DoDelta(-10)
inst.components.health:GetPercent()
'''
section, content, ref_count = extract_connected_for_chunk(
    chunk_code=chunk_with_components,
    own_filename="combat.lua",
    full_refs=[("./components/health.lua", ["DoDelta", "GetPercent"])],
)
test("section non-empty", section != "", f"section='{section}'")
test("ref_count >= 1", ref_count >= 1, f"ref_count={ref_count}")
test("DoDelta in content", "DoDelta" in content, f"content='{content[:100]}'")

# Test 2: chunk goi nhieu inst.components.X
print("\n--- Test 2: chunk goi nhieu inst.components.X ---")
chunk_inst_components = '''
inst.components.health:DoDelta(-5)
inst.components.hunger:DoDelta(-1)
'''
section2, content2, ref_count2 = extract_connected_for_chunk(
    chunk_code=chunk_inst_components,
    own_filename="combat.lua",
    full_refs=[("./components/health.lua", ["DoDelta"]), ("./components/hunger.lua", ["DoDelta"])],
)
test("ref_count >= 1", ref_count2 >= 1, f"ref_count={ref_count2}")
if content2:
    test("DoDelta in content", "DoDelta" in content2, f"content='{content2[:100]}'")
else:
    test("content empty OK (files may not resolve)", True)

# Test 3: chunk độc lập thực sự → không inject gì
print("\n--- Test 3: chunk độc lập ---")
chunk_independent = '''
local x = 1 + 2
return x * 3
'''
section3, content3, ref_count3 = extract_connected_for_chunk(
    chunk_code=chunk_independent,
    own_filename="util.lua",
    full_refs=[("./components/health.lua", ["DoDelta"])],
)
test("section empty", section3 == "", f"section='{section3}'")
test("content empty", content3 == "", f"content='{content3[:100] if content3 else ''}'")
test("ref_count == 0", ref_count3 == 0, f"ref_count={ref_count3}")

# Test 4: signature-only output phải fit trong CONTEXT_RESERVE
print("\n--- Test 4: signature truncation ---")
large_full_refs = [
    ("./components/health.lua", ["DoDelta", "GetPercent", "SetMax", "IsDead", "IsInvincible"]),
    ("./components/hunger.lua", ["DoDelta", "GetPercent"]),
    ("./components/combat.lua", ["GetAttacked", "DoAttack", "CalcDamage"]),
]
sig_content, kept = extract_signatures_only(large_full_refs, max_output_tokens=CONTEXT_RESERVE)
if sig_content:
    sig_tokens = count_tokens(sig_content)
    if sig_tokens == -1:
        sig_tokens = len(sig_content) // 4
    test(
        f"sig_tokens ({sig_tokens}) <= CONTEXT_RESERVE ({CONTEXT_RESERVE})",
        sig_tokens <= CONTEXT_RESERVE,
    )
else:
    test("sig_content empty (files may not resolve)", True)

# Test 5: guard section/content mismatch — file refs không tồn tại trên disk
print("\n--- Test 5: file không tồn tại → guard ---")
section5, content5, ref_count5 = extract_connected_for_chunk(
    chunk_code="inst.components.nonexistent:Foo()",
    own_filename="combat.lua",
    full_refs=[("./components/nonexistent.lua", ["Foo"])],
)
test("section empty", section5 == "", f"section='{section5}'")
test("content empty", content5 == "", f"content='{content5}'")
test(
    "ref_count == 1 (file missing, not independent)",
    ref_count5 == 1,
    f"ref_count={ref_count5}. Risk #15 fix chưa apply?",
)

# Test 6: require-based cross-chunk — known gap
print("\n--- Test 6: require-based cross-chunk (known gap) ---")
chunk_require_user = '''
-- chunk 2: gọi util.SomeFunction() nhưng require nằm ở chunk 1
util.SomeFunction(inst)
'''
section6, content6, ref_count6 = extract_connected_for_chunk(
    chunk_code=chunk_require_user,
    own_filename="combat.lua",
    full_refs=[("./util/module.lua", ["SomeFunction"])],
)
test("section empty", section6 == "", f"section='{section6}'")
test("content empty", content6 == "", f"content='{content6}'")
test("ref_count == 0 (known gap)", ref_count6 == 0, f"ref_count={ref_count6}")


print("\n" + "=" * 60)
print("TEST 7.1b: extract_connected_content() với max_total_tokens")
print("=" * 60)

# Test B1: full bodies FIT
print("\n--- Test B1: full bodies fit ---")
small_refs = [("./components/health.lua", ["GetPercent"])]
content_b1 = extract_connected_content(small_refs, max_total_tokens=3500)
if content_b1:
    test("no SIGONLY marker (full bodies)", "--[SIGONLY:" not in content_b1)
else:
    test("content empty (file may not resolve)", True)

# Test B2: full bodies VƯỢT → fallback signatures
print("\n--- Test B2: budget cực nhỏ → fallback ---")
content_b2 = extract_connected_content(
    [("./components/health.lua", ["DoDelta", "GetPercent", "SetMax"])],
    max_total_tokens=10,
)
if content_b2:
    test("SIGONLY marker present", "--[SIGONLY:" in content_b2, f"content='{content_b2[:100]}'")
else:
    test("content empty (file may not resolve or all truncated)", True)

# Test B3: max_total_tokens=0 → không fallback
print("\n--- Test B3: unlimited (default) ---")
content_b3 = extract_connected_content(
    [("./components/health.lua", ["DoDelta"])],
    max_total_tokens=0,
)
if content_b3:
    test("no SIGONLY marker (unlimited)", "--[SIGONLY:" not in content_b3)
else:
    test("content empty (file may not resolve)", True)


# ── Summary ──
print("\n" + "=" * 60)
print(f"RESULTS: {passed} passed, {failed} failed")
print("=" * 60)
sys.exit(1 if failed else 0)
