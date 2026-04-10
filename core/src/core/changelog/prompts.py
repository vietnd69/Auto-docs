# core/src/core/changelog/prompts.py


def build_changelog_prompt(
    old_ver: str,
    new_ver: str,
    date: str,
    changes: list[dict],
) -> str:
    counts = {"added": 0, "modified": 0, "deleted": 0, "moved": 0}
    for c in changes:
        action = c.get("action", "")
        if action in counts:
            counts[action] += 1

    lines = []
    for c in changes:
        action = c.get("action", "")
        if action == "moved":
            old_p = c.get("old_path", "")
            new_p = c.get("new_path", "")
            summary = c.get("diff_summary", "(no content changes)")
            lines.append(f"[moved]     {old_p} → {new_p} ({summary})")
        elif action == "deleted":
            path = c.get("path", "")
            lines.append(f"[deleted]   {path} (removed)")
        else:
            path = c.get("path", "")
            summary = c.get("diff_summary", "")
            lines.append(f"[{action}]    {path} ({summary})")

    file_list = "\n".join(lines)

    return f"""You are a technical writer documenting changes in the Don't Starve Together game API.
Given the list of changed files between two game builds, write a concise changelog entry
in commit-message style.

BUILD: {old_ver} → {new_ver} | DATE: {date}

STATISTICS:
- Added: {counts['added']} files
- Modified: {counts['modified']} files
- Deleted: {counts['deleted']} files
- Moved: {counts['moved']} files

CHANGED FILES:
{file_list}

OUTPUT FORMAT:
## Build {new_ver}

<Subject: imperative sentence summarizing the overall theme of changes>

- <one bullet per meaningful change; group trivial renames or micro-fixes into a single bullet>

<Closing paragraph summarizing the overall impact — length proportional to the scope of changes>

RULES:
- Subject: imperative mood, no period
- Bullets: start with a verb, be specific about what changed and why it matters
- Do not list every file — focus on patterns and themes
- Do not speculate beyond what file names and diff stats suggest
"""
