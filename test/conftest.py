from __future__ import annotations

import re
from pathlib import Path

from pytest_insta import Fmt


class FmtException(Fmt[str]):  # type: ignore[no-untyped-call] # __init_subclass__
    extension = ".exc.txt"
    project_dir: str

    def __init__(self) -> None:
        self.project_dir = f"{Path(__file__, "../..").resolve()}/"

    def with_absolute_paths(self, trace: str) -> str:
        return re.sub(r'(?<=[("])/…/v8serialize/', self.project_dir, trace)

    def with_relative_paths(self, trace: str) -> str:
        return re.sub(r'(?<=[("])/.*/v8serialize/', "/…/v8serialize/", trace)

    def load(self, path: Path) -> str:
        exception_trace = path.read_text()
        return self.with_absolute_paths(exception_trace)

    def dump(self, path: Path, value: str) -> None:
        exception_trace = self.with_relative_paths(value)
        path.write_text(exception_trace)
