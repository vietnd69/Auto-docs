# validator.py
import re
import frontmatter
import emoji
import subprocess
import json
import shutil
from pathlib import Path
from validator.constants import MDX_NODE_TIMEOUT

def validate_mdx_via_node(filepath: str) -> list[str]:
    # Kiểm tra node có sẵn không
    if not shutil.which("node"):
        return ["[mdx] Node.js không tìm thấy — hãy cài Node.js"]

    script = Path(__file__).parent / "validate_mdx.mjs"
    if not script.exists():
        return [f"[mdx] Không tìm thấy {script}"]

    result = subprocess.run(
        ["node", "--experimental-vm-modules", str(script), filepath],
        capture_output=True,
        text=True,
        timeout=MDX_NODE_TIMEOUT  # tránh treo
    )

    if result.returncode != 0 and not result.stdout:
        return [f"[mdx] Node error: {result.stderr.strip()}"]

    try:
        data = json.loads(result.stdout)
        return data.get("errors", [])
    except json.JSONDecodeError:
        return [f"[mdx] Unexpected output: {result.stdout[:200]}"]

REQUIRED_FIELDS = [
    'id', 'title', 'description', 'tags', 'sidebar_position',
    'last_updated', 'build_version', 'change_status',
    'category_type', 'source_hash', 'system_scope',
]

def check_frontmatter(text):
    errors = []

    # Must start and end with ---
    fm_match = re.match(r'^---\n([\s\S]*?)\n---\n', text)
    if not fm_match:
        errors.append("Missing or malformed frontmatter delimiters")
        return errors

    fm = fm_match.group(1)

    # Check all required fields exist inside frontmatter
    for field in REQUIRED_FIELDS:
        if not re.search(rf'^{field}:', fm, re.MULTILINE):
            errors.append(f"Missing required field: {field}")

    # description must not be placeholder
    if re.search(r'description:\s*(<.*?>|\[\]|automatically generated)', fm):
        errors.append("description is placeholder")

    # tags must not be empty []
    if re.search(r'tags:\s*\[\s*\]', fm):
        errors.append("tags is empty")

    # tags missing []
    if re.search(r'^tags:\s*[^\[\s\n].*$', fm, re.MULTILINE):
        errors.append("tags missing square brackets []")

    # last_updated must not be {today_date} literal (unfilled)
    if re.search(r'last_updated:\s*\{today_date\}', fm):
        errors.append("last_updated not filled")

    # system_scope must have a valid format: non-empty, lowercase tag (letters, digits, hyphens)
    if not re.search(r'system_scope:\s*[a-z][a-z0-9\-]*\s*$', fm, re.MULTILINE):
        errors.append("system_scope missing or invalid format")

    # No <> or [] placeholders left
    if re.search(r'<[^>]+>|\[\]', fm):
        errors.append("Unfilled placeholder found in frontmatter")

    # Check for extra '---' in the body
    body = text[fm_match.end():]
    if re.search(r'^---$', body, re.MULTILINE):
        errors.append("Extra '---' divider found in document body")

    # Detect orphaned YAML keys after closing --- (split frontmatter)
    post_fm = text[fm_match.end():]
    orphaned_lines = []
    for line in post_fm.splitlines():
        if line.strip() == '':
            continue
        if re.match(r'^[a-z_]+:', line):
            orphaned_lines.append(line.strip())
        else:
            break
    if orphaned_lines:
        errors.append(f"YAML keys outside frontmatter (split): {', '.join(orphaned_lines)}")

    return errors  # empty list = OK

def check_required_headings(text: str) -> list[str]:
    required_headings = [
        "## Overview",
        "## Usage example",
        "## Dependencies & tags",
        "## Properties",
        "## Main functions",
        "## Events & listeners"
    ]
    errors = []
    last_index = -1
    last_heading = None
    
    for heading in required_headings:
        match = re.search(rf'^{re.escape(heading)}\s*$', text, re.MULTILINE)
        if not match:
            errors.append(f"Missing required heading: {heading}")
        else:
            current_index = match.start()
            if last_heading and current_index < last_index:
                errors.append(f"Heading '{heading}' is out of order (must appear after '{last_heading}')")
            last_index = max(last_index, current_index)
            last_heading = heading
            
    return errors

def check_duplication(text: str) -> list[str]:
    errors = []
    
    # 1. Check for multiple H1 headers
    h1_headers = re.findall(r'^#\s+.+$', text, re.MULTILINE)
    if len(h1_headers) > 1:
        errors.append(f"Multiple H1 headers found ({len(h1_headers)}). Document might be duplicated.")
        
    # 2. Check for repeated frontmatter-like keys in the body
    # We look for keys like 'id:', 'title:', 'description:' at the start of a line in the body
    # (excluding the first frontmatter block)
    fm_match = re.match(r'^---\n([\s\S]*?)\n---\n', text)
    if fm_match:
        body = text[fm_match.end():]
        duplicated_keys = []
        for key in ['id', 'title', 'description', 'category_type']:
            if re.search(rf'^{key}:', body, re.MULTILINE):
                duplicated_keys.append(key)
        
        if duplicated_keys:
            errors.append(f"Frontmatter keys found in body (possible duplication): {', '.join(duplicated_keys)}")
            
    return errors

def validate_full(filepath: str) -> list[str]:
    errors = []
    raw = Path(filepath).read_text(encoding="utf-8")

    # Python checks
    found_emojis = emoji.emoji_list(raw)
    if found_emojis:
        details = ", ".join([f"'{e['emoji']}' at {e['match_start']}" for e in found_emojis])
        errors.append(f"[warning:emoji] Chứa emoji hoặc unicode symbol: {details}")

    # found = find_bare_operators(raw)
    # if found:
    #     errors.append(f"[mdx] Bare operators: {found}")

    try:
        post = frontmatter.loads(raw)
        # Frontmatter(**post.metadata)
    except Exception as e:
        errors.append(f"[frontmatter] {e}")

    # custom YAML checks
    yaml_errs = check_frontmatter(raw)
    for err in yaml_errs:
        errors.append(f"[yaml] {err}")
        
    # Required headings check
    heading_errs = check_required_headings(raw)
    for err in heading_errs:
        errors.append(f"[format] {err}")

    # Duplication check
    dup_errs = check_duplication(raw)
    for err in dup_errs:
        errors.append(f"[format] {err}")

    # Check for filler text at the end of the file
    if re.search(r'\(End of (documentation|example)\)', raw, re.IGNORECASE):
        errors.append("[format] Chứa text rác: (End of documentation) hoặc (End of example)")

    # Node.js MDX check
    mdx_errors = validate_mdx_via_node(filepath)
    errors.extend(mdx_errors)

    return errors if errors else ["OK"]
