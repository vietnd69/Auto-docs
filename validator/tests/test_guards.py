from validator.content.guards import (
    is_runaway,
    validate_review_schema,
    validate_patches_schema,
    validate_jury_schema,
    compact_bad_response,
)


# --- is_runaway ---

def test_is_runaway_short_response():
    assert is_runaway("small response") is False


def test_is_runaway_non_repetitive():
    raw = "\n".join(f"Line {i}: unique content here" for i in range(50))
    assert is_runaway(raw) is False


def test_is_runaway_detects_repeated_lines():
    line = "| onenter (frozen) |  |  |"
    # pad to exceed 3000 char threshold
    padding = "\n".join(f"unique content line number {i} with extra text to pad" for i in range(60))
    raw = padding + "\n" + "\n".join([line] * 20)
    assert is_runaway(raw) is True


def test_is_runaway_threshold():
    line = "| some repeated table row |  |  |"
    # pad to exceed 3000 char threshold
    padding = "\n".join(f"unique content line number {i} with extra text to pad size" for i in range(60))
    raw_7 = padding + "\n" + "\n".join([line] * 7)
    raw_8 = padding + "\n" + "\n".join([line] * 8)
    assert is_runaway(raw_7) is False
    assert is_runaway(raw_8) is True


def test_is_runaway_ignores_short_lines():
    raw = "\n".join(["ok"] * 50 + [f"unique {i}" for i in range(20)])
    assert is_runaway(raw) is False


# --- validate_review_schema ---

def test_validate_review_schema_valid():
    data = {"approved": True, "findings": []}
    assert validate_review_schema(data) is True


def test_validate_review_schema_with_findings():
    data = {"approved": False, "findings": [{"issue": "x", "suggestion": "y"}]}
    assert validate_review_schema(data) is True


def test_validate_review_schema_missing_approved():
    assert validate_review_schema({"findings": []}) is False


def test_validate_review_schema_wrong_approved_type():
    assert validate_review_schema({"approved": "true", "findings": []}) is False


def test_validate_review_schema_missing_findings():
    assert validate_review_schema({"approved": True}) is False


def test_validate_review_schema_finding_missing_field():
    data = {"approved": False, "findings": [{"issue": "x"}]}
    assert validate_review_schema(data) is False


# --- validate_patches_schema ---

def test_validate_patches_schema_valid():
    data = [{"old_text": "a", "new_text": "b", "reason": "r"}]
    assert validate_patches_schema(data) is True


def test_validate_patches_schema_empty_list():
    assert validate_patches_schema([]) is True


def test_validate_patches_schema_not_list():
    assert validate_patches_schema({"old_text": "a"}) is False


def test_validate_patches_schema_missing_field():
    data = [{"old_text": "a", "new_text": "b"}]
    assert validate_patches_schema(data) is False


# --- validate_jury_schema ---

def test_validate_jury_schema_yes():
    assert validate_jury_schema({"vote": "yes", "reason": "r"}) is True


def test_validate_jury_schema_no():
    assert validate_jury_schema({"vote": "no", "reason": "r"}) is True


def test_validate_jury_schema_invalid_vote():
    assert validate_jury_schema({"vote": "maybe", "reason": "r"}) is False


def test_validate_jury_schema_missing_reason():
    assert validate_jury_schema({"vote": "yes"}) is False


# --- compact_bad_response ---

def test_compact_short_response_unchanged():
    raw = "short"
    assert compact_bad_response(raw, max_chars=500) == raw


def test_compact_runaway_response():
    line = "| onenter (frozen) |  |  |"
    raw = "\n".join([line] * 30 + [f"unique {i}" for i in range(20)])
    result = compact_bad_response(raw, max_chars=500)
    assert "runaway" in result.lower()
    assert "30" in result


def test_compact_large_non_runaway():
    raw = " ".join(f"word{i}" for i in range(1000))
    result = compact_bad_response(raw, max_chars=100)
    assert len(result) < len(raw)
    assert "TRUNCATED" in result
