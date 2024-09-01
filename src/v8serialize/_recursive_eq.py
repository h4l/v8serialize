from __future__ import annotations

from _thread import get_ident
from functools import wraps
from typing import Final, TypeVar

_RUNNING_EQ_KEYS: Final[set[tuple[int, int]]] = set()

_T = TypeVar("_T")


def recursive_eq(cls: type[_T]) -> type[_T]:
    """Allow `==` of classes with self-referencing fields.

    This class decorator wraps `__eq__` to detect and short-circuit `__eq__`
    being called on an object as a result of itself checking its own equality.
    This allows objects that contain direct or indirect references to themself
    to compare with `==`, without infinite recursive calls until stack overflow.

    Self-referential objects are equal to others if both sides use the same
    object-identity structure (according to `is` / `id()`) and their own
    `__eq__` is `True`.

    For example `a -> b -> a` can be equal to `a' -> b' -> a'`, but will not be
    equal to `a' -> b' -> A' -> B' -> a'` (assuming `a` would be equal to `A` in
    isolation). In the first case, the identity structure has two nodes
    repeating, in the second there are four nodes, so the object-identity
    structure is different.
    """
    wrapped_eq = cls.__eq__

    @wraps(wrapped_eq)
    def decorator(self: object, other: object) -> bool:
        # We must stop if self is other, otherwise we'd try to add ourself
        # twice, which shouldn't be allowed — it'd fail when removing.
        # Could parametrize a default result here for some kind of weird
        # recursive type that doesn't eq itself, but that seems unlikely.
        if self is other:
            return True

        # Keys are different across threads so that concurrent eq calls are
        # independent.
        thread_id = get_ident()
        self_key = id(self), thread_id
        other_key = id(other), thread_id
        self_running = self_key in _RUNNING_EQ_KEYS
        other_running = other_key in _RUNNING_EQ_KEYS

        # If either side already has __eq__ running in the call stack, we must
        # stop recursing, otherwise we'll infinitely loop.
        if self_running or other_running:
            # If both sides were already seen, we might be equal (caller decides)
            # If only one side was running, we can't be equal, as there's a
            # different structure referencing this point.
            return self_running and other_running

        # Register these objects as running so that we won't descend into them
        # if they are referenced again.
        _RUNNING_EQ_KEYS.add(self_key)
        _RUNNING_EQ_KEYS.add(other_key)

        # Allow the type to do its own equality check as normal, descending into
        # children if required.
        try:
            eq = wrapped_eq(self, other)
        finally:
            _RUNNING_EQ_KEYS.remove(self_key)
            _RUNNING_EQ_KEYS.remove(other_key)
        return eq

    cls.__eq__ = decorator  # type: ignore[method-assign]
    return cls
