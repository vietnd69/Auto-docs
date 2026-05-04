import pytest
import json
from validator.content.writer import Patch, apply_patches, parse_writer_response


def test_patch_dataclass():
    p = Patch(old_text="foo", new_text="bar", reason="test")
    assert p.old_text == "foo"
    assert p.new_text == "bar"
    assert p.reason == "test"


def test_apply_patches_success():
    content = "Hello world. Goodbye world."
    patches = [
        Patch(old_text="Hello", new_text="Hi", reason="greeting"),
        Patch(old_text="Goodbye", new_text="Bye", reason="farewell"),
    ]
    result, failed, ambiguous, guard_blocked = apply_patches(content, patches)
    assert result == "Hi world. Bye world."
    assert failed == 0
    assert ambiguous == []
    assert guard_blocked == []


def test_apply_patches_partial_failure():
    content = "Hello world."
    patches = [
        Patch(old_text="Hello", new_text="Hi", reason="ok"),
        Patch(old_text="NONEXISTENT", new_text="X", reason="fail"),
    ]
    result, failed, ambiguous, guard_blocked = apply_patches(content, patches)
    assert result == "Hi world."
    assert failed == 1
    assert ambiguous == []
    assert guard_blocked == []


def test_apply_patches_empty():
    content = "Hello"
    result, failed, ambiguous, guard_blocked = apply_patches(content, [])
    assert result == "Hello"
    assert failed == 0
    assert ambiguous == []
    assert guard_blocked == []


def test_apply_patches_ambiguous_skipped():
    # When old_text appears multiple times, patch is skipped and returned as ambiguous
    content = "foo foo foo"
    p = Patch(old_text="foo", new_text="bar", reason="test")
    result, failed, ambiguous, guard_blocked = apply_patches(content, [p])
    assert result == "foo foo foo"  # unchanged
    assert failed == 1
    assert ambiguous == [p]
    assert guard_blocked == []


def test_apply_patches_guard_blocked_tracked():
    """Guard-blocked patches are returned as 4th element with lost fn names."""
    content = "### `foo`\nfoo content\n\n### `bar`\nbar content\n"
    # A patch that spans both ### blocks and drops one function
    p = Patch(
        old_text="### `foo`\nfoo content\n\n### `bar`\nbar content\n",
        new_text="### `foo`\nfoo content\n",
        reason="drops bar",
    )
    result, failed, ambiguous, guard_blocked = apply_patches(content, [p])
    assert result == content  # unchanged
    assert failed == 1
    assert len(guard_blocked) == 1
    blocked_patch, lost_fns = guard_blocked[0]
    assert blocked_patch is p
    assert "bar" in lost_fns


def test_parse_writer_response_valid():
    raw = json.dumps([
        {"old_text": "foo", "new_text": "bar", "reason": "test"},
    ])
    patches = parse_writer_response(raw)
    assert len(patches) == 1
    assert patches[0].old_text == "foo"


def test_parse_writer_response_multiple():
    raw = json.dumps([
        {"old_text": "a", "new_text": "b", "reason": "1"},
        {"old_text": "c", "new_text": "d", "reason": "2"},
    ])
    patches = parse_writer_response(raw)
    assert len(patches) == 2


def test_parse_writer_response_with_fence():
    raw = '```json\n[{"old_text": "a", "new_text": "b", "reason": "c"}]\n```'
    patches = parse_writer_response(raw)
    assert len(patches) == 1


def test_parse_writer_response_with_think():
    raw = '<think>thinking</think>\n[{"old_text": "a", "new_text": "b", "reason": "c"}]'
    patches = parse_writer_response(raw)
    assert len(patches) == 1


def test_parse_writer_response_invalid():
    raw = "Not valid JSON"
    patches = parse_writer_response(raw)
    assert patches == []


def test_parse_writer_response_empty_old_text_skipped():
    raw = json.dumps([
        {"old_text": "", "new_text": "bar", "reason": "empty"},
        {"old_text": "valid", "new_text": "ok", "reason": "good"},
    ])
    patches = parse_writer_response(raw)
    assert len(patches) == 1
    assert patches[0].old_text == "valid"


def test_parse_writer_json_valid():
    from validator.content.writer import parse_writer_json
    data = [
        {"old_text": "foo", "new_text": "bar", "reason": "fix"},
    ]
    patches = parse_writer_json(data)
    assert len(patches) == 1
    assert patches[0].old_text == "foo"


def test_parse_writer_json_empty():
    from validator.content.writer import parse_writer_json
    patches = parse_writer_json([])
    assert patches == []


def test_parse_writer_json_skips_empty_old_text():
    from validator.content.writer import parse_writer_json
    data = [
        {"old_text": "", "new_text": "bar", "reason": "empty"},
        {"old_text": "valid", "new_text": "ok", "reason": "good"},
    ]
    patches = parse_writer_json(data)
    assert len(patches) == 1
    assert patches[0].old_text == "valid"
