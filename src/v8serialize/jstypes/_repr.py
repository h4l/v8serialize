from __future__ import annotations

from itertools import islice
from reprlib import Repr
from typing import TYPE_CHECKING, Any, Iterable

from v8serialize.jstypes.jsarrayproperties import SparseArrayProperties

if TYPE_CHECKING:
    from v8serialize.jstypes.jsarray import JSArray
    from v8serialize.jstypes.jsobject import JSObject


class JSRepr(Repr):
    """Generate repr strings for JS types.

    This implements the repr strings used by JSObject and JSArray, which can be
    indented and handle cyclic references by substituting `...` after several
    recursive calls.
    """

    maxjsobject: int
    maxjsarray: int

    def __init__(
        self, *args: Any, maxjsobject: int = 20, maxjsarray: int = 20, **kwargs: Any
    ) -> None:
        super(JSRepr, self).__init__(*args, **kwargs)

        self.maxjsobject = maxjsobject
        self.maxjsarray = maxjsarray

    if TYPE_CHECKING:

        def _join(self, pieces: Iterable[str], level: int) -> str: ...

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


def _contains_single_piece(pieces: list[str]) -> bool:
    if len(pieces) != 1:
        return False
    piece = pieces[0]
    return not ("\n" in piece or "\r" in piece)


default_js_repr = JSRepr(indent=2)
js_repr = default_js_repr.repr