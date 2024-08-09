from dataclasses import dataclass
from typing import cast


@dataclass(init=False)
class V8CodecError(BaseException):
    message: str

    def __init__(self, message: str, *args: object) -> None:
        super().__init__(message, *args)

    @property  # type: ignore[no-redef]
    def message(self) -> str:
        return cast(str, self.args[0])
