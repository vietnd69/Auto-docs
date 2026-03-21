import pytest
from validator.format.checks import (
    ValidationError,
    check_frontmatter,
    check_required_headings,
    check_duplication,
    check_emoji,
    check_filler_text,
)


def test_validation_error_dataclass():
    err = ValidationError(category="mdx", severity="error", message="test")
    assert err.category == "mdx"
    assert err.severity == "error"
    assert err.message == "test"
    assert err.line is None

    err_with_line = ValidationError(category="yaml", severity="warning", message="x", line=5)
    assert err_with_line.line == 5


# --- check_frontmatter ---

VALID_FRONTMATTER = """\
---
id: test
title: Test
description: A valid description
tags: [test]
sidebar_position: 1
last_updated: 2026-03-21
build_version: 714014
change_status: new
category_type: component
source_hash: abc12345
system_scope: client
---

# Test
"""


def test_check_frontmatter_valid():
    errors = check_frontmatter(VALID_FRONTMATTER)
    assert errors == []


def test_check_frontmatter_missing_field():
    text = VALID_FRONTMATTER.replace("system_scope: client\n", "")
    errors = check_frontmatter(text)
    assert len(errors) == 1
    assert errors[0].category == "yaml"
    assert "system_scope" in errors[0].message


def test_check_frontmatter_empty_tags():
    text = VALID_FRONTMATTER.replace("tags: [test]", "tags: []")
    errors = check_frontmatter(text)
    assert any("tags is empty" in e.message for e in errors)


def test_check_frontmatter_missing_delimiters():
    text = "id: test\ntitle: Test\n"
    errors = check_frontmatter(text)
    assert any("frontmatter delimiters" in e.message for e in errors)


def test_check_frontmatter_invalid_system_scope():
    text = VALID_FRONTMATTER.replace("system_scope: client", "system_scope: INVALID")
    errors = check_frontmatter(text)
    assert any("system_scope" in e.message for e in errors)


# --- check_required_headings ---

VALID_BODY = """\
---
id: test
title: Test
---

## Overview

content

## Usage example

content

## Dependencies & tags

content

## Properties

content

## Main functions

content

## Events & listeners

content
"""


def test_check_required_headings_valid():
    errors = check_required_headings(VALID_BODY)
    assert errors == []


def test_check_required_headings_missing():
    text = VALID_BODY.replace("## Properties\n", "")
    errors = check_required_headings(text)
    assert len(errors) == 1
    assert errors[0].category == "format"
    assert "Properties" in errors[0].message


def test_check_required_headings_out_of_order():
    text = VALID_BODY.replace("## Overview", "## PLACEHOLDER").replace(
        "## Events & listeners", "## Overview"
    ).replace("## PLACEHOLDER", "## Events & listeners")
    errors = check_required_headings(text)
    assert any("out of order" in e.message for e in errors)


# --- check_duplication ---

def test_check_duplication_multiple_h1():
    text = "---\nid: x\n---\n# Title\nContent\n# Title\n"
    errors = check_duplication(text)
    assert len(errors) >= 1
    assert any("H1" in e.message for e in errors)


def test_check_duplication_clean():
    text = "---\nid: x\n---\n# Title\nContent\n"
    errors = check_duplication(text)
    assert errors == []


def test_check_duplication_frontmatter_in_body():
    text = "---\nid: x\n---\n# Title\nid: duplicate\n"
    errors = check_duplication(text)
    assert any("body" in e.message.lower() for e in errors)


# --- check_emoji ---

def test_check_emoji_found():
    text = "Hello 🌍 world"
    errors = check_emoji(text)
    assert len(errors) == 1
    assert errors[0].severity == "warning"
    assert errors[0].category == "format"


def test_check_emoji_clean():
    text = "Hello world, no emojis here."
    errors = check_emoji(text)
    assert errors == []


# --- check_filler_text ---

def test_check_filler_text_found():
    text = "Content\n(End of documentation)\n"
    errors = check_filler_text(text)
    assert len(errors) == 1
    assert errors[0].category == "format"


def test_check_filler_text_example():
    text = "Content\n(End of example)\n"
    errors = check_filler_text(text)
    assert len(errors) == 1


def test_check_filler_text_clean():
    text = "Content\nMore content\n"
    errors = check_filler_text(text)
    assert errors == []
