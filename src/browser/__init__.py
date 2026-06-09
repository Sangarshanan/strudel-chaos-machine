"""Browser automation for Strudel.cc via Playwright."""

from .page import (
    READ_BUFFER_JS,
    WRITE_BUFFER_JS,
    read_buffer,
    trigger_play,
    write_buffer,
)

__all__ = [
    "READ_BUFFER_JS",
    "WRITE_BUFFER_JS",
    "read_buffer",
    "write_buffer",
    "trigger_play",
]
