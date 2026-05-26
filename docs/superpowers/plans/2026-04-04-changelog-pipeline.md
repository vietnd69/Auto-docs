# Changelog Pipeline Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone pipeline (`python -m core.changelog`) that reads `data/diff_report.json` and prepends a high-level LLM-written summary to `dst-api-webdocs/change-log.md`.

**Architecture:** Three-module package under `core/src/core/changelog/` — `prompts.py` builds the prompt string, `pipeline.py` contains all logic (load → generate → prepend), and `__main__.py` wires the CLI entry point. Tests mock the LLM and filesystem where needed.

**Tech Stack:** Python 3.11, pytest, `unittest.mock`, `llm.client.ollama_chat` (Ollama Cloud), `llm.settings.MODEL_UPDATE`

---

## Chunk 1: Prompt builder + module scaffold

### Task 1: Scaffold the changelog package

**Files:**
- Create: `core/src/core/changelog/__init__.py`
- Create: `core/src/core/changelog/prompts.py`
- Create: `core/tests/test_changelog_pipeline.py`

- [ ] **Step 1: Create empty package init**

```python
# core/src/core/changelog/__init__.py
```

- [ ] **Step 2: Create prompts.py stub**

```python
# core/src/core/changelog/prompts.py


def build_changelog_prompt(
    old_ver: str,
    new_ver: str,
    date: str,
    changes: list[dict],
) -> str:
    raise NotImplementedError
```

- [ ] **Step 3: Write failing tests for `build_changelog_prompt()`**

```python
# core/tests/test_changelog_pipeline.py
"""Unit tests for core.changelog.pipeline and core.changelog.prompts."""
import pytest


SAMPLE_REPORT = {
    "version": {"old": "714014", "new": "718694"},
    "date": "2026-03-23",
    "changes": [
        {"action": "added", "path": "prefabs/w_radio.lua", "diff_summary": "+102 lines"},
        {"action": "added", "path": "stategraphs/SGcritter_bulbin.lua", "diff_summary": "new file"},
        {"action": "modified", "path": "brains/crittersbrain.lua", "diff_summary": "+2 lines, -0 lines"},
        {"action": "deleted", "path": "old/deprecated.lua"},
        {
            "action": "moved",
            "old_path": "old/path.lua",
            "new_path": "new/path.lua",
            "diff_summary": "+3 lines, -1 lines",
        },
        {
            "action": "moved",
            "old_path": "a.lua",
            "new_path": "b.lua",
            # no diff_summary — content_changed: False
        },
    ],
}


class TestBuildChangelogPrompt:
    def _call(self, report=None):
        from core.changelog.prompts import build_changelog_prompt
        r = report or SAMPLE_REPORT
        return build_changelog_prompt(
            old_ver=r["version"]["old"],
            new_ver=r["version"]["new"],
            date=r["date"],
            changes=r["changes"],
        )

    def test_contains_version_header(self):
        prompt = self._call()
        assert "714014 → 718694" in prompt

    def test_contains_date(self):
        prompt = self._call()
        assert "2026-03-23" in prompt

    def test_statistics_present(self):
        prompt = self._call()
        assert "Added: 2" in prompt
        assert "Modified: 1" in prompt
        assert "Deleted: 1" in prompt
        assert "Moved: 2" in prompt

    def test_added_file_rendered(self):
        prompt = self._call()
        assert "[added]" in prompt
        assert "prefabs/w_radio.lua" in prompt
        assert "+102 lines" in prompt

    def test_deleted_file_rendered(self):
        prompt = self._call()
        assert "[deleted]" in prompt
        assert "old/deprecated.lua" in prompt
        assert "(removed)" in prompt

    def test_moved_with_diff_rendered(self):
        prompt = self._call()
        assert "old/path.lua → new/path.lua" in prompt
        assert "+3 lines, -1 lines" in prompt

    def test_moved_no_diff_uses_fallback(self):
        prompt = self._call()
        assert "(no content changes)" in prompt

    def test_unified_diff_excluded(self):
        """unified_diff key must never appear in prompt."""
        report = {
            "version": {"old": "1", "new": "2"},
            "date": "2026-01-01",
            "changes": [
                {
                    "action": "modified",
                    "path": "foo.lua",
                    "diff_summary": "+1 lines",
                    "unified_diff": "--- a/foo.lua\n+++ b/foo.lua\n@@ secret @@",
                }
            ],
        }
        prompt = self._call(report)
        assert "secret" not in prompt
        assert "unified_diff" not in prompt

    def test_output_format_instruction_present(self):
        prompt = self._call()
        assert "## Build 718694" in prompt
```

- [ ] **Step 4: Run tests — verify they fail**

```
.venv/Scripts/pytest core/tests/test_changelog_pipeline.py::TestBuildChangelogPrompt -v
```

Expected: `NotImplementedError` on all tests.

- [ ] **Step 5: Implement `build_changelog_prompt()`**

```python
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
Given the list of changed files between two game builds, write a concise, high-level
changelog entry in Markdown.

BUILD: {old_ver} → {new_ver} | DATE: {date}

STATISTICS:
- Added: {counts['added']} files
- Modified: {counts['modified']} files
- Deleted: {counts['deleted']} files
- Moved: {counts['moved']} files

CHANGED FILES:
{file_list}

OUTPUT FORMAT: Markdown section starting with ## Build {new_ver}
- Write a 3-5 sentence "Highlights" paragraph identifying the most significant changes
- List files grouped by action (Added / Modified / Deleted / Moved)
- Be concise. Do not speculate beyond what file names and diff stats suggest.
"""
```

- [ ] **Step 6: Run tests — verify they pass**

```
.venv/Scripts/pytest core/tests/test_changelog_pipeline.py::TestBuildChangelogPrompt -v
```

Expected: all 9 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add core/src/core/changelog/__init__.py core/src/core/changelog/prompts.py core/tests/test_changelog_pipeline.py
git commit -m "feat(changelog): scaffold package and implement build_changelog_prompt"
```

---

## Chunk 2: `load_diff_report()` and `prepend_to_changelog()`

### Task 2: Implement `load_diff_report()`

**Files:**
- Create: `core/src/core/changelog/pipeline.py`
- Modify: `core/tests/test_changelog_pipeline.py`

- [ ] **Step 1: Create pipeline.py with `load_diff_report()` stub**

```python
# core/src/core/changelog/pipeline.py
"""
Changelog generation pipeline.

Usage:
    .venv/Scripts/python -m core.changelog
    .venv/Scripts/python -m core.changelog --dry-run
"""
import json
import signal
import sys
from pathlib import Path

from llm.paths import DATA_DIR, PROJECT_ROOT


def load_diff_report() -> dict | None:
    raise NotImplementedError


def build_changelog_entry(report: dict) -> str | None:
    raise NotImplementedError


def prepend_to_changelog(entry: str, changelog_path: Path) -> None:
    raise NotImplementedError


def main() -> None:
    raise NotImplementedError
```

- [ ] **Step 2: Write failing tests for `load_diff_report()`**

Add to `core/tests/test_changelog_pipeline.py`:

```python
class TestLoadDiffReport:
    def test_returns_dict_when_file_exists(self, tmp_path):
        report_path = tmp_path / "diff_report.json"
        report_path.write_text(json.dumps(SAMPLE_REPORT), encoding="utf-8")
        with patch("core.changelog.pipeline.DATA_DIR", str(tmp_path)):
            from core.changelog.pipeline import load_diff_report
            result = load_diff_report()
        assert result == SAMPLE_REPORT

    def test_returns_none_when_file_missing(self, tmp_path, capsys):
        with patch("core.changelog.pipeline.DATA_DIR", str(tmp_path)):
            from core.changelog.pipeline import load_diff_report
            result = load_diff_report()
        assert result is None
        assert "diff_report.json" in capsys.readouterr().out
```

Add `import json` and `from unittest.mock import patch, MagicMock` at the top of the test file.

- [ ] **Step 3: Run tests — verify they fail**

```
.venv/Scripts/pytest core/tests/test_changelog_pipeline.py::TestLoadDiffReport -v
```

Expected: `NotImplementedError`.

- [ ] **Step 4: Implement `load_diff_report()`**

Replace the stub in `pipeline.py`:

```python
def load_diff_report() -> dict | None:
    path = Path(DATA_DIR) / "diff_report.json"
    if not path.exists():
        print(f"[Error] {path} not found. Run the watcher first.")
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)
```

- [ ] **Step 5: Run tests — verify they pass**

```
.venv/Scripts/pytest core/tests/test_changelog_pipeline.py::TestLoadDiffReport -v
```

Expected: 2 tests PASS.

### Task 3: Implement `prepend_to_changelog()`

- [ ] **Step 6: Write failing tests for `prepend_to_changelog()`**

Add to `core/tests/test_changelog_pipeline.py`:

```python
class TestPrependToChangelog:
    def test_creates_file_if_not_exists(self, tmp_path):
        from core.changelog.pipeline import prepend_to_changelog
        path = tmp_path / "change-log.md"
        prepend_to_changelog("## Build 2\n\nContent.", path)
        text = path.read_text(encoding="utf-8")
        assert "# DST API Changelog" in text
        assert "## Build 2" in text

    def test_prepends_before_existing_content(self, tmp_path):
        from core.changelog.pipeline import prepend_to_changelog
        path = tmp_path / "change-log.md"
        path.write_text("# DST API Changelog\n\n## Build 1\n\nOld.", encoding="utf-8")
        prepend_to_changelog("## Build 2\n\nNew.", path)
        text = path.read_text(encoding="utf-8")
        assert text.index("## Build 2") < text.index("## Build 1")

    def test_header_written_only_once(self, tmp_path):
        from core.changelog.pipeline import prepend_to_changelog
        path = tmp_path / "change-log.md"
        prepend_to_changelog("## Build 2\n\nContent.", path)
        prepend_to_changelog("## Build 3\n\nNewer.", path)
        text = path.read_text(encoding="utf-8")
        assert text.count("# DST API Changelog") == 1
```

- [ ] **Step 7: Run tests — verify they fail**

```
.venv/Scripts/pytest core/tests/test_changelog_pipeline.py::TestPrependToChangelog -v
```

Expected: `NotImplementedError`.

- [ ] **Step 8: Implement `prepend_to_changelog()`**

```python
def prepend_to_changelog(entry: str, changelog_path: Path) -> None:
    header = "# DST API Changelog\n"
    if changelog_path.exists():
        existing = changelog_path.read_text(encoding="utf-8")
        # Strip existing header to avoid duplication
        body = existing.removeprefix(header).lstrip("\n")
    else:
        changelog_path.parent.mkdir(parents=True, exist_ok=True)
        body = ""
    changelog_path.write_text(
        f"{header}\n{entry.strip()}\n\n{body}".rstrip() + "\n",
        encoding="utf-8",
    )
```

- [ ] **Step 9: Run all tests so far**

```
.venv/Scripts/pytest core/tests/test_changelog_pipeline.py -v
```

Expected: all tests PASS.

- [ ] **Step 10: Commit**

```bash
git add core/src/core/changelog/pipeline.py core/tests/test_changelog_pipeline.py
git commit -m "feat(changelog): implement load_diff_report and prepend_to_changelog"
```

---

## Chunk 3: LLM call + main() + entry point

### Task 4: Implement `build_changelog_entry()`

**Files:**
- Modify: `core/src/core/changelog/pipeline.py`
- Modify: `core/tests/test_changelog_pipeline.py`

- [ ] **Step 1: Write failing tests for `build_changelog_entry()`**

Add to `core/tests/test_changelog_pipeline.py`:

```python
class TestBuildChangelogEntry:
    def _make_fake_response(self, content: str) -> dict:
        return {"message": {"content": content}}

    def test_returns_markdown_string_on_success(self):
        fake_resp = self._make_fake_response("## Build 718694\n\n### Highlights\nSome changes.")
        with patch("core.changelog.pipeline.ollama_chat", return_value=fake_resp):
            from core.changelog.pipeline import build_changelog_entry
            result = build_changelog_entry(SAMPLE_REPORT)
        assert result is not None
        assert "## Build 718694" in result

    def test_returns_none_on_empty_response(self, capsys):
        fake_resp = self._make_fake_response("")
        with patch("core.changelog.pipeline.ollama_chat", return_value=fake_resp):
            from core.changelog.pipeline import build_changelog_entry
            result = build_changelog_entry(SAMPLE_REPORT)
        assert result is None
        assert "empty" in capsys.readouterr().out.lower()

    def test_calls_ollama_chat_with_think_false(self):
        fake_resp = self._make_fake_response("## Build 718694\n\nContent.")
        with patch("core.changelog.pipeline.ollama_chat", return_value=fake_resp) as mock_chat:
            from core.changelog.pipeline import build_changelog_entry
            build_changelog_entry(SAMPLE_REPORT)
        call_kwargs = mock_chat.call_args
        assert call_kwargs.kwargs.get("think") is False or (
            len(call_kwargs.args) > 2 and call_kwargs.args[2] is False
        )

    def test_uses_version_from_report_not_config(self):
        """Ensure old_ver/new_ver come from report dict, not core.config.VERSION."""
        captured_messages = []
        def fake_chat(model, messages, *, think=True, **kwargs):
            captured_messages.extend(messages)
            return {"message": {"content": "## Build 99999\n\nContent."}}
        with patch("core.changelog.pipeline.ollama_chat", side_effect=fake_chat):
            from core.changelog.pipeline import build_changelog_entry
            build_changelog_entry(SAMPLE_REPORT)
        prompt_text = captured_messages[0]["content"]
        assert "714014 → 718694" in prompt_text

    def test_returns_none_on_llm_exception(self, capsys):
        """ollama_chat raises (network/server error) → returns None, does not propagate."""
        with patch("core.changelog.pipeline.ollama_chat", side_effect=Exception("network error")):
            from core.changelog.pipeline import build_changelog_entry
            result = build_changelog_entry(SAMPLE_REPORT)
        assert result is None
        assert capsys.readouterr().out  # some warning printed
```

- [ ] **Step 2: Run tests — verify they fail**

```
.venv/Scripts/pytest core/tests/test_changelog_pipeline.py::TestBuildChangelogEntry -v
```

Expected: `NotImplementedError`.

- [ ] **Step 3: Implement `build_changelog_entry()`**

Ensure the full imports block at top of `pipeline.py` is:

```python
# core/src/core/changelog/pipeline.py
import argparse
import json
import signal
import sys
from pathlib import Path

from core.changelog.prompts import build_changelog_prompt
from core.utils import shutdown
from llm.client import ollama_chat
from llm.paths import DATA_DIR, PROJECT_ROOT
from llm.settings import MODEL_UPDATE
```

Replace the stub:

```python
def build_changelog_entry(report: dict) -> str | None:
    old_ver = report["version"]["old"]
    new_ver = report["version"]["new"]
    date = report["date"]
    changes = report["changes"]

    prompt = build_changelog_prompt(
        old_ver=old_ver,
        new_ver=new_ver,
        date=date,
        changes=changes,
    )

    try:
        response = ollama_chat(
            MODEL_UPDATE,
            [{"role": "user", "content": prompt}],
            think=False,
        )
    except Exception as e:
        print(f"[Changelog] Warning: LLM call failed — {e}")
        return None

    content = response["message"]["content"].strip()
    if not content:
        print("[Changelog] Warning: LLM returned empty response.")
        return None
    return content
```

- [ ] **Step 4: Run tests — verify they pass**

```
.venv/Scripts/pytest core/tests/test_changelog_pipeline.py::TestBuildChangelogEntry -v
```

Expected: all 5 tests PASS.

### Task 5: Implement `main()` and CLI entry point

**Files:**
- Modify: `core/src/core/changelog/pipeline.py`
- Create: `core/src/core/changelog/__main__.py`
- Modify: `core/pyproject.toml`
- Modify: `core/tests/test_changelog_pipeline.py`

- [ ] **Step 1: Write failing tests for `main()`**

Add to `core/tests/test_changelog_pipeline.py`:

```python
class TestMain:
    def _run_main(self, tmp_path, argv, llm_content=None, report=None):
        changelog_path = tmp_path / "change-log.md"
        r = report or SAMPLE_REPORT
        fake_resp = {"message": {"content": llm_content or "## Build 718694\n\n### Highlights\nNew critter."}}
        with patch("core.changelog.pipeline.load_diff_report", return_value=r), \
             patch("core.changelog.pipeline.ollama_chat", return_value=fake_resp), \
             patch("core.changelog.pipeline.CHANGELOG_PATH", changelog_path), \
             patch("sys.argv", ["mod-changelog"] + argv):
            from core.changelog.pipeline import main
            main()
        return changelog_path

    def test_writes_changelog_on_success(self, tmp_path):
        path = self._run_main(tmp_path, [])
        assert path.exists()
        assert "## Build 718694" in path.read_text(encoding="utf-8")

    def test_dry_run_does_not_write(self, tmp_path):
        path = self._run_main(tmp_path, ["--dry-run"])
        assert not path.exists()

    def test_dry_run_prints_prompt(self, tmp_path, capsys):
        self._run_main(tmp_path, ["--dry-run"])
        out = capsys.readouterr().out
        assert "714014 → 718694" in out

    def test_already_logged_skips(self, tmp_path):
        changelog_path = tmp_path / "change-log.md"
        changelog_path.write_text(
            "# DST API Changelog\n\n## Build 718694\n\nAlready here.\n",
            encoding="utf-8",
        )
        fake_resp = {"message": {"content": "## Build 718694\n\nNew."}}
        with patch("core.changelog.pipeline.load_diff_report", return_value=SAMPLE_REPORT), \
             patch("core.changelog.pipeline.ollama_chat", return_value=fake_resp) as mock_chat, \
             patch("core.changelog.pipeline.CHANGELOG_PATH", changelog_path), \
             patch("sys.argv", ["mod-changelog"]):
            from core.changelog.pipeline import main
            main()
        mock_chat.assert_not_called()
        assert changelog_path.read_text(encoding="utf-8").count("## Build 718694") == 1

    def test_missing_report_exits_1(self, tmp_path, capsys):
        with patch("core.changelog.pipeline.load_diff_report", return_value=None), \
             patch("sys.argv", ["mod-changelog"]):
            from core.changelog.pipeline import main
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 1

    def test_empty_llm_response_exits_1(self, tmp_path, capsys):
        fake_resp = {"message": {"content": ""}}
        with patch("core.changelog.pipeline.load_diff_report", return_value=SAMPLE_REPORT), \
             patch("core.changelog.pipeline.ollama_chat", return_value=fake_resp), \
             patch("sys.argv", ["mod-changelog"]):
            from core.changelog.pipeline import main
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 1
```

- [ ] **Step 2: Run tests — verify they fail**

```
.venv/Scripts/pytest core/tests/test_changelog_pipeline.py::TestMain -v
```

Expected: `NotImplementedError` / `AttributeError` on `CHANGELOG_PATH`.

- [ ] **Step 3: Implement `main()` and add `CHANGELOG_PATH` constant**

Replace the stubs in `pipeline.py`. Add at module level after imports:

```python
from core.utils import shutdown

CHANGELOG_PATH: Path = PROJECT_ROOT / "dst-api-webdocs" / "change-log.md"
```

Replace `main()` stub:

```python
def main() -> None:
    import argparse

    def _handle_sigint(signum, frame):
        if not shutdown.stop_requested:
            print("\n[Changelog] Ctrl+C — stopping.")
            shutdown.request_stop()
        sys.exit(1)

    signal.signal(signal.SIGINT, _handle_sigint)

    parser = argparse.ArgumentParser(description="Generate changelog entry from diff_report.json")
    parser.add_argument("--dry-run", action="store_true", help="Print prompt only, do not call LLM or write file")
    args = parser.parse_args()

    report = load_diff_report()
    if report is None:
        sys.exit(1)

    new_ver = report["version"]["new"]

    if args.dry_run:
        from core.changelog.prompts import build_changelog_prompt
        prompt = build_changelog_prompt(
            old_ver=report["version"]["old"],
            new_ver=new_ver,
            date=report["date"],
            changes=report["changes"],
        )
        print(prompt)
        sys.exit(0)

    # Idempotency check
    if CHANGELOG_PATH.exists():
        existing = CHANGELOG_PATH.read_text(encoding="utf-8")
        if f"## Build {new_ver}" in existing:
            print(f"[Changelog] Already logged: Build {new_ver}. Use --force to overwrite.")
            sys.exit(0)

    entry = build_changelog_entry(report)
    if entry is None:
        sys.exit(1)

    prepend_to_changelog(entry, CHANGELOG_PATH)
    print(f"[Changelog] Done: {CHANGELOG_PATH}")
```

- [ ] **Step 4: Create `__main__.py`**

```python
# core/src/core/changelog/__main__.py
from core.changelog.pipeline import main

main()
```

- [ ] **Step 5: Add entry point to `core/pyproject.toml`**

In `[project.scripts]`, add:

```toml
mod-changelog = "core.changelog.pipeline:main"
```

Then re-sync:

```
.venv/Scripts/uv sync
```

- [ ] **Step 6: Run all tests**

```
.venv/Scripts/pytest core/tests/test_changelog_pipeline.py -v
```

Expected: all tests PASS.

- [ ] **Step 7: Smoke test — dry-run**

```
.venv/Scripts/python -m core.changelog --dry-run
```

Expected: prompt printed to stdout with `BUILD: 714014 → 718694`, no file written.

- [ ] **Step 8: Commit**

```bash
git add core/src/core/changelog/pipeline.py core/src/core/changelog/__main__.py core/pyproject.toml core/tests/test_changelog_pipeline.py
git commit -m "feat(changelog): implement pipeline main, LLM call, and CLI entry point"
```

---

## Final: Full test run

- [ ] **Run full test suite to confirm no regressions**

```
.venv/Scripts/pytest core/tests/ -v
```

Expected: all existing tests still PASS, new changelog tests PASS.

- [ ] **Run integration smoke test (requires real `diff_report.json` and API keys)**

```
.venv/Scripts/python -m core.changelog --dry-run
```

- [ ] **Final commit if any cleanup needed**

```bash
git add -p
git commit -m "chore(changelog): final cleanup"
```
