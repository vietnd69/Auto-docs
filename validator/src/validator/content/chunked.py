"""Chunked file content validation strategy.

Files >= 32K tokens cannot fit in a single LLM context for review.
The content loop (loop.py) only handles standard-size files.
This module will define a separate strategy for large files —
likely section-by-section review or chunk-level review with
cross-chunk consistency checks.

NOT IMPLEMENTED — pipeline.py skips content validation for chunked files
and logs them as "skipped_chunked".
"""
