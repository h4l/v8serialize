from __future__ import annotations

import re
import sys
from enum import Enum, auto
from pathlib import Path

from pytest_insta import Fmt


class ExceptionColno(Enum):
    Supported = auto()
    Unsupported = auto()

    @staticmethod
    def get_current() -> ExceptionColno:
        return (
            ExceptionColno.Supported
            if sys.version_info >= (3, 11)
            else ExceptionColno.Unsupported
        )

    @property
    def is_current(self) -> bool:
        return self == ExceptionColno.get_current()


class FmtException(Fmt[str]):  # type: ignore[no-untyped-call] # __init_subclass__
    extension = ".exc.txt"
    project_dir: Path
    colno: ExceptionColno

    def __init__(self) -> None:
        self.project_dir = Path(__file__, "../..").resolve()
        self.project_dir_pattern = re.escape(str(Path(__file__, "../..").resolve()))
        self.colno = ExceptionColno.get_current()

    def with_absolute_paths(self, trace: str) -> str:
        return re.sub(r'(?<=[("])/…/v8serialize/', f"{self.project_dir}/", trace)

    def with_relative_paths(self, trace: str) -> str:
        return re.sub(f'(?<=[("]){self.project_dir_pattern}/', "/…/v8serialize/", trace)

    def with_unknown_colno(self, trace: str) -> str:
        return re.sub(
            r"^(\s+at .* \(.*:\d+):(\d+)\)$",
            r"\1:<unknown>)",
            trace,
            flags=re.MULTILINE,
        )

    def load(self, path: Path) -> str:
        exception_trace = path.read_text()
        exception_trace = self.with_absolute_paths(exception_trace)
        if self.colno is ExceptionColno.Unsupported:
            exception_trace = self.with_unknown_colno(exception_trace)
        return exception_trace

    def dump(self, path: Path, value: str) -> None:
        exception_trace = self.with_relative_paths(value)
        if self.colno is ExceptionColno.Unsupported:
            raise AssertionError(
                f"""\
Cannot dump a modified exception trace snapshot on a platform with \
{self.colno}. You must (re)generate the snapshot on a platform that supports \
column numbers in tracebacks (Python 3.11+) and then run tests on platforms \
that lack column number support to verify the pre-generated snapshot \
matches their behaviour (column numbers are ignored when comparing snapshots
on platforms without column number support)."""
            )
        path.write_text(exception_trace)
