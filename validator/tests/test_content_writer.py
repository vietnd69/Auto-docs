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


def test_parse_writer_response_runaway_returns_empty():
    """Runaway response: repeated non-JSON lines → parse returns empty list."""
    line = "| onenter (frozen) |  |  |"
    raw = "\n".join([line] * 30 + [f"unique {i}" for i in range(25)])
    patches = parse_writer_response(raw)
    assert patches == []


def test_rewrite_document_valid_large_patch_array_not_killed_as_runaway():
    """Valid JSON with repeated 'reason' field must NOT trigger is_runaway.

    Regression test: when 49 patches share the same reason string, is_runaway
    would previously detect 49 repetitions of the same line and kill the response
    before JSON parsing even ran. After the fix, JSON parse runs first and
    the response is accepted as valid.
    """
    from unittest.mock import patch as mock_patch, MagicMock
    from validator.content.writer import rewrite_document
    from validator.content.reviewer import ReviewResult

    # Build a valid JSON patch array with 49 entries, all with the same reason.
    # This previously triggered is_runaway (49 × same "reason" line ≥ threshold of 8).
    shared_reason = "Remove incorrect error states; source code has nil guards or components are guaranteed to exist"
    patches_data = [
        {
            "old_text": f"* **Error states:** Errors if inst has no Component{i}",
            "new_text": "* **Error states:** None",
            "reason": shared_reason,
        }
        for i in range(49)
    ]
    raw_response = json.dumps(patches_data)

    review = ReviewResult(
        approved=False,
        issues=[f"WRONG_ERROR_STATE fn{i}" for i in range(49)],
        suggestions=["Remove incorrect error states"] * 49,
        raw_response="",
    )

    mock_response = {"message": {"content": raw_response}}

    with mock_patch("validator.content.writer.ollama_chat", return_value=mock_response):
        result_patches, result_raw, _ = rewrite_document(
            md_content="some content\n* **Error states:** Errors if inst has no Component0\n",
            lua_source="",
            connected_content="",
            review_feedback=review,
            model="test-model",
        )

    # Must return patches, not be killed as runaway
    assert len(result_patches) >= 1, (
        "Writer killed valid 49-patch response as runaway — is_runaway runs before JSON parse"
    )
