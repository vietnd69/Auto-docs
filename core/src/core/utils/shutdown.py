"""
Shared shutdown flag for graceful Ctrl+C handling across modules.
"""

import time

stop_requested = False


def request_stop() -> None:
    global stop_requested
    stop_requested = True


def interruptible_sleep(seconds: int) -> None:
    """Sleep in 1-second increments, stopping early if shutdown is requested."""
    for _ in range(seconds):
        if stop_requested:
            break
        time.sleep(1)
