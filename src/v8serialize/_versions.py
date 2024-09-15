from __future__ import annotations

import re

from packaging.version import VERSION_PATTERN, InvalidVersion, Version

LENIENT_VERSION_PATTERN = re.compile(
    f"^(?P<version>{VERSION_PATTERN})(?:-(?P<suffix>\\S+))?$", re.VERBOSE
)


def parse_lenient_version(version: str) -> Version:
    """
    Parse a version number less strictly than `packaging.version.parse()`.

    Versions can have arbitrary suffixes after a `-`, like `12.9.202.2-rusty`.
    These suffixes become the local part of a Python Version.

    >>> version = parse_lenient_version("12.9.202.2-rusty")
    >>> version
    <Version('12.9.202.2+rusty')>
    >>> version.local
    'rusty'

    >>> parse_lenient_version("12.9.202.2")
    <Version('12.9.202.2')>

    >>> parse_lenient_version("afsdf")  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    packaging.version.InvalidVersion: afsdf
    """
    match = LENIENT_VERSION_PATTERN.match(version)
    if not match:
        raise InvalidVersion(version)

    # We allow trailing local part starting with a dash. The Python version
    # expects a local part to start with a + and contain anything, but doesn't
    # allow a - suffix. Note that if the default pattern's local part matches,
    # we must have no suffix, as local will have consumed it all.
    lenient_suffix = match.group("suffix")
    if lenient_suffix:
        assert not match.group("local")
        return Version(f"{match.group('version')}+{lenient_suffix}")
    return Version(version)
