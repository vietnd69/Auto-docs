import pytest
from validator.format.autofix import (
    FixResult,
    remove_pure_emojis,
    remove_extra_dividers,
    fix_frontmatter_delimiters,
    fix_split_frontmatter,
    fix_yaml_mapping_colon_in_description,
    fix_reference_errors,
    fix_bare_curly_braces,
    fix_table_pipes,
    remove_filler_text,
)
from validator.format.checks import ValidationError


def test_fix_result_dataclass():
    result = FixResult(changes=["fix1"], remaining_errors=[])
    assert result.changes == ["fix1"]
    assert result.remaining_errors == []


def test_fix_result_with_errors():
    err = ValidationError("mdx", "error", "test")
    result = FixResult(changes=[], remaining_errors=[err])
    assert len(result.remaining_errors) == 1


def test_emoji_removal():
    text = "Hello 🌍! This is a test ↔ with symbols."
    fixed, count = remove_pure_emojis(text)
    assert "🌍" not in fixed
    assert "↔" in fixed
    assert count == 1


def test_emoji_removal_no_emoji():
    text = "Hello world, no emojis."
    fixed, count = remove_pure_emojis(text)
    assert fixed == text
    assert count == 0


def test_divider_removal_trailing():
    text = "---\nid: test\n---\nContent\n\n---\n"
    fixed, count = remove_extra_dividers(text)
    assert count == 1
    assert fixed == "---\nid: test\n---\nContent\n"


def test_divider_removal_middle_kept():
    text = "---\nid: test\n---\nBefore\n\n---\n\nAfter\n"
    fixed, count = remove_extra_dividers(text)
    assert count == 0
    assert "\n\n---\n\n" in fixed


def test_divider_removal_multiple():
    text = "---\nid: test\n---\nContent\n---\n---\n"
    fixed, count = remove_extra_dividers(text)
    assert count == 2


def test_frontmatter_delimiters_missing_opening():
    text = "id: test\ntitle: Test\n---\n# Content\n"
    fixed, changed = fix_frontmatter_delimiters(text)
    assert changed is True
    assert fixed.startswith("---\n")


def test_frontmatter_delimiters_already_correct():
    text = "---\nid: test\n---\n# Content\n"
    fixed, changed = fix_frontmatter_delimiters(text)
    assert changed is False


def test_split_frontmatter_orphaned_keys():
    text = "---\nid: test\n---\nlast_updated: 2026-03-21\n\n# Content\n"
    fixed, changed = fix_split_frontmatter(text)
    assert changed is True
    assert "last_updated" not in fixed.split("---\n", 2)[-1].split("---")[0] or "last_updated" in fixed.split("---")[1]


def test_yaml_mapping_colon():
    text = "---\ndescription: test: colon\n---\n"
    fixed, changed = fix_yaml_mapping_colon_in_description(text)
    assert changed is True
    assert 'description: "test: colon"' in fixed


def test_yaml_mapping_colon_already_quoted():
    text = '---\ndescription: "test: colon"\n---\n'
    fixed, changed = fix_yaml_mapping_colon_in_description(text)
    assert changed is False


def test_filler_text_removal():
    text = "Content\n(End of documentation)\n"
    fixed, changed = remove_filler_text(text)
    assert changed is True
    assert "(End of documentation)" not in fixed


def test_fix_bare_curly_braces():
    text = "The type is {number, number} in the API.\n"
    fixed, count = fix_bare_curly_braces(text)
    assert count == 1
    assert "`{number, number}`" in fixed


def test_fix_bare_curly_braces_in_code_block():
    text = "```\n{number, number}\n```\n"
    fixed, count = fix_bare_curly_braces(text)
    assert count == 0


def test_fix_reference_errors():
    text = "| `bar` | {number, number} | `{0.7}` |\n"
    fixed, count = fix_reference_errors(text, "number")
    assert count >= 1
    assert "`{number, number}`" in fixed


def test_fix_reference_errors_preserves_backticked():
    text = "* **Parameters:** `data` (`{ resistance = number }`) -- Saved.\n"
    fixed, count = fix_reference_errors(text, "number")
    assert count == 0


def test_fix_table_pipes():
    text = "| col | `a|b` | col |\n"
    fixed, count = fix_table_pipes(text)
    assert count >= 1
    assert "\\|" in fixed


# --- Additional functions: import + basic behavior tests ---

def test_fix_empty_tags_and_placeholders():
    from validator.format.autofix import fix_empty_tags_and_placeholders
    text = "---\ntags: []\n---\n"
    fixed, applied = fix_empty_tags_and_placeholders(text)
    assert len(applied) > 0
    assert "tags: [stub]" in fixed


def test_fix_tags_format():
    from validator.format.autofix import fix_tags_format
    text = "---\ntags: tag1, tag2\n---\n"
    fixed, changed = fix_tags_format(text)
    assert changed is True
    assert "tags: [tag1, tag2]" in fixed


def test_fix_malformed_multiline_backticks():
    from validator.format.autofix import fix_malformed_multiline_backticks
    text = "  `{\n    `{abc=1}`,\n  }`\n"
    fixed, count = fix_malformed_multiline_backticks(text)
    assert count == 1
    assert "```lua" in fixed


def test_prune_duplicated_content():
    from validator.format.autofix import prune_duplicated_content
    text = "---\nid: x\n---\n# Title\nContent\n# Title\nContent\n"
    fixed, pruned = prune_duplicated_content(text)
    assert pruned is True


def test_fix_all_bare_operators():
    from validator.format.autofix import fix_all_bare_operators
    text = "The value x <= 5 is checked.\n"
    fixed = fix_all_bare_operators(text)
    assert "`" in fixed


def test_get_mdx_errors_exists():
    from validator.format.autofix import get_mdx_errors
    assert callable(get_mdx_errors)


def test_is_inside_backticks():
    from validator.format.autofix import is_inside_backticks
    assert is_inside_backticks("`hello`", 3) is True
    assert is_inside_backticks("hello", 3) is False


def test_fix_bare_operator_on_line():
    from validator.format.autofix import fix_bare_operator_on_line
    line = "value <= 5 in the range"
    fixed = fix_bare_operator_on_line(line, 6, "<=")
    assert "`" in fixed
