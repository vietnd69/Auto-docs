
import sys
from pathlib import Path

# Add parent to path to import validator modules
sys.path.append(str(Path(__file__).parent))

from autofix_mdx import remove_pure_emojis, remove_extra_dividers, fix_frontmatter_delimiters

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
    text = """---
id: test
---
---
Invalid divider (no blank line above)
# Heading
---
Valid divider (HR)

---
Invalid divider (no blank line below)
Text here
"""
    fixed, count = remove_extra_dividers(text)
    print(f"Fixed text:\n{fixed}")
    print(f"Count: {count}")
    
    # Valid HR should remain (it has blank lines before and after in the source, 
    # 1. --- immediately after FM closing (invalid)
    # 2. --- immediately after Text (invalid, missing blank line before)
    # 3. --- between two blank lines (valid HR)
    precise_text = "---\nid: test\n---\n---\nText\n---\n\n---\n\nMore Text\n"
    
    fixed, count = remove_extra_dividers(precise_text)
    print(f"Precise Fixed:\n{repr(fixed)}")
    print(f"Count: {count}")
    
    assert count == 2
    assert "Text\n---\n" not in fixed # The one after text should be gone
    assert "\n\n---\n\n" in fixed      # The valid HR should remain
    
    print("✅ Divider removal logic verified!")

def test_frontmatter_delimiters():
    print("\nTesting frontmatter delimiters...")
    # Edge case: missing trailing newline after closing ---
    text = "---\nid: test\n---"
    fixed, changed = fix_frontmatter_delimiters(text)
    assert changed == False # Should already match if we improved the regex or handled it
    
    # Test our new regex in fix_yaml_mapping_colon_in_description
    from autofix_mdx import fix_yaml_mapping_colon_in_description
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
