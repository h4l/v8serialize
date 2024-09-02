from __future__ import annotations

import sys
from typing import Literal, TypedDict


class NoArg(TypedDict):
    pass


class SlotsTrue(TypedDict):
    slots: Literal[True]


if sys.version_info < (3, 10):

    def slots_if310() -> NoArg:
        return NoArg()

else:

    def slots_if310() -> SlotsTrue:
        return SlotsTrue(slots=True)
