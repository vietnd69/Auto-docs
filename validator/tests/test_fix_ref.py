"""Quick test for fix_reference_errors function"""
import re

def fix_reference_errors(text, identifier):
    lines = text.splitlines(keepends=True)
    count = 0
    in_code_block = False
    brace_pattern = re.compile(
        r'(?<!`)\{([^{}`\n]*\b' + re.escape(identifier) + r'\b[^{}`\n]*)\}(?!`)'
    )
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('```'):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        parts = re.split(r'(`[^`\n]+`)', line)
        new_parts = []
        line_changed = False
        for j, part in enumerate(parts):
            if j % 2 == 1:
                new_parts.append(part)
                continue
            def wrap_fn(m):
                nonlocal count, line_changed
                count += 1
                line_changed = True
                return f'`{m.group(0)}`'
            new_parts.append(brace_pattern.sub(wrap_fn, part))
        if line_changed:
            lines[idx] = ''.join(new_parts)
    return ''.join(lines), count

# Test cases
tests = [
    ("healthbar.md", "number", 
     '| `bar_colour` | {number, number, number, number} | `{0.7, 0.1, 0, 1}` |'),
    ("canopylightrays.md", "x",
     '| `lightray_positions` | table of {x,z} pairs | `{}` |'),
    ("remoteteleporter.md", "Entity",
     '*   **Returns:** `{Entity}` - list of valid items.'),
    ("riftspawner.md", "number",
     '*   **Parameters:** `forced_pos` ({x=number, z=number}|nil)'),
    ("explosiveresist.md (should NOT change)", "number",
     '* **Parameters:** `data` (`{ resistance = number }`) -- Saved.'),
    ("code block (should NOT change)", "number",
     '```\n{number: 5}\n```'),
]

for name, ident, line in tests:
    result, count = fix_reference_errors(line + "\n", ident)
    print(f"[{name}] ident={ident}, fixes={count}")
    print(f"  IN:  {line}")
    print(f"  OUT: {result.strip()}")
    print()
