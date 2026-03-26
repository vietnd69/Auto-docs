"""Tests for JSON schemas used with Ollama format parameter."""

import json
import jsonschema
import pytest


def test_review_schema_importable():
    from validator.content.schemas import REVIEW_SCHEMA
    assert isinstance(REVIEW_SCHEMA, dict)
    assert REVIEW_SCHEMA["type"] == "object"


def test_patches_schema_importable():
    from validator.content.schemas import PATCHES_SCHEMA
    assert isinstance(PATCHES_SCHEMA, dict)
    assert PATCHES_SCHEMA["type"] == "array"


def test_review_schema_validates_approved():
    from validator.content.schemas import REVIEW_SCHEMA
    valid = {"approved": True, "findings": []}
    jsonschema.validate(valid, REVIEW_SCHEMA)


def test_review_schema_validates_findings():
    from validator.content.schemas import REVIEW_SCHEMA
    valid = {
        "approved": False,
        "findings": [
            {"issue": "Wrong param", "suggestion": "Fix it"},
        ],
    }
    jsonschema.validate(valid, REVIEW_SCHEMA)


def test_review_schema_rejects_missing_approved():
    from validator.content.schemas import REVIEW_SCHEMA
    invalid = {"findings": []}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid, REVIEW_SCHEMA)


def test_patches_schema_validates_patch_list():
    from validator.content.schemas import PATCHES_SCHEMA
    valid = [
        {"old_text": "foo", "new_text": "bar", "reason": "fix"},
    ]
    jsonschema.validate(valid, PATCHES_SCHEMA)


def test_patches_schema_validates_empty_list():
    from validator.content.schemas import PATCHES_SCHEMA
    jsonschema.validate([], PATCHES_SCHEMA)


def test_patches_schema_rejects_missing_old_text():
    from validator.content.schemas import PATCHES_SCHEMA
    invalid = [{"new_text": "bar", "reason": "fix"}]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid, PATCHES_SCHEMA)
