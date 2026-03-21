# conftest.py — pytest collection configuration for core/tests/
#
# Standalone integration scripts that execute at module level (and may call
# sys.exit) must be excluded from pytest collection. They are intended to be
# run directly: `python core/tests/chunked_test.py`

collect_ignore = [
    "chunked_test.py",  # integration script: traverses dst-scripts tree at import time
    "test.py",          # integration script: traverses dst-scripts tree at import time
    "test_per_chunk.py",     # standalone script: calls sys.exit() at module level
    "test_file_type_detection.py",  # standalone script: calls sys.exit() at module level
]
