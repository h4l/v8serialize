"""This is a simplified demo of the protocols defined in v8serialize.typing."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING
from typing_extensions import Protocol, TypeVar, overload, runtime_checkable

T = TypeVar("T")

if TYPE_CHECKING:

    class SpecialisedSequenceProtocol(Sequence[T]):
        def extra_method(self) -> None: ...

else:

    @runtime_checkable
    class SpecialisedSequenceProtocol(Protocol[T]):
        def extra_method(self) -> None: ...

    Sequence.register(SpecialisedSequenceProtocol)


class SpecialisedSequence(SpecialisedSequenceProtocol[T], Sequence[T]):
    pass


class ConcreteSpecialisedSequence(SpecialisedSequence[T]):
    def extra_method(self) -> None:
        return None

    @overload
    def __getitem__(self, i: int, /) -> T: ...

    @overload
    def __getitem__(self, i: slice, /) -> Sequence[T]: ...

    def __getitem__(self, index: int | slice, /) -> T | Sequence[T]:
        raise NotImplementedError

    def __len__(self) -> int:
        raise NotImplementedError


@SpecialisedSequence.register
class OtherImpl(SpecialisedSequenceProtocol[T]):
    def extra_method(self) -> None:
        return

    @overload
    def __getitem__(self, i: int, /) -> T: ...

    @overload
    def __getitem__(self, i: slice, /) -> Sequence[T]: ...

    def __getitem__(self, index: int | slice, /) -> T | Sequence[T]:
        raise NotImplementedError

    def __len__(self) -> int:
        raise NotImplementedError


class Unrelated:
    pass


class CustomList(list[T]):
    def extra_method(self) -> None:
        raise NotImplementedError


def test_other_impl() -> None:
    impl: SpecialisedSequenceProtocol[object] = OtherImpl()
    assert isinstance(impl, SpecialisedSequence)
    assert isinstance(impl, SpecialisedSequenceProtocol)

    seq: Sequence[object] = impl  # noqa: F841
    seq2: Sequence[object] = OtherImpl()  # noqa: F841


def test_spec_seq() -> None:
    specs: SpecialisedSequenceProtocol[object] = ConcreteSpecialisedSequence()
    assert isinstance(specs, SpecialisedSequence)
    assert isinstance(specs, SpecialisedSequenceProtocol)

    seq: Sequence[object] = specs  # noqa: F841
    seq2: Sequence[object] = ConcreteSpecialisedSequence()  # noqa: F841


def test_runtime_checkable() -> None:
    assert not isinstance(Unrelated(), SpecialisedSequenceProtocol)
    assert isinstance(CustomList(), SpecialisedSequenceProtocol)
