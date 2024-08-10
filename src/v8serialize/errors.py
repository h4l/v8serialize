from dataclasses import asdict, dataclass
from typing import cast


@dataclass(init=False)
class V8CodecError(BaseException):
    message: str

    def __init__(self, message: str, *args: object) -> None:
        super().__init__(message, *args)

    @property  # type: ignore[no-redef]
    def message(self) -> str:
        return cast(str, self.args[0])

    def __str__(self) -> str:
        field_values = asdict(self)
        message = field_values.pop("message")
        values_fmt = ", ".join(f"{f}={v!r}" for (f, v) in field_values.items())

        return f"{message}{": " if values_fmt else ""}{values_fmt}"
