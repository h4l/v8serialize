from __future__ import annotations

import enum
import sys

# BufferFlags does not exist until 3.12
if sys.version_info >= (3, 12):
    from inspect import BufferFlags as BufferFlags
else:

    class BufferFlags(enum.IntFlag):
        SIMPLE = 0
