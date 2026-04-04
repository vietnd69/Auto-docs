"""Full pipeline: content loop -> format fix, per file."""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from llm.tokens import count_tokens
from rag.docs import safe_read_lua
from validator.content.loop import ContentLoopConfig, ContentLoopResult, run_content_loop
from validator.content.chunked import run_chunked_content_loop
from validator.format.autofix import FixResult, autofix_file
from validator.format.checks import validate_all, ValidationError
from validator.utils import resolve_lua_path
from llm.settings import CHUNKED_TOKEN_THRESHOLD, VALIDATOR_MAX_ITERATIONS, MODEL_MAIN, MODEL_JURY
from validator.content.checkpoint import load_batch_checkpoint, save_batch_checkpoint


def _never_stop() -> bool:
    return False


@dataclass
class PipelineConfig:
    """Configuration for the full validation pipeline."""
    content_max_iterations: int = VALIDATOR_MAX_ITERATIONS
    writer_model: str = MODEL_MAIN
    reviewer_model: str = MODEL_MAIN
    jury_model: str = MODEL_JURY
    skip_content: bool = False
    skip_format: bool = False
    resume: bool = False
    stop_check: Callable[[], bool] = field(default=_never_stop, repr=False)


@dataclass
class FileResult:
    """Result of processing a single file."""
    filepath: str
    content_result: ContentLoopResult | None
    format_result: FixResult | None
    final_status: str   # "ok", "content_failed", "format_failed"


def process_file(md_filepath: str, config: PipelineConfig) -> FileResult:
    """Process a single .md file through content loop then format fix."""
    content_result = None
    format_result = None

    # --- Content validation ---
    if not config.skip_content:
        lua_filepath = resolve_lua_path(md_filepath)

        if lua_filepath is None:
            print(f"  [pipeline] No Lua source found for {Path(md_filepath).name}, skipping content")
        else:
            content_config = ContentLoopConfig(
                max_iterations=config.content_max_iterations,
                writer_model=config.writer_model,
                reviewer_model=config.reviewer_model,
                jury_model=config.jury_model,
                stop_check=config.stop_check,
            )
            lua_code = safe_read_lua(lua_filepath)
            if lua_code and count_tokens(lua_code) >= CHUNKED_TOKEN_THRESHOLD:
                print(
                    f"  [pipeline] File is chunked (>={CHUNKED_TOKEN_THRESHOLD} tokens), "
                    "running per-section validation..."
                )
                content_result = run_chunked_content_loop(
                    md_filepath, lua_filepath, content_config, resume=config.resume
                )
                # falls through — format validation also runs for chunked files
            else:
                content_result = run_content_loop(md_filepath, lua_filepath, content_config)

            if content_result and not content_result.approved:
                print(
                    f"  [pipeline] Content not approved after {content_result.iterations} iterations"
                )

    accepted_headings = content_result.accepted_headings if content_result else set()
    if accepted_headings:
        print(f"  [pipeline] Jury accepted non-standard replacements for: {', '.join(sorted(accepted_headings))}")

    # --- Format validation ---
    if not config.skip_format:
        errors = validate_all(md_filepath, accepted_headings=accepted_headings)
        if errors:
            print(f"  [pipeline] {len(errors)} format errors found, running autofix")
            format_result = autofix_file(md_filepath, accepted_headings=accepted_headings)
        else:
            format_result = FixResult(changes=[], remaining_errors=[])

    # --- Determine final status ---
    if content_result and not content_result.approved:
        final_status = "content_failed"
    elif format_result and format_result.remaining_errors:
        final_status = "format_failed"
    else:
        final_status = "ok"

    return FileResult(
        filepath=md_filepath,
        content_result=content_result,
        format_result=format_result,
        final_status=final_status,
    )


def process_batch(target: str, config: PipelineConfig) -> list[FileResult]:
    """Process a batch of .md files through the pipeline."""
    target_path = Path(target)
    is_batch = not target_path.is_file()

    if target_path.is_file():
        files = [target_path]
    else:
        files = sorted(target_path.rglob("*.md"))

    # Load batch checkpoint when resuming a directory run
    completed_files: set[str] = set()
    if config.resume and is_batch:
        completed_files = set(load_batch_checkpoint(target))
        if completed_files:
            print(f"[resume] {len(completed_files)} file(s) already processed, skipping")

    print(f"Processing {len(files)} file(s)...")
    results: list[FileResult] = []

    try:
        for i, filepath in enumerate(files, 1):
            filepath_str = str(filepath)
            if filepath_str in completed_files:
                print(f"[{i}/{len(files)}] {filepath.name} -- skipped (checkpoint: already done)")
                continue
            print(f"[{i}/{len(files)}] {filepath.name}")
            result = process_file(str(filepath), config)
            results.append(result)
            print(f"  -> {result.final_status}")

            # Always save batch checkpoint after each file (available for future --resume)
            if is_batch:
                completed_files.add(filepath_str)
                save_batch_checkpoint(target, list(completed_files))
    except KeyboardInterrupt:
        print(f"\n[Ctrl+C] Stopped after {len(results)}/{len(files)} files")

    # Summary
    ok     = sum(1 for r in results if r.final_status == "ok")
    failed = sum(1 for r in results if "failed" in r.final_status)

    print(f"\n{'='*40}")
    print(f"  OK: {ok} | Failed: {failed}")
    print(f"{'='*40}")

    return results
