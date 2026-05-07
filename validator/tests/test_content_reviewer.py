import pytest
import json
from validator.content.reviewer import ReviewResult, parse_review_response


def test_review_result_approved():
    result = ReviewResult(approved=True, issues=[], suggestions=[])
    assert result.approved is True
    assert result.issues == []


def test_review_result_rejected():
    result = ReviewResult(
        approved=False,
        issues=["Wrong param name"],
        suggestions=["Change 'foo' to 'bar'"],
    )
    assert result.approved is False
    assert len(result.issues) == 1


def test_parse_review_response_valid_json():
    raw = json.dumps({
        "approved": False,
        "issues": ["issue1"],
        "suggestions": ["fix1"],
    })
    result = parse_review_response(raw)
    assert result.approved is False
    assert result.issues == ["issue1"]
    assert result.suggestions == ["fix1"]


def test_parse_review_response_approved():
    raw = json.dumps({"approved": True, "issues": [], "suggestions": []})
    result = parse_review_response(raw)
    assert result.approved is True


def test_parse_review_response_with_markdown_fence():
    raw = '```json\n{"approved": true, "issues": [], "suggestions": []}\n```'
    result = parse_review_response(raw)
    assert result.approved is True


def test_parse_review_response_with_think_block():
    raw = '<think>reasoning here</think>\n{"approved": false, "issues": ["x"], "suggestions": ["y"]}'
    result = parse_review_response(raw)
    assert result.approved is False
    assert result.issues == ["x"]


def test_parse_review_response_invalid_json():
    raw = "This is not JSON at all"
    result = parse_review_response(raw)
    assert result.approved is False
    assert len(result.issues) >= 1  # Should contain parse error info


def test_parse_review_json_approved():
    from validator.content.reviewer import parse_review_json
    data = {"approved": True, "findings": []}
    result = parse_review_json(data)
    assert result.approved is True
    assert result.issues == []


def test_parse_review_json_with_findings():
    from validator.content.reviewer import parse_review_json
    data = {
        "approved": False,
        "findings": [
            {"issue": "Wrong param", "suggestion": "Fix it"},
            {"issue": "Missing return", "suggestion": "Add return docs"},
        ],
    }
    result = parse_review_json(data)
    assert result.approved is False
    assert len(result.issues) == 2
    assert result.issues[0] == "Wrong param"
    assert result.suggestions[1] == "Add return docs"


def test_parse_review_json_empty_findings():
    from validator.content.reviewer import parse_review_json
    data = {"approved": False, "findings": []}
    result = parse_review_json(data)
    assert result.approved is False
    assert result.issues == []


def test_parse_review_json_valid():
    from validator.content.reviewer import parse_review_json
    data = {"approved": False, "findings": [{"issue": "x", "suggestion": "y"}]}
    result = parse_review_json(data)
    assert result.approved is False
    assert result.issues == ["x"]
    assert result.suggestions == ["y"]


def test_raw_response_not_set_on_bad_parse():
    """raw_response must be empty string on unparseable responses."""
    result = parse_review_response("not json at all")
    assert result.raw_response == ""


def test_raw_response_not_set_on_empty():
    result = parse_review_response("")
    assert result.raw_response == ""
