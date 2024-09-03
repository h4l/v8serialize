from __future__ import annotations

import sys

if sys.version_info >= (3, 10):
    from types import NoneType as NoneType
else:
    NoneType = type(None)
