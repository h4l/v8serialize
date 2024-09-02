from __future__ import annotations

from functools import singledispatchmethod as _singledispatchmethod
from typing import TYPE_CHECKING, Any, Callable, Generic, TypeVar, overload

from v8serialize.constants import SerializationTag

if TYPE_CHECKING:
    from functools import _SingleDispatchCallable
    from typing_extensions import Concatenate, ParamSpec

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


# TODO: remove this if we don't start using it
def tag(tag: SerializationTag) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Mark a function with a SerializationTag.

    Currently for metadata/documentation purposes only.
    """

    def tag_decorator(func: Callable[P, T]) -> Callable[P, T]:
        return func

    return tag_decorator


# typeshed's singledispatchmethod type annotations don't keep the function's
# argument types. We re-define its types to fix that.
if TYPE_CHECKING:

    P = ParamSpec("P")
    S = TypeVar("S")  # self / class
    D = TypeVar("D")  # default dispatch type
    D1 = TypeVar("D1")  # overload dispatch type

    class singledispatchmethod(Generic[S, D, P, T]):
        dispatcher: _SingleDispatchCallable[T]
        func: Callable[Concatenate[S, D, P], T]

        def __init__(self, func: Callable[Concatenate[S, D, P], T]) -> None: ...

        @property
        def __isabstractmethod__(self) -> bool: ...

        # The register decorator can be used like @register to use the 1st arg's
        # type annotation as the dispatch type.
        @overload
        def register(
            self, cls: Callable[Concatenate[S, D1, P], T]
        ) -> Callable[Concatenate[S, D1, P], T]: ...

        # ... or with an explicit type, like @register(bool)
        @overload
        def register(
            self,
            cls: type,
        ) -> Callable[
            [Callable[Concatenate[S, D1, P], T]], Callable[Concatenate[S, D1, P], T]
        ]: ...

        @overload
        def register(
            self, cls: type[Any], method: Callable[Concatenate[D1, P], T]
        ) -> Callable[Concatenate[D1, P], T]: ...

        def register(*args: Any, **kwargs: Any) -> Any: ...

        def __call__(self, value: D, *args: P.args, **kwargs: P.kwargs) -> T: ...

else:
    singledispatchmethod = _singledispatchmethod
