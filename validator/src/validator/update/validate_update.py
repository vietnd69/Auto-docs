import os
import re
import json
import frontmatter
from pathlib import Path
from datetime import datetime
from validator.format.checks import validate_all

def validate_update(filepath: str, action: str, meta: dict) -> list[str]:
    """
    Tầng A: Chạy validate_all() + các check đặc thù theo action.
    """
    # FIX 1: Check existence BEFORE validate_all
    if not os.path.exists(filepath):
        return [f"[critical] File not found: {filepath}"]

    validation_errors = validate_all(filepath)
    # Convert to strings for compatibility with existing action-specific checks
    errors = [f"[{e.category}] {e.message}" for e in validation_errors]

    raw = Path(filepath).read_text(encoding="utf-8")
    try:
        post = frontmatter.loads(raw)
        fm = post.metadata
    except Exception as e:
        errors.append(f"[frontmatter] Parse error for action check: {e}")
        return errors

    new_ver = meta.get("build_version")
    source_hash = meta.get("source_hash")

    # Common Frontmatter Checks
    if action == "added":
        if fm.get("change_status") != "new":
            errors.append(f"[yaml] change_status should be 'new', got '{fm.get('change_status')}'")
    elif action == "modified":
        if fm.get("change_status") != "updated":
            errors.append(f"[yaml] change_status should be 'updated', got '{fm.get('change_status')}'")
    elif action in ["deleted", "deprecated"]:
        if fm.get("change_status") != "deprecated":
            errors.append(f"[yaml] change_status should be 'deprecated', got '{fm.get('change_status')}'")
    elif action == "moved":
        if fm.get("change_status") != "moved":
            errors.append(f"[yaml] change_status should be 'moved', got '{fm.get('change_status')}'")

    # FIX 2: Unify source_hash check message and handle it consistently
    if action != "deleted":
        if str(fm.get("build_version")) != str(new_ver):
            errors.append(f"[yaml] build_version should be '{new_ver}', got '{fm.get('build_version')}'")

    # Check source_hash for all actions (deleted requires matching old hash)
    if str(fm.get("source_hash")) != str(source_hash):
        if action == "deleted":
            errors.append(f"[yaml] source_hash mismatch. Expected '{source_hash}' (old hash), got '{fm.get('source_hash')}'")
        else:
            errors.append(f"[yaml] source_hash mismatch. Expected '{source_hash}', got '{fm.get('source_hash')}'")

    # Action-specific body/content checks
    body = post.content

    if action == "added":
        if re.search(r'\*\(Changed in build .*?\)\*|~~.*?~~', body):
            errors.append("[warning:inline] New doc should not contain inline change notes or strikethrough")

    elif action == "modified":
        if not re.search(rf'\*\(Changed in build {re.escape(str(new_ver))}\)\*', body):
            errors.append(f"[warning:inline] No change notes found for current version {new_ver}")

        if "## Changelog" in body:
            errors.append("[format] Should not contain '## Changelog' section")

    elif action == "deleted":
        if not re.search(r'## Overview\s*\n\n> \[!WARNING\]', body):
            errors.append("[format] Missing [!WARNING] deprecation notice after ## Overview")
        if not re.search(rf'Deprecated in build {re.escape(str(new_ver))}', body):
            errors.append(f"[format] Deprecation notice should mention build {new_ver}")

    elif action == "moved":
        content_changed = meta.get("content_changed", True)
        if content_changed:
            if not re.search(r'\*\(Changed in build .*?\)\*', body):
                errors.append("[warning:inline] Moved file with content changes missing inline notes")
            if "## Changelog" in body:
                errors.append("[format] Should not contain '## Changelog' section")
        else:
            if str(fm.get("moved_from")) != str(meta.get("old_path")):
                errors.append(f"[yaml] moved_from mismatch. Expected '{meta.get('old_path')}', got '{fm.get('moved_from')}'")
            if str(fm.get("moved_in")) != str(new_ver):
                errors.append(f"[yaml] moved_in mismatch. Expected '{new_ver}', got '{fm.get('moved_in')}'")
            if not re.search(r'> \[!NOTE\]\s*\n> \*\*Moved in build', body):
                errors.append("[format] Missing relocation [!NOTE] after title")
            if re.search(r'\*\(Changed in build .*?\)\*', body):
                errors.append("[warning:inline] Moved file with NO content change should NOT have inline change notes")

    return errors  # empty list = no errors (replaces old ["OK"] contract)

def append_to_validation_log(filepath: str, action: str, errors: list[str]):
    """
    Ghi log lỗi validation để fix sau.
    """
    log_file = Path(__file__).parent / "validation_update_errors.log"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    hard_errors = [e for e in errors if not e.startswith("[warning")]
    warnings = [e for e in errors if e.startswith("[warning")]

    if not hard_errors and not warnings:
        return

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {action.upper()} | {filepath}\n")
        for e in hard_errors:
            f.write(f"  {e}\n")
        for w in warnings:
            f.write(f"  {w}\n")
        f.write("\n")

def validate_batch(diff_report_path: str, docs_dir: str) -> list[str]:
    """
    Tầng B: Kiểm tra tổng thể sau toàn bộ batch.
    """
    batch_errors = []
    if not os.path.exists(diff_report_path):
        batch_errors.append(f"[batch] Diff report not found: {diff_report_path}")
        return batch_errors

    with open(diff_report_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    new_ver = report["version"]["new"]
    changes = report["changes"]

    docs_path = Path(docs_dir)

    # 1. Check if all changed files exist in docs (except truly deleted which we keep as deprecated)
    for c in changes:
        action = c["action"]
        # FIX 4: Safe path handling
        path = c.get("path") or c.get("new_path") or c.get("old_path")
        if not path:
            batch_errors.append(f"[batch] Change entry missing all path fields for action {action}")
            continue

        md_rel_path = path.replace(".lua", ".md")
        md_full_path = docs_path / md_rel_path

        if action == "deleted":
            if not md_full_path.exists():
                batch_errors.append(f"[batch] Deleted file {md_rel_path} was removed from docs but should be kept as deprecated")
        elif action == "moved":
            old_path = c.get("old_path")
            if old_path:
                old_md_rel = old_path.replace(".lua", ".md")
                old_md_full = docs_path / old_md_rel
                if old_md_full.exists() and old_path != path:
                    batch_errors.append(f"[batch] Old path {old_md_rel} still exists after move to {md_rel_path}")

            if not md_full_path.exists():
                batch_errors.append(f"[batch] Moved file {md_rel_path} does not exist in docs")
        else:
            if not md_full_path.exists():
                batch_errors.append(f"[batch] File {md_rel_path} ({action}) missing from docs")

    # 2. Check for orphan docs with new status but old version
    # (Simplified: check all files in docs_dir)
    for md_file in docs_path.rglob("*.md"):
        try:
            raw = md_file.read_text(encoding="utf-8")
            post = frontmatter.loads(raw)
            fm = post.metadata

            # FIX 3: Implement orphan doc check as warning
            if fm.get("change_status") == "new" and str(fm.get("build_version")) != str(new_ver):
                 batch_errors.append(f"[warning:batch] Orphan 'new' doc found: {md_file.relative_to(docs_path)} (build_version: {fm.get('build_version')}, expected: {new_ver})")
        except Exception:
            continue

    if batch_errors:
        append_to_validation_log("BATCH_CHECK", "BATCH", batch_errors)

    return batch_errors
