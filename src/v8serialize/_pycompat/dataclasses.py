from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass
from dataclasses import fields as dataclass_fields


@dataclass
class FrozenAfterInitDataclass:
    """A mixin for dataclasses that disallows changing fields after init.

    Fields can be set once and not again. This is an alternative to
    `@dataclass(frozen=True)` — it only freezes dataclass-managed fields, so it
    doesn't affect non-dataclass fields, such as typing.Generic's dunder fields.
    """

    def __delattr__(self, name: str) -> None:
        if name in (f.name for f in dataclass_fields(self)):
            raise FrozenInstanceError(f"cannot delete field {name}")
        super(FrozenAfterInitDataclass, self).__delattr__(name)

    def __setattr__(self, name: str, value: object) -> None:
        if name in (f.name for f in dataclass_fields(self)):
            if hasattr(self, name):
                raise FrozenInstanceError(f"cannot set {name!r}")
        super(FrozenAfterInitDataclass, self).__setattr__(name, value)
