from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, TypeVar, overload

if TYPE_CHECKING:
    from typing_extensions import Self, SupportsIndex, TypeAlias

    # https://github.com/python/typeshed/blob/main/stdlib/builtins.pyi
    # fmt: off
    _PositiveInteger: TypeAlias = Literal[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25]  # noqa: E501
    _NegativeInteger: TypeAlias = Literal[-1, -2, -3, -4, -5, -6, -7, -8, -9, -10, -11, -12, -13, -14, -15, -16, -17, -18, -19, -20]  # noqa: E501
    # fmt: on

    T = TypeVar("T")


class JSBigInt(int):
    """A Python `int` subtype that represents JavaScript bigint values."""

    __slots__ = ()

    @overload
    def _wrap_int(self, value: int) -> Self: ...
    @overload
    def _wrap_int(self, value: T) -> T: ...
    def _wrap_int(self, value: object) -> object:
        if isinstance(value, int):
            return self.__class__(value)
        return value

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({super().__repr__()})"

    # Override all the int-returning methods defined in typeshed for int. (Other
    # than methods that return an int incidentally, such as bit_length().)
    # https://github.com/python/typeshed/blob/main/stdlib/builtins.pyi

    def as_integer_ratio(self) -> tuple[Self, Self]:  # type: ignore[override]
        return self, self.__class__(1)

    @property
    def real(self) -> Self:
        return self

    @property
    def imag(self) -> Self:  # type: ignore[override]
        return self.__class__(0)

    @property
    def numerator(self) -> Self:
        return self

    @property
    def denominator(self) -> Self:  # type: ignore[override]
        return self.__class__(1)

    def conjugate(self) -> Self:
        return self

    def __add__(self, value: int, /) -> Self:
        return self._wrap_int(super().__add__(value))

    def __sub__(self, value: int, /) -> Self:
        return self._wrap_int(super().__sub__(value))

    def __mul__(self, value: int, /) -> Self:
        return self._wrap_int(super().__mul__(value))

    def __floordiv__(self, value: int, /) -> Self:
        return self._wrap_int(super().__floordiv__(value))

    # def __truediv__(self, value: int, /) -> float: ...

    def __mod__(self, value: int, /) -> Self:
        return self._wrap_int(super().__mod__(value))

    def __divmod__(self, value: int, /) -> tuple[Self, Self]:
        result = super().__divmod__(value)
        if result is NotImplemented:
            return NotImplemented
        return self.__class__(result[0]), self.__class__(result[1])

    def __radd__(self, value: int, /) -> Self:
        return self._wrap_int(super().__radd__(value))

    def __rsub__(self, value: int, /) -> Self:
        return self._wrap_int(super().__rsub__(value))

    def __rmul__(self, value: int, /) -> Self:
        return self._wrap_int(super().__rmul__(value))

    def __rfloordiv__(self, value: int, /) -> Self:
        return self._wrap_int(super().__rfloordiv__(value))

    # def __rtruediv__(self, value: int, /) -> float: ...

    def __rmod__(self, value: int, /) -> Self:
        return self._wrap_int(super().__rmod__(value))

    def __rdivmod__(self, value: int, /) -> tuple[Self, Self]:
        result = super().__rdivmod__(value)
        if result is NotImplemented:
            return NotImplemented  # type: ignore[no-any-return]
        return self.__class__(result[0]), self.__class__(result[1])

    @overload  # type: ignore[override]
    def __pow__(self, value: _PositiveInteger, mod: None = None, /) -> Self: ...
    @overload
    def __pow__(self, value: _NegativeInteger, mod: None = None, /) -> float: ...
    # # positive __value -> int; negative __value -> float
    # # return type must be Any as `int | float` causes too many false-positive errors
    @overload
    def __pow__(self, value: int, mod: None = None, /) -> Any: ...
    @overload
    def __pow__(self, value: int, mod: int, /) -> int: ...
    def __pow__(self, value: int, mod: int | None = None, /) -> Any:
        return self._wrap_int(super().__pow__(value, mod))

    def __rpow__(self, value: int, mod: int | None = None, /) -> Any:
        return self._wrap_int(super().__rpow__(value, mod))

    def __and__(self, value: int, /) -> Self:
        return self._wrap_int(super().__and__(value))

    def __or__(self, value: int, /) -> Self:
        return self._wrap_int(super().__or__(value))

    def __xor__(self, value: int, /) -> Self:
        return self._wrap_int(super().__xor__(value))

    def __lshift__(self, value: int, /) -> Self:
        return self._wrap_int(super().__lshift__(value))

    def __rshift__(self, value: int, /) -> Self:
        return self._wrap_int(super().__rshift__(value))

    def __rand__(self, value: int, /) -> Self:
        return self._wrap_int(super().__rand__(value))

    def __ror__(self, value: int, /) -> Self:
        return self._wrap_int(super().__ror__(value))

    def __rxor__(self, value: int, /) -> Self:
        return self._wrap_int(super().__rxor__(value))

    def __rlshift__(self, value: int, /) -> Self:
        return self._wrap_int(super().__rlshift__(value))

    def __rrshift__(self, value: int, /) -> Self:
        return self._wrap_int(super().__rrshift__(value))

    def __neg__(self) -> Self:
        return self._wrap_int(super().__neg__())

    def __pos__(self) -> Self:
        return self._wrap_int(super().__pos__())

    def __invert__(self) -> Self:
        return self._wrap_int(super().__invert__())

    def __trunc__(self) -> Self:
        return self._wrap_int(super().__trunc__())

    def __ceil__(self) -> Self:
        return self._wrap_int(super().__ceil__())

    def __floor__(self) -> Self:
        return self._wrap_int(super().__floor__())

    def __round__(self, ndigits: SupportsIndex = 0, /) -> Self:
        return self._wrap_int(super().__round__(ndigits))

    # def __getnewargs__(self) -> tuple[int]: ...
    # def __eq__(self, value: object, /) -> bool: ...
    # def __ne__(self, value: object, /) -> bool: ...
    # def __lt__(self, value: int, /) -> bool: ...
    # def __le__(self, value: int, /) -> bool: ...
    # def __gt__(self, value: int, /) -> bool: ...
    # def __ge__(self, value: int, /) -> bool: ...
    # def __float__(self) -> float: ...
    # def __int__(self) -> int: ...
    def __abs__(self) -> Self:
        return self._wrap_int(super().__abs__())

    # def __hash__(self) -> int: ...
    # def __bool__(self) -> bool: ...
    # def __index__(self) -> int: ...
