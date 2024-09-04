from __future__ import annotations

import sys
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from typing_extensions import ParamSpec

    _P = ParamSpec("_P")
    _R_co = TypeVar("_R_co", covariant=True)

# @staticmethod decorator is not callable in py3.9, you must reference it via
# the class it's used in. We call it from within the class definition to define
# hypothesis strategies, so we need to call it directly.
if sys.version_info >= (3, 10):
    callable_staticmethod = staticmethod
else:
    if TYPE_CHECKING:

        class callable_staticmethod(staticmethod[_P, _R_co]):
            def __call__(self, *args: _P.args, **kwargs: _P.kwargs) -> _R_co: ...

    else:

        class callable_staticmethod(staticmethod):
            def __call__(self, *args, **kwargs):
                return self.__func__(*args, **kwargs)
