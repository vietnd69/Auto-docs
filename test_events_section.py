"""
Tests for _ensure_events_section() in chunked_olm.py.
Run: python test_events_section.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from chunked_olm import _ensure_events_section

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


print("\n-- _ensure_events_section() --")

# Case 1: section already present -- document unchanged
doc_with_section = (
    "## Overview\nfoo\n\n"
    "## Events & listeners\n- **Listens to:** x\n"
)
result = _ensure_events_section(doc_with_section)
test("section present: document unchanged",
     result == doc_with_section,
     f"document was modified unexpectedly")

test("section present: no double-append",
     result.count("## Events & listeners") == 1,
     f"section appears {result.count('## Events & listeners')} times")

# Case 2: section absent -- fallback appended
doc_without = "## Overview\nfoo\n\n## Main functions\nbar\n"
result2 = _ensure_events_section(doc_without)
test("section absent: heading appended",
     "## Events & listeners" in result2,
     "heading not found in output")
test("section absent: fallback body appended",
     "This file is not event-driven." in result2,
     "fallback body not found in output")
test("section absent: appended at end (after original content)",
     result2.startswith(doc_without.rstrip()),
     f"start of result unexpected: {result2[:60]!r}")

# Case 3: empty string -- fallback appended
result3 = _ensure_events_section("")
test("empty input: heading appended",
     "## Events & listeners" in result3,
     "heading not found")
test("empty input: fallback body appended",
     "This file is not event-driven." in result3,
     "body not found")

# Case 4: heading present at very start of document
doc_at_start = "## Events & listeners\nsome content\n"
result4 = _ensure_events_section(doc_at_start)
test("section at start: document unchanged",
     result4 == doc_at_start,
     "document was modified")

# Case 5: heading present but with empty body -- still unchanged
doc_empty_body = "## Overview\nfoo\n\n## Events & listeners\n\n## Properties\n"
result5 = _ensure_events_section(doc_empty_body)
test("section with empty body: document unchanged",
     result5 == doc_empty_body,
     "document was modified")


print(f"\n{'='*40}")
print(f"Results: {passed} passed, {failed} failed")
if failed:
    sys.exit(1)
