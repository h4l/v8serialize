from typing import Final


class JSUndefinedType:
    def __init__(self) -> None:
        if "JSUndefined" in globals():
            raise AssertionError("Cannot instantiate JSUndefinedType")


JSUndefined: Final = JSUndefinedType()
