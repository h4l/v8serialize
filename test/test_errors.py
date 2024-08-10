from dataclasses import dataclass

from v8serialize.errors import V8CodecError


@dataclass(init=False)
class ExampleV8CodecError(V8CodecError):
    level: int
    limit: float

    def __init__(self, message: str, *, level: int, limit: float) -> None:
        super().__init__(message)
        self.level = level
        self.limit = limit


def test_v8codecerror_str_with_fields() -> None:
    assert (
        str(ExampleV8CodecError("Level too high", level=3, limit=2.123))
        == "Level too high: level=3, limit=2.123"
    )


def test_v8codecerror_str_without_fields() -> None:
    assert str(V8CodecError("Something went wrong")) == "Something went wrong"
