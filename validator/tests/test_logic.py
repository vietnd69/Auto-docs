
import sys

from validator.autofix_mdx import remove_pure_emojis, remove_extra_dividers, fix_frontmatter_delimiters

def test_emoji_removal():
    print("Testing emoji removal...")
    text = "Hello 🌍! This is a test ↔ with symbols."
    fixed, count = remove_pure_emojis(text)
    print(f"Original: {text}")
    print(f"Fixed:    {fixed}")
    print(f"Count:    {count}")
    assert "🌍" not in fixed
    assert "↔" in fixed
    assert count == 1
    print("✅ Emoji removal test passed!")

def test_divider_removal():
    print("\nTesting divider removal...")

    # 1. Trailing --- at end of body -> removed
    text_trailing = "---\nid: test\n---\nContent\n\n---\n"
    fixed, count = remove_extra_dividers(text_trailing)
    assert count == 1
    assert fixed == "---\nid: test\n---\nContent\n"
    print("  trailing --- removed ✓")

    # 2. --- in middle of body (valid HR) -> kept
    text_middle = "---\nid: test\n---\nBefore\n\n---\n\nAfter\n"
    fixed, count = remove_extra_dividers(text_middle)
    assert count == 0
    assert "\n\n---\n\n" in fixed
    print("  middle HR kept ✓")

    # 3. Multiple trailing --- -> all removed
    text_multi = "---\nid: test\n---\nContent\n---\n---\n"
    fixed, count = remove_extra_dividers(text_multi)
    assert count == 2
    assert fixed == "---\nid: test\n---\nContent\n"
    print("  multiple trailing --- removed ✓")

    # 4. No trailing --- -> unchanged
    text_none = "---\nid: test\n---\n---\nText\n---\n\n---\n\nMore Text\n"
    fixed, count = remove_extra_dividers(text_none)
    assert count == 0
    assert fixed == text_none
    print("  no trailing --- unchanged ✓")

    print("✅ Divider removal logic verified!")

def test_frontmatter_delimiters():
    print("\nTesting frontmatter delimiters...")
    # Edge case: missing trailing newline after closing ---
    text = "---\nid: test\n---"
    fixed, changed = fix_frontmatter_delimiters(text)
    assert changed == False # Should already match if we improved the regex or handled it
    
    # Test our new regex in fix_yaml_mapping_colon_in_description
    from validator.autofix_mdx import fix_yaml_mapping_colon_in_description
    text_no_newline = "---\ndescription: test: colon\n---"
    fixed, changed = fix_yaml_mapping_colon_in_description(text_no_newline)
    assert changed == True
    assert 'description: "test: colon"' in fixed
    print("✅ Frontmatter edge cases passed!")

if __name__ == "__main__":
    try:
        test_emoji_removal()
        test_divider_removal()
        test_frontmatter_delimiters()
        print("\nAll targeted logic tests passed!")
    except AssertionError as e:
        print(f"\n❌ Test failed!")
        sys.exit(1)
