from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from typing import NewType

V8SharedValueId = NewType("V8SharedValueId", int)


@dataclass(frozen=True, slots=True)
class V8SharedObjectReference(ABC):
    """Represents an inaccessible shared object in a V8 process.

    This can only be used to round-trip a value back to V8. It should resolve to
    an actual JavaScript value. There's no real use-case for this type, it only
    really exists to avoid being unable to deserialize a a larger object graph
    that happens to contain a shared object that is of no consequence.
    """

    shared_value_id: V8SharedValueId
