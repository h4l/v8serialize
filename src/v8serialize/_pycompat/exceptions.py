from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    from typing_extensions import TypeGuard


class Notes(Protocol):
    __notes__: list[str]


def has_notes(exc: BaseException) -> TypeGuard[Notes]:
    return isinstance(getattr(exc, "__notes__", None), list)


def add_note(exc: BaseException, note: str) -> None:
    if not isinstance(note, str):
        raise TypeError("note must be a str")
    if not has_notes(exc):
        exc_with_notes = cast(Notes, exc)
        exc_with_notes.__notes__ = notes = []
    else:
        notes = exc.__notes__
    notes.append(note)
