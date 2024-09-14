from __future__ import annotations

import functools
import operator
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum, IntFlag
from functools import lru_cache, reduce
from types import MappingProxyType
from typing import (
    TYPE_CHECKING,
    AbstractSet,
    Final,
    Generic,
    Literal,
    TypeVar,
    overload,
)

from packaging.version import Version

from v8serialize._pycompat.dataclasses import FrozenAfterInitDataclass, slots_if310
from v8serialize._pycompat.enum import IntEnum, IterableFlag, IterableIntFlag, StrEnum
from v8serialize._pycompat.re import RegexFlag
from v8serialize._versions import parse_lenient_version
from v8serialize.errors import JSRegExpV8CodecError

if TYPE_CHECKING:
    from typing_extensions import Self, TypeAlias, TypeGuard

kLatestVersion: Final = 15
"""The current supported serialization format implemented here."""

INT32_RANGE: Final = range(-(2**31), 2**31)
UINT32_RANGE: Final = range(0, 2**32)
# The range of MAX_SAFE_INTEGER
FLOAT64_SAFE_INT_RANGE: Final = range(-(2**53 - 1), 2**53)
"""The range of integers which a JavaScript number (64-bit float) can represent
without loss.

Same as Number.MIN_SAFE_INTEGER, Number.MAX_SAFE_INTEGER JavaScript constants.
"""

MAX_ARRAY_LENGTH: Final = 2**32 - 1
MAX_ARRAY_LENGTH_REPR: Final = "2**32 - 1"


class SerializationTag(IntEnum):
    """1-byte tags used to identify the type of the next value.

    This list is a direct translation of the SerializationTag enum in the v8 src:
    https://chromium.googlesource.com/v8/v8/+/f2f3b3f7a22d67d7f5afa66bc39ee2e299cdf63e/src/objects/value-serializer.cc#117
    """

    # version:uint32_t (if at beginning of data, sets version > 0)
    kVersion = 0xFF
    # ignore
    kPadding = ord("\0")
    # refTableSize:uint32_t (previously used for sanity checks; safe to ignore)
    kVerifyObjectCount = ord("?")
    # Oddballs (no data).
    kTheHole = ord("-")
    kUndefined = ord("_")
    kNull = ord("0")
    kTrue = ord("T")
    kFalse = ord("F")
    # Number represented as 32-bit integer, ZigZag-encoded
    # (like sint32 in protobuf)
    kInt32 = ord("I")
    # Number represented as 32-bit unsigned integer, varint-encoded
    # (like uint32 in protobuf)
    kUint32 = ord("U")
    # Number represented as a 64-bit double.
    # Host byte order is used (N.B. this makes the format non-portable).
    kDouble = ord("N")
    # BigInt. Bitfield:uint32_t, then raw digits storage.
    kBigInt = ord("Z")
    # byteLength:uint32_t, then raw data
    kUtf8String = ord("S")
    kOneByteString = ord('"')
    kTwoByteString = ord("c")
    # Reference to a serialized object. objectID:uint32_t
    kObjectReference = ord("^")
    # Beginning of a JS object.
    kBeginJSObject = ord("o")
    # End of a JS object. numProperties:uint32_t
    kEndJSObject = ord("{")
    # Beginning of a sparse JS array. length:uint32_t
    # Elements and properties are written as key/value pairs, like objects.
    kBeginSparseJSArray = ord("a")
    # End of a sparse JS array. numProperties:uint32_t length:uint32_t
    kEndSparseJSArray = ord("@")
    # Beginning of a dense JS array. length:uint32_t
    # |length| elements, followed by properties as key/value pairs
    kBeginDenseJSArray = ord("A")
    # End of a dense JS array. numProperties:uint32_t length:uint32_t
    kEndDenseJSArray = ord("$")
    # Date. millisSinceEpoch:double
    kDate = ord("D")
    # Boolean object. No data.
    kTrueObject = ord("y")
    kFalseObject = ord("x")
    # Number object. value:double
    kNumberObject = ord("n")
    # BigInt object. Bitfield:uint32_t, then raw digits storage.
    kBigIntObject = ord("z")
    # String object, UTF-8 encoding. byteLength:uint32_t, then raw data.
    kStringObject = ord("s")
    # Regular expression, UTF-8 encoding. byteLength:uint32_t, raw data,
    # flags:uint32_t.
    kRegExp = ord("R")
    # Beginning of a JS map.
    kBeginJSMap = ord(";")
    # End of a JS map. length:uint32_t.
    kEndJSMap = ord(":")
    # Beginning of a JS set.
    kBeginJSSet = ord("'")
    # End of a JS set. length:uint32_t.
    kEndJSSet = ord(",")
    # Array buffer. byteLength:uint32_t, then raw data.
    kArrayBuffer = ord("B")
    # Resizable ArrayBuffer.
    kResizableArrayBuffer = ord("~")
    # Array buffer (transferred). transferID:uint32_t
    kArrayBufferTransfer = ord("t")
    # View into an array buffer.
    # subtag:ArrayBufferViewTag, byteOffset:uint32_t, byteLength:uint32_t
    # For typed arrays, byteOffset and byteLength must be divisible by the size
    # of the element.
    # Note: kArrayBufferView is special, and should have an ArrayBuffer (or an
    # ObjectReference to one) serialized just before it. This is a quirk arising
    # from the previous stack-based implementation.
    kArrayBufferView = ord("V")
    # Shared array buffer. transferID:uint32_t
    kSharedArrayBuffer = ord("u")
    # A HeapObject shared across Isolates. sharedValueID:uint32_t
    kSharedObject = ord("p")
    # A wasm module object transfer. next value is its index.
    kWasmModuleTransfer = ord("w")
    # The delegate is responsible for processing all following data.
    # This "escapes" to whatever wire format the delegate chooses.
    kHostObject = ord("\\")
    # A transferred WebAssembly.Memory object. maximumPages:int32_t, then by
    # SharedArrayBuffer tag and its data.
    kWasmMemoryTransfer = ord("m")
    # A list of (subtag: ErrorTag, [subtag dependent data]). See ErrorTag for
    # details.
    kError = ord("r")
    # The following tags are reserved because they were in use in Chromium before
    # the kHostObject tag was introduced in format version 13, at
    #   v8           refs/heads/master@{#43466}
    #   chromium/src refs/heads/master@{#453568}
    #
    # They must not be reused without a version check to prevent old values from
    # starting to deserialize incorrectly. For simplicity, it's recommended to
    # avoid them altogether.
    #
    # This is the set of tags that existed in SerializationTag.h at that time and
    # still exist at the time of this writing (i.e., excluding those that were
    # removed on the Chromium side because there should be no real user data
    # containing them).
    #
    # It might be possible to also free up other tags which were never persisted
    # (e.g. because they were used only for transfer) in the future.
    kLegacyReservedMessagePort = ord("M")
    kLegacyReservedBlob = ord("b")
    kLegacyReservedBlobIndex = ord("i")
    kLegacyReservedFile = ord("f")
    kLegacyReservedFileIndex = ord("e")
    kLegacyReservedDOMFileSystem = ord("d")
    kLegacyReservedFileList = ord("l")
    kLegacyReservedFileListIndex = ord("L")
    kLegacyReservedImageData = ord("#")
    kLegacyReservedImageBitmap = ord("g")
    kLegacyReservedImageBitmapTransfer = ord("G")
    kLegacyReservedOffscreenCanvas = ord("H")
    kLegacyReservedCryptoKey = ord("K")
    kLegacyReservedRTCCertificate = ord("k")


################################################################################
# This is necessary because MyPy treats a Literal of all enum values differently
# to a the enum type itself, but Literal[SerializationTag] is not allowed.

# fmt: off
AnySerializationTag = Literal[SerializationTag.kVersion, SerializationTag.kPadding, SerializationTag.kVerifyObjectCount, SerializationTag.kTheHole, SerializationTag.kUndefined, SerializationTag.kNull, SerializationTag.kTrue, SerializationTag.kFalse, SerializationTag.kInt32, SerializationTag.kUint32, SerializationTag.kDouble, SerializationTag.kBigInt, SerializationTag.kUtf8String, SerializationTag.kOneByteString, SerializationTag.kTwoByteString, SerializationTag.kObjectReference, SerializationTag.kBeginJSObject, SerializationTag.kEndJSObject, SerializationTag.kBeginSparseJSArray, SerializationTag.kEndSparseJSArray, SerializationTag.kBeginDenseJSArray, SerializationTag.kEndDenseJSArray, SerializationTag.kDate, SerializationTag.kTrueObject, SerializationTag.kFalseObject, SerializationTag.kNumberObject, SerializationTag.kBigIntObject, SerializationTag.kStringObject, SerializationTag.kRegExp, SerializationTag.kBeginJSMap, SerializationTag.kEndJSMap, SerializationTag.kBeginJSSet, SerializationTag.kEndJSSet, SerializationTag.kArrayBuffer, SerializationTag.kResizableArrayBuffer, SerializationTag.kArrayBufferTransfer, SerializationTag.kArrayBufferView, SerializationTag.kSharedArrayBuffer, SerializationTag.kSharedObject, SerializationTag.kWasmModuleTransfer, SerializationTag.kHostObject, SerializationTag.kWasmMemoryTransfer, SerializationTag.kError, SerializationTag.kLegacyReservedMessagePort, SerializationTag.kLegacyReservedBlob, SerializationTag.kLegacyReservedBlobIndex, SerializationTag.kLegacyReservedFile, SerializationTag.kLegacyReservedFileIndex, SerializationTag.kLegacyReservedDOMFileSystem, SerializationTag.kLegacyReservedFileList, SerializationTag.kLegacyReservedFileListIndex, SerializationTag.kLegacyReservedImageData, SerializationTag.kLegacyReservedImageBitmap, SerializationTag.kLegacyReservedImageBitmapTransfer, SerializationTag.kLegacyReservedOffscreenCanvas, SerializationTag.kLegacyReservedCryptoKey, SerializationTag.kLegacyReservedRTCCertificate]  # noqa: B950
# fmt: on

# Generate with:
# python -c 'from v8serialize.constants import SerializationTag; print("Literal[{}]".format(", ".join(f"SerializationTag.{t.name}" for t in SerializationTag)))'  # noqa: B950
################################################################################


class ArrayBufferViewTag(IntEnum):
    kInt8Array = ord("b")
    kUint8Array = ord("B")
    kUint8ClampedArray = ord("C")
    kInt16Array = ord("w")
    kUint16Array = ord("W")
    kInt32Array = ord("d")
    kUint32Array = ord("D")
    kFloat16Array = ord("h")
    kFloat32Array = ord("f")
    kFloat64Array = ord("F")
    kBigInt64Array = ord("q")
    kBigUint64Array = ord("Q")
    kDataView = ord("?")


# TODO: rename without plural s
class ArrayBufferViewFlags(IntFlag):
    IsLengthTracking = 1
    IsBufferResizable = 2


class JSRegExpFlag(IterableIntFlag):
    """The bit flags for V8's representation of JavaScript RegExp flags.

    Defined at: https://github.com/v8/v8/blob/\
0654522388d6a3782b9831b5de49b0c0abe0f643/src/regexp/regexp-flags.h#L20
    """

    HasIndices = "d", 7, RegexFlag.NOFLAG
    Global = "g", 0, RegexFlag.NOFLAG
    IgnoreCase = "i", 1, RegexFlag.IGNORECASE
    Linear = "l", 6, None
    Multiline = "m", 2, RegexFlag.MULTILINE
    DotAll = "s", 5, RegexFlag.DOTALL
    Unicode = "u", 4, RegexFlag.UNICODE
    UnicodeSets = "v", 8, RegexFlag.UNICODE
    Sticky = "y", 3, RegexFlag.NOFLAG
    NoFlag = "", None, RegexFlag.NOFLAG

    __char: str  # only present on defined values, not combinations
    __python_flag: RegexFlag | None

    if not TYPE_CHECKING:  # this __new__ breaks the default Enum types if mypy sees it

        def __new__(
            cls, char: str, bit_index: int | None, python_flag: RegexFlag | None
        ) -> Self:
            value = 0 if bit_index is None else (1 << bit_index)
            obj = int.__new__(cls, value)
            obj._value_ = value
            obj.__char = char
            obj.__python_flag = python_flag
            return obj

    @staticmethod
    @lru_cache(maxsize=1)  # noqa: B019
    def _python_flag_mapping() -> Mapping[RegexFlag, JSRegExpFlag]:
        return MappingProxyType(
            {
                f.__python_flag: f
                for f in JSRegExpFlag
                # Exclude Unicode because Unicode and UnicodeSets are mutually
                # exclusive and UnicodeSets enables more features.
                if f.__python_flag and f is not JSRegExpFlag.Unicode
            }
        )

    @staticmethod
    def from_python_flags(python_flags: RegexFlag) -> JSRegExpFlag:
        if python_flags & RegexFlag.VERBOSE:
            raise JSRegExpV8CodecError(
                "No equivalent JavaScript RegExp flags exist for RegexFlag.VERBOSE"
            )
        mapping = JSRegExpFlag._python_flag_mapping()
        return reduce(
            operator.or_,
            (mapping[f] for f in RegexFlag(python_flags) if f in mapping),
            JSRegExpFlag.NoFlag,
        )

    @property
    def canonical(self) -> JSRegExpFlag:
        return self & 0b111111111

    @overload
    def as_python_flags(self, *, throw: Literal[False]) -> RegexFlag | None: ...

    @overload
    def as_python_flags(self, *, throw: Literal[True] = True) -> RegexFlag: ...

    def as_python_flags(self, *, throw: bool = True) -> RegexFlag | None:
        """The Python re module flags that correspond to this value's active flags.

        Some flags don't have a direct equivalent, such as Linear. These result
        in there being no Python equivalent, so the result is None.

        Some flag don't affect Python because they adjust the JavaScript matching
        API which isn't used in Python. For example, HasIndices. These are ignored.
        """
        flags = RegexFlag.NOFLAG
        for f in self:
            if f.__python_flag is None:
                break
            flags |= f.__python_flag
        else:
            return flags

        if not throw:
            return None

        incompatible = ", ".join(
            f"JSRegExp.{f.name}" for f in self if f.__python_flag is None
        )
        raise JSRegExpV8CodecError(
            f"No equivalent Python flags exist for {incompatible}"
        )

    def __str__(self) -> str:
        return "".join(f.__char for f in self)


class SerializationErrorTag(IntEnum):
    EvalErrorPrototype = "E"
    """The error is a EvalError. No accompanying data."""
    RangeErrorPrototype = "R"
    """The error is a RangeError. No accompanying data."""
    ReferenceErrorPrototype = "F"
    """The error is a ReferenceError. No accompanying data."""
    SyntaxErrorPrototype = "S"
    """The error is a SyntaxError. No accompanying data."""
    TypeErrorPrototype = "T"
    """The error is a TypeError. No accompanying data."""
    UriErrorPrototype = "U"
    """The error is a URIError. No accompanying data."""
    Message = "m"
    """Followed by message: string."""
    Cause = "c"
    """Followed by a JS object: cause."""
    Stack = "s"
    """Followed by stack: string."""
    End = "."
    """The end of this error information."""

    if not TYPE_CHECKING:

        def __new__(cls, code_char: str) -> Self:
            code = ord(code_char)
            obj = int.__new__(cls, code)
            obj._value_ = code
            return obj


class JSErrorName(StrEnum):
    EvalError = "EvalError", SerializationErrorTag.EvalErrorPrototype
    RangeError = "RangeError", SerializationErrorTag.RangeErrorPrototype
    ReferenceError = "ReferenceError", SerializationErrorTag.ReferenceErrorPrototype
    SyntaxError = "SyntaxError", SerializationErrorTag.SyntaxErrorPrototype
    TypeError = "TypeError", SerializationErrorTag.TypeErrorPrototype
    UriError = "UriError", SerializationErrorTag.UriErrorPrototype
    Error = "Error", None

    __error_tag: SerializationErrorTag | None

    if not TYPE_CHECKING:

        def __new__(cls, name: str, error_tag: SerializationErrorTag | None) -> Self:
            obj = str.__new__(cls, name)
            obj._value_ = name
            obj.__error_tag = error_tag
            return obj

    @property
    def error_tag(self) -> SerializationErrorTag | None:
        return self.__error_tag

    @staticmethod
    def for_error_name(error_name: str) -> JSErrorName:
        return (
            JSErrorName(error_name) if error_name in JSErrorName else JSErrorName.Error
        )

    @staticmethod
    @lru_cache  # noqa: B019  # OK because static
    def for_error_tag(error_tag: SerializationErrorTag) -> JSErrorName:
        for x in JSErrorName:
            if x.error_tag is error_tag:
                return x
        return JSErrorName.Error


@functools.total_ordering
class SymbolicVersion(Enum):
    Unreleased = "Unreleased"
    """A value greater than all Version instances."""

    def __lt__(self, other: object) -> bool:
        if isinstance(other, Version):
            return False
        if isinstance(other, SymbolicVersion):
            return False
        return NotImplemented


UnreleasedVersion: TypeAlias = Literal[SymbolicVersion.Unreleased]


class SerializationFeature(IterableFlag):
    """Changes to serialization within format versions that affect compatibility.

    V8 makes changes to its serialization format without bumping the version
    number, and these changes affect backwards compatibility by making versions
    before the change unable to deserialize data encoded by versions with the
    change.

    (Based on comments in V8's value-serializer.cc code) V8's compatibility
    policy is that data written by older versions must be deserializable by
    newer versions, but does not require that data written by newer versions is
    deserializable by older versions. To remain compatible with older versions,
    it's necessary to avoid writing data with features newer than the earliest
    version of V8 that needs to read serialized data.

    In general, only writing features that existed at the point that a new
    format version was released will ensure that all V8 versions will continue
    to be able to read the data in the future.

    This flag names the format changes that have occurred, to allow enabling and
    disabling support for them when encoding data.
    """

    MaxCompatibility = 0, "10.0.29"
    """First version with format version v15.

    https://github.com/v8/v8/commit/fc23bc1de29f415f5e3bc080055b67fb3ea19c53
    """

    RegExpUnicodeSets = 1, "10.7.123"
    """Enable writing RegExp with the UnicodeSets flag.

    This wasn't a format change in the serializer itself, but versions of V8
    without support for this flag will not be able to handle RegExp using it.

    The commit adding the `v` flag was made on 2022-09-03:
    https://github.com/v8/v8/commit/5d4567279e30e1e74588c022861b1d8dfc354a4e

    Note that it seems the flag wasn't correctly validated by the serializer, so
    initially V8 could deserialize RegExps that incorrectly used `u` and `v`
    flags at the same time:
    https://github.com/v8/v8/commit/492a4920f011fa2ceeadfe99022d8d573e7d74a6
    We consistently enforce this in JSRegExp.
    """

    ResizableArrayBuffers = 2, "11.0.193"
    """Enable writing Resizable ArrayBuffers.

    This was introduced in v15 Dec 2022:
    https://github.com/v8/v8/commit/3f17de8d3aa447cbedd8047efb90086b936f8d63

    V8 Versions supporting v15 before this cannot deserialize values containing
    resizable ArrayBuffers.
    """

    CircularErrorCause = 4, "12.1.109"
    """
    Support for serializing errors with cause objects referencing the error
    was added to v15 in Nov 2023:
    https://github.com/v8/v8/commit/5ff265b202a593d7f45348c2a3f0d4dd5fdff74e

    Versions before this are not able to de-serialize errors linking to
    themselves in their cause. Also, versions before this change serialize error
    stack after the cause, whereas versions after this serialize the stack
    before the cause and are not able to handle the previous stack encoding.

    We are able to support reading both formats ourselves, despite V8 not being
    able to read errors written before this change (despite the format remaining
    at 15). The new error layout can be read by V8 versions before the change.

    However we must avoid writing errors with self-referencing cause values
    unless this feature is enabled.
    """

    Float16Array = 8, SymbolicVersion.Unreleased
    """
    Support for encoding typed array views holding Float16 elements.

    Added to v15 2024-03-03:
    https://github.com/v8/v8/commit/8fcd3f809ba5c71f7a29bc6623c1f93a9eac72fe

    Versions with v15 support before this will not be able to decode data
    containing such arrays. This added the ArrayBufferViewTag.kFloat16Array
    constant.
    """

    __first_v8_version: Version | UnreleasedVersion

    if not TYPE_CHECKING:

        def __new__(
            cls,
            flag: int,
            first_v8_version: str | UnreleasedVersion,
        ) -> Self:
            obj = object.__new__(cls)
            obj._value_ = flag
            obj.__first_v8_version = (
                Version(first_v8_version)
                if isinstance(first_v8_version, str)
                else first_v8_version
            )
            return obj

    @classmethod
    @functools.lru_cache  # noqa: B019 # OK because static method
    def for_name(cls, name: str, /) -> SerializationFeature:
        # Allow looking up flags by name
        for value in SerializationFeature:
            if value._name_ == name:
                return value
        raise LookupError(name)

    if TYPE_CHECKING:

        def __invert__(self) -> Self: ...

    @property
    def first_v8_version(self) -> Version | UnreleasedVersion:
        return self.__first_v8_version

    @classmethod
    @functools.lru_cache  # noqa: B019 # OK because static method
    def supported_by(
        cls, *, v8_version: Version | UnreleasedVersion | str
    ) -> SerializationFeature:
        """Get the optional serialization features supported by a V8 version or newer.

        Versions of V8 newer than the specified `v8_version` are expected to
        continue to be able to read data serialized with these features, because
        V8 requires that changes to its serialization allow newer versions to
        read data written by older versions. See the
        [information in V8's serializer code for details][v8-compat-comment].

        [v8-compat-comment]: https://github.com/v8/v8/blob/\
42d57fc8309677f13bfb4a443723a4c7306ec1b7/src/objects/value-serializer.cc#L51
        """
        if isinstance(v8_version, str):
            v8_version = parse_lenient_version(v8_version)

        if v8_version < cls.MaxCompatibility.first_v8_version:
            raise LookupError(
                f"V8 version {v8_version} is earlier than the first V8 version "
                f"that supports serialization format {kLatestVersion}. "
                f"v8_version must be >= {cls.MaxCompatibility.first_v8_version}"
            )

        features = cls.MaxCompatibility
        for feature in cls:
            if feature.first_v8_version <= v8_version:
                features |= feature
        return features


if TYPE_CHECKING:
    TagT_co = TypeVar(
        "TagT_co",
        bound=AnySerializationTag,
        default=AnySerializationTag,
        covariant=True,
    )
else:
    TagT_co = TypeVar("TagT_co", bound=AnySerializationTag)

TagSet = AbstractSet[TagT_co]


@dataclass(unsafe_hash=True, **slots_if310())
class TagConstraint(FrozenAfterInitDataclass, Generic[TagT_co]):
    name: str
    allowed_tags: TagSet[TagT_co]

    def __contains__(self, tag: object) -> TypeGuard[TagT_co]:
        """True if `tag` is allowed by the constraint."""
        return tag in self.allowed_tags

    @property
    def allowed_tag_names(self) -> str:
        """The"""
        return ", ".join(sorted(t.name for t in self.allowed_tags))

    def __str__(self) -> str:
        return f"{self.name}: {self.allowed_tag_names}"


ObjectKeyTag = Literal[
    SerializationTag.kInt32,
    SerializationTag.kDouble,
    SerializationTag.kUint32,
    SerializationTag.kNumberObject,
    SerializationTag.kOneByteString,
    SerializationTag.kTwoByteString,
    SerializationTag.kUtf8String,
    SerializationTag.kStringObject,
]

JS_OBJECT_KEY_TAGS: Final = TagConstraint[ObjectKeyTag](
    name="JavaScript Object Keys",
    allowed_tags=frozenset(
        {
            SerializationTag.kInt32,
            SerializationTag.kDouble,
            SerializationTag.kUint32,
            SerializationTag.kNumberObject,
            SerializationTag.kOneByteString,
            SerializationTag.kTwoByteString,
            SerializationTag.kUtf8String,
            SerializationTag.kStringObject,
        }
    ),
)
"""Tags that are allowed in the context of a JSObject key.

Numbers (except bigint) and strings.
"""

ConstantTags = Literal[
    SerializationTag.kTheHole,
    SerializationTag.kUndefined,
    SerializationTag.kNull,
    SerializationTag.kTrue,
    SerializationTag.kFalse,
]

JS_CONSTANT_TAGS: Final = TagConstraint[ConstantTags](
    name="JavaScript Constants",
    allowed_tags=frozenset(
        {
            SerializationTag.kTheHole,
            SerializationTag.kUndefined,
            SerializationTag.kNull,
            SerializationTag.kTrue,
            SerializationTag.kFalse,
        }
    ),
)

ArrayBufferTags = Literal[
    SerializationTag.kArrayBuffer,
    SerializationTag.kResizableArrayBuffer,
    SerializationTag.kSharedArrayBuffer,
    SerializationTag.kArrayBufferTransfer,
]

JS_ARRAY_BUFFER_TAGS: Final = TagConstraint[ArrayBufferTags](
    name="ArrayBuffers",
    allowed_tags=frozenset(
        {
            SerializationTag.kArrayBuffer,
            SerializationTag.kResizableArrayBuffer,
            SerializationTag.kSharedArrayBuffer,
            SerializationTag.kArrayBufferTransfer,
        }
    ),
)

PrimitiveObjectTag = Literal[
    SerializationTag.kTrueObject,
    SerializationTag.kFalseObject,
    SerializationTag.kNumberObject,
    SerializationTag.kBigIntObject,
    SerializationTag.kStringObject,
]

JS_PRIMITIVE_OBJECT_TAGS = TagConstraint[PrimitiveObjectTag](
    name="Primitive wrapper objects",
    allowed_tags=frozenset(
        {
            SerializationTag.kTrueObject,
            SerializationTag.kFalseObject,
            SerializationTag.kNumberObject,
            SerializationTag.kBigIntObject,
            SerializationTag.kStringObject,
        }
    ),
)

StringTag = Literal[
    SerializationTag.kUtf8String,
    SerializationTag.kOneByteString,
    SerializationTag.kTwoByteString,
    SerializationTag.kStringObject,
]

JS_STRING_TAGS = TagConstraint[StringTag](
    name="Strings",
    allowed_tags=frozenset(
        {
            SerializationTag.kUtf8String,
            SerializationTag.kOneByteString,
            SerializationTag.kTwoByteString,
            SerializationTag.kStringObject,
        }
    ),
)
