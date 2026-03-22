# validator/tests/test_sections.py
import pytest
from validator.content.sections import DocSection, split_md_sections, join_md_sections, extract_function_names


def test_split_no_frontmatter():
    """Text with no frontmatter and no ## headings → one preamble section."""
    content = "Some intro text.\n"
    fm, sections = split_md_sections(content)
    assert fm == ""
    assert len(sections) == 1
    assert sections[0].heading == ""
    assert sections[0].text == "Some intro text.\n"


def test_split_frontmatter_no_sections():
    """Frontmatter extracted; body with no ## becomes one preamble section."""
    content = "---\ntitle: Foo\n---\nsome body\n"
    fm, sections = split_md_sections(content)
    assert fm == "---\ntitle: Foo\n---\n"
    assert len(sections) == 1
    assert sections[0].heading == ""
    assert sections[0].text == "some body\n"


def test_split_one_section():
    """Single ## section captured with heading as first line."""
    content = "---\ntitle: Foo\n---\n## Functions\nbody text\n"
    fm, sections = split_md_sections(content)
    assert fm == "---\ntitle: Foo\n---\n"
    assert len(sections) == 1
    assert sections[0].heading == "## Functions"
    assert sections[0].text == "## Functions\nbody text\n"


def test_split_multiple_sections_with_preamble():
    """Preamble + two ## sections → three DocSection objects."""
    content = "---\ntitle: T\n---\npreamble\n## A\na text\n## B\nb text\n"
    fm, sections = split_md_sections(content)
    assert fm == "---\ntitle: T\n---\n"
    assert len(sections) == 3
    assert sections[0].heading == "" and sections[0].text == "preamble\n"
    assert sections[1].heading == "## A" and sections[1].text == "## A\na text\n"
    assert sections[2].heading == "## B" and sections[2].text == "## B\nb text\n"


def test_split_ignores_triple_hash():
    """### headings are NOT split points."""
    content = "## Functions\n### GetOwner\nbody\n### SetOwner\nbody2\n"
    _, sections = split_md_sections(content)
    assert len(sections) == 1
    assert "### GetOwner" in sections[0].text
    assert "### SetOwner" in sections[0].text


def test_split_empty_body_after_frontmatter():
    """Empty body after frontmatter → empty sections list."""
    content = "---\ntitle: T\n---\n"
    fm, sections = split_md_sections(content)
    assert fm == "---\ntitle: T\n---\n"
    assert sections == []


def test_split_crlf_normalized():
    """CRLF line endings normalised to LF; no \\r in output."""
    content = "---\r\ntitle: Foo\r\n---\r\n## Sec\r\nbody\r\n"
    fm, sections = split_md_sections(content)
    assert "\r" not in fm
    assert all("\r" not in s.text for s in sections)


def test_split_roundtrip():
    """join_md_sections(*split_md_sections(x)) == x (LF-normalised)."""
    content = "---\ntitle: T\n---\npreamble\n## A\na text\n### Sub\nmore\n## B\nb text\n"
    fm, sections = split_md_sections(content)
    assert join_md_sections(fm, sections) == content


def test_split_crlf_roundtrip():
    """CRLF input round-trips to LF-only output."""
    content = "---\r\ntitle: T\r\n---\r\n## A\r\ntext\r\n"
    fm, sections = split_md_sections(content)
    reassembled = join_md_sections(fm, sections)
    assert reassembled == content.replace("\r\n", "\n")


def test_join_md_sections():
    """join_md_sections concatenates frontmatter + all section texts."""
    sections = [
        DocSection("## A", "## A\ntext\n"),
        DocSection("## B", "## B\nmore\n"),
    ]
    result = join_md_sections("---\ntitle: T\n---\n", sections)
    assert result == "---\ntitle: T\n---\n## A\ntext\n## B\nmore\n"


def test_extract_fn_heading_pattern():
    """### FunctionName headings (with optional backtick) are captured."""
    text = "## Functions\n### GetOwner\nReturns owner.\n### `SetOwner`\nSets owner.\n"
    names = extract_function_names(text)
    assert "GetOwner" in names
    assert "SetOwner" in names


def test_extract_fn_backtick_paren():
    """`FuncName(` pattern captured."""
    text = "Call `GetOwner()` to get the owner.\n"
    assert "GetOwner" in extract_function_names(text)


def test_extract_fn_method_call():
    """`inst:Method(` captures Method (not inst)."""
    text = "Use `inst:GetOwner()` or `self:SetOwner()`.\n"
    names = extract_function_names(text)
    assert "GetOwner" in names
    assert "SetOwner" in names


def test_extract_fn_capitalized_standalone_backtick():
    """`CapitalizedName` (no parens, capital first letter) is captured."""
    text = "The `GetOwner` function returns the owner.\n"
    assert "GetOwner" in extract_function_names(text)


def test_extract_fn_lowercase_standalone_not_captured():
    """`lowercase` standalone backtick NOT captured (false-positive filter)."""
    text = "The `owner` variable holds the owner.\n"
    assert "owner" not in extract_function_names(text)


def test_extract_fn_deduplication():
    """Same name via multiple patterns appears only once."""
    text = "`GetOwner()` mentioned again as `GetOwner`.\n"
    names = extract_function_names(text)
    assert names.count("GetOwner") == 1


def test_extract_fn_offset_ordering():
    """Names ordered by first occurrence position in text."""
    text = "`Alpha()` then `Beta()`.\n"
    assert extract_function_names(text) == ["Alpha", "Beta"]


def test_extract_fn_empty_text():
    """Empty section returns empty list."""
    assert extract_function_names("") == []
