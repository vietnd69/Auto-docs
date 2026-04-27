"""Validator CLI entry point."""

import argparse
import sys

from llm.settings import MODEL_WRITER, MODEL_REVIEWER
from validator.pipeline import PipelineConfig, process_batch
from validator.utils import DOCS_DIR


def main():
    parser = argparse.ArgumentParser(description="Validate DST API documentation")
    parser.add_argument(
        "target", nargs="?", default=str(DOCS_DIR),
        help="File or directory to validate (default: docs dir)",
    )
    parser.add_argument("--content-only", action="store_true", help="Run content validation only")
    parser.add_argument("--format-only", action="store_true", help="Run format validation only")
    parser.add_argument("--max-iterations", type=int, default=3, help="Max content loop iterations")
    parser.add_argument("--writer-model", default=MODEL_WRITER, help="LLM model for writer")
    parser.add_argument("--reviewer-model", default=MODEL_REVIEWER, help="LLM model for reviewer")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint if available")

    args = parser.parse_args()

    config = PipelineConfig(
        content_max_iterations=args.max_iterations,
        writer_model=args.writer_model,
        reviewer_model=args.reviewer_model,
        skip_content=args.format_only,
        skip_format=args.content_only,
        resume=args.resume,
    )

    try:
        process_batch(args.target, config)
    except KeyboardInterrupt:
        print("\n[Ctrl+C] Exiting safely.")
        sys.exit(0)


if __name__ == "__main__":
    main()
