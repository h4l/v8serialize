from abc import ABC, ABCMeta
from typing import Protocol, Sequence


class SpecialisedSequenceProtocol(Protocol):
    def extra_method(self) -> None: ...


class SpecialisedSequence(SpecialisedSequenceProtocol, ABC):
    pass


class ConcreteSpecialisedSequence(SpecialisedSequence):
    def extra_method(self) -> None:
        return None


@SpecialisedSequence.register
class OtherImpl(SpecialisedSequenceProtocol):
    def extra_method(self) -> None:
        return


def test_other_impl() -> None:
    impl = OtherImpl()
    assert isinstance(impl, SpecialisedSequence)


def test_spec_seq() -> None:
    specs: SpecialisedSequenceProtocol = ConcreteSpecialisedSequence()
    assert isinstance(specs, SpecialisedSequence)
