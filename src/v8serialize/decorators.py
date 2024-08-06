from typing import Any, Callable, TypeVar
from typing_extensions import ParamSpec

from v8serialize.constants import SerializationTag

P = ParamSpec("P")
T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


def tag(tag: SerializationTag) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Mark a function with a SerializationTag.

    Currently for metadata/documentation purposes only.
    """

    def tag_decorator(func: Callable[P, T]) -> Callable[P, T]:
        return func

    return tag_decorator
