from __future__ import annotations

import warnings
from _thread import get_ident
from collections.abc import Collection, Iterable
from contextlib import contextmanager
from itertools import islice
from reprlib import Repr
from typing import TYPE_CHECKING, Any, ContextManager, Final, Generator, overload

from v8serialize.constants import JSErrorName
from v8serialize.jstypes.jsarrayproperties import SparseArrayProperties

if TYPE_CHECKING:
    from v8serialize.jstypes.jsarray import JSArray
    from v8serialize.jstypes.jserror import JSError
    from v8serialize.jstypes.jsmap import JSMap
    from v8serialize.jstypes.jsobject import JSObject
    from v8serialize.jstypes.jsset import JSSet


class RecursiveReprMixin(Repr):
    """reprlib.recursive_repr as a Repr class mixin."""

    fillvalue: str
    __repr_running: set[tuple[int, int]] = set()

    def repr1_safe(self, x: object, level: int) -> str:
        if level <= 0:
            return self.fillvalue
        repr_running = self.__repr_running
        key = id(x), get_ident()
        if key in repr_running:
            return self.fillvalue
        repr_running.add(key)
        try:
            result = self.repr1(x, level)
        finally:
            repr_running.discard(key)
        return result


class JSRepr(RecursiveReprMixin, Repr):
    """Generate repr strings for JS types.

    This implements the repr strings used by JSObject and JSArray, which can be
    indented and handle cyclic references by substituting `...` after several
    recursive calls.
    """

    fillvalue: str
    indent: int | None
    maxjsobject: int
    maxjsarray: int

    @overload
    def __init__(self) -> None: ...

    @overload
    def __init__(
        self,
        *,
        maxjsobject: int = ...,
        maxjsarray: int = ...,
        maxlevel: int = ...,
        maxtuple: int = ...,
        maxlist: int = ...,
        maxarray: int = ...,
        maxdict: int = ...,
        maxset: int = ...,
        maxfrozenset: int = ...,
        maxdeque: int = ...,
        maxstring: int = ...,
        maxlong: int = ...,
        maxother: int = ...,
        fillvalue: str = ...,
        indent: int | None = ...,
    ) -> None: ...

    def __init__(
        self, *, maxjsobject: int = 20, maxjsarray: int = 20, **kwargs: Any
    ) -> None:
        super(JSRepr, self).__init__()

        # Need to always set the non-3.9 fields:
        self.fillvalue = kwargs.pop("fillvalue", "...")
        self.indent = kwargs.pop("indent", None)  # None is a value for indent
        self.maxjsobject = maxjsobject
        self.maxjsarray = maxjsarray

        # Repr init doesn't accept kwargs until 3.12 — set attrs directly
        for k, v in kwargs.items():
            if k not in _known_fields:
                raise TypeError(
                    f"JSRepr.__init__() got an unexpected keyword argument {k!r}"
                )
            if v is not None:
                setattr(self, k, v)

    if TYPE_CHECKING:

        def _join(self, pieces: Iterable[str], level: int) -> str: ...

        def _repr_iterable(
            self,
            obj: Collection[object],
            level: int,
            left: str,
            right: str,
            maxiter: int,
            trail: str = "",
        ) -> str: ...

    else:
        if not hasattr(Repr, "_join"):
            # basic _join without indent for versions < 3.12 without _join()
            def _join(self, pieces: Iterable[str], level: int) -> str:
                return ", ".join(pieces)

    # We need to maintain insertion order in the repr because that's a defined
    # behaviour of JavaScript objects. The default repr behaviour is to sort
    # dict keys, so we can't reuse dict's repr for args to JSObject/JSArray.
    def repr_JSObject(self, obj: JSObject, level: int) -> str:
        return self.__repr_JSObject(obj, level)

    def __repr_JSObject(
        self,
        obj: JSObject,
        level: int,
        type_name: str = "JSObject",
        maxprops: int | None = None,
    ) -> str:
        if len(obj) == 0:
            return f"{type_name}()"

        if level <= 0:
            return f"{type_name}({self.fillvalue})"

        maxprops = self.maxjsobject if maxprops is None else maxprops
        repr1 = self.repr1

        array_pieces: list[str] = []
        if obj.array.elements_used > 0:
            array_pieces = [
                f"{i!r}: {repr1(v, level - 1)}"
                for i, v in islice(obj.array.elements().items(), maxprops)
            ]
            if obj.array.elements_used > maxprops:
                array_pieces.append(self.fillvalue)
            maxprops -= obj.array.elements_used

        all_properties_can_be_kwargs = obj.properties and all(
            isinstance(k, str) and k.isidentifier() for k in obj.properties
        )
        if all_properties_can_be_kwargs:
            kwarg_pieces = [
                f"{k}={repr1(v, level - 1)}"
                for k, v in islice(obj.properties.items(), max(0, maxprops))
            ]
            if len(obj.properties) > maxprops:
                kwarg_pieces.append(self.fillvalue)
            maxprops -= len(obj.properties)

            kwargs_repr = self._join(kwarg_pieces, level)

            if not array_pieces:
                if _contains_single_piece(kwarg_pieces):
                    return f"{type_name}({kwarg_pieces[0]})"
                return f"{type_name}({kwargs_repr})"

            array_repr = self._join(array_pieces, level)
            sep = "" if kwargs_repr[0].isspace() else " "
            return f"{type_name}({{{array_repr}}},{sep}{kwargs_repr})"

        prop_pieces: list[str] = array_pieces
        if obj.properties:
            prop_pieces.extend(
                f"{k!r}: {repr1(v, level - 1)}"
                for k, v in islice(obj.properties.items(), max(0, maxprops))
            )
            if len(obj.properties) > maxprops:
                prop_pieces.append(self.fillvalue)

        props_repr = self._join(prop_pieces, level)
        return f"{type_name}({{{props_repr}}})"

    def repr_JSArray(self, obj: JSArray, level: int) -> str:
        if len(obj) == 0:
            return "JSArray()"

        if level <= 0:
            return f"JSArray({self.fillvalue})"

        maxprops = self.maxjsarray
        repr1 = self.repr1

        if isinstance(obj.array, SparseArrayProperties):
            # If the array is sparse it's best to represent it as a dict of
            # index entries, and this is the same as the JSObject repr.
            return self.__repr_JSObject(
                obj, level, type_name="JSArray", maxprops=maxprops
            )

        array_pieces: list[str] = []
        if len(obj.array) > 0:
            array_pieces = [repr1(v, level - 1) for v in islice(obj.array, maxprops)]
            if len(obj.array) > maxprops:
                array_pieces.append(self.fillvalue)
            maxprops -= len(obj.array)

        all_properties_can_be_kwargs = obj.properties and all(
            isinstance(k, str) and k.isidentifier() for k in obj.properties
        )
        if all_properties_can_be_kwargs:
            kwarg_pieces = [
                f"{k}={repr1(v, level - 1)}"
                for k, v in islice(obj.properties.items(), max(0, maxprops))
            ]
            if len(obj.properties) > maxprops:
                kwarg_pieces.append(self.fillvalue)
            maxprops -= len(obj.properties)

            kwargs_repr = self._join(kwarg_pieces, level)

            if not array_pieces:
                if _contains_single_piece(kwarg_pieces):
                    return f"JSArray({kwarg_pieces[0]})"
                return f"JSArray({kwargs_repr})"

            array_repr = self._join(array_pieces, level)
            sep = "" if kwargs_repr[0].isspace() else " "
            return f"JSArray([{array_repr}],{sep}{kwargs_repr})"

        prop_pieces: list[str] = []
        if obj.properties:
            prop_pieces.extend(
                f"{k!r}: {repr1(v, level - 1)}"
                for k, v in islice(obj.properties.items(), max(0, maxprops))
            )
            if len(obj.properties) > maxprops:
                prop_pieces.append(self.fillvalue)

        props_repr = self._join(prop_pieces, level)

        # We have non-array properties that can't be kwargs (names aren't Python
        # identifiers). If we don't have array props we can pass them as a dict.
        # If we do have a dense array, we represent the dense array as a list,
        # and pass the props as a **{} kwargs to bypass identifier restrictions.
        if not array_pieces:
            if _contains_single_piece(prop_pieces):
                return f"JSArray({{{prop_pieces[0]}}})"
            return f"JSArray({{{props_repr}}})"

        array_repr = self._join(array_pieces, level)
        if prop_pieces:
            return f"JSArray([{array_repr}], **{{{props_repr}}})"
        return f"JSArray([{array_repr}])"

    def repr_JSMap(self, obj: JSMap, level: int) -> str:
        # same as repr_dict() but without sorting entries and "JSMap()" not {}
        n = len(obj)
        if n == 0:
            return "JSMap()"
        if level <= 0:
            return "JSMap({" + self.fillvalue + "})"
        newlevel = level - 1
        repr1 = self.repr1
        pieces = []
        for key in islice(obj, self.maxdict):
            keyrepr = repr1(key, newlevel)
            valrepr = repr1(obj[key], newlevel)
            pieces.append("%s: %s" % (keyrepr, valrepr))
        if n > self.maxdict:
            pieces.append(self.fillvalue)
        s = self._join(pieces, level)
        return "JSMap({%s})" % (s,)

    def repr_JSSet(self, obj: JSSet, level: int) -> str:
        if not obj:
            return "JSSet()"
        return self._repr_iterable(obj, level, "JSSet([", "])", self.maxset)

    def repr_JSError(self, obj: JSError, level: int) -> str:
        args = [
            self.repr1_safe(obj.message, level - 1),
            (
                None
                if obj.name == JSErrorName.Error
                else f"name={self.repr1_safe(obj.name, level - 1)}"
            ),
            (
                None
                if obj.stack is None
                else f"stack={self.repr1_safe(obj.stack, level - 1)}"
            ),
            (
                None
                if obj.cause is None
                else f"cause={self.repr1_safe(obj.cause, level - 1)}"
            ),
        ]
        return f"JSError({self._join((arg for arg in args if arg), level)})"


def _contains_single_piece(pieces: list[str]) -> bool:
    if len(pieces) != 1:
        return False
    piece = pieces[0]
    return not ("\n" in piece or "\r" in piece)


def js_repr(obj: object) -> str:
    """Create an indented/recursively-safe repr with the active repr settings."""
    return active_js_repr.repr(obj)


@overload
def js_repr_settings(
    js_repr: JSRepr, *, force_restore: bool = ...
) -> ContextManager[JSRepr]: ...


@overload
def js_repr_settings(
    *,
    maxjsobject: int | None = ...,
    maxjsarray: int | None = ...,
    maxlevel: int | None = ...,
    maxtuple: int | None = ...,
    maxlist: int | None = ...,
    maxarray: int | None = ...,
    maxdict: int | None = ...,
    maxset: int | None = ...,
    maxfrozenset: int | None = ...,
    maxdeque: int | None = ...,
    maxstring: int | None = ...,
    maxlong: int | None = ...,
    maxother: int | None = ...,
    fillvalue: str | None = ...,
    indent: int | None = ...,
    force_restore: bool = ...,
) -> ContextManager[JSRepr]: ...


@contextmanager
def js_repr_settings(
    js_repr: JSRepr | None = None,
    *,
    force_restore: bool = False,
    **kwargs: int | str | None,
) -> Generator[JSRepr]:
    """Override the active repr settings for JS types.

    This returns a context manager that will restore the previous settings at
    the end of the context block.

    If someone changes the js_repr_settings within your block and your block
    closes before theirs, your block will emit a `JSReprSettingsNotRestored`
    warning and leave the repr settings unchanged. Pass `force_restore=True` to
    restore your initial state anyway and not warn.
    """
    global active_js_repr
    initial_js_repr = active_js_repr

    if not js_repr:
        override_state = {
            field: getattr(initial_js_repr, field) for field in _known_fields
        }
        for k, v in kwargs.items():
            if k not in override_state:
                raise TypeError(
                    f"configure_repr() got an unexpected keyword argument {k!r}"
                )
            if v is not None or k == "indent":  # None is a value for indent
                override_state[k] = v
        js_repr = JSRepr(**override_state)

    active_js_repr = js_repr
    try:
        yield js_repr
    finally:
        if active_js_repr is js_repr or force_restore:
            active_js_repr = initial_js_repr
        else:
            warnings.warn(
                JSReprSettingsNotRestored(
                    "configure_js_repr() is not restoring the initial JSRepr "
                    "instance because the active JSRepr instance is no longer "
                    "the one it created"
                ),
                stacklevel=1,
            )


class JSReprSettingsNotRestored(UserWarning):
    pass


_known_fields: Final = (
    "maxjsobject",
    "maxjsarray",
    "maxlevel",
    "maxtuple",
    "maxlist",
    "maxarray",
    "maxdict",
    "maxset",
    "maxfrozenset",
    "maxdeque",
    "maxstring",
    "maxlong",
    "maxother",
    "fillvalue",
    "indent",
)


default_js_repr = JSRepr(
    indent=None,
    maxjsobject=100,
    maxjsarray=100,
    maxlevel=20,
    maxtuple=100,
    maxlist=100,
    maxarray=100,
    maxdict=100,
    maxset=100,
    maxfrozenset=100,
    maxdeque=100,
    maxstring=200,
    maxother=100,
)

active_js_repr: JSRepr = default_js_repr
