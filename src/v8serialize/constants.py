from __future__ import annotations

import operator
import re
from dataclasses import dataclass
from enum import IntEnum, IntFlag
from functools import lru_cache, reduce
from types import MappingProxyType
from typing import (
    TYPE_CHECKING,
    AbstractSet,
    Final,
    Generic,
    Literal,
    Mapping,
    Self,
    TypeGuard,
    TypeVar,
    cast,
    overload,
)

from v8serialize.errors import JSRegExpV8CodecError

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


class JSRegExpFlag(IntFlag):
    """The bit flags for V8's representation of JavaScript RegExp flags.

    Defined at: https://github.com/v8/v8/blob/\
0654522388d6a3782b9831b5de49b0c0abe0f643/src/regexp/regexp-flags.h#L20
    """

    HasIndices = "d", 7, re.NOFLAG
    Global = "g", 0, re.NOFLAG
    IgnoreCase = "i", 1, re.IGNORECASE
    Linear = "l", 6, None
    Multiline = "m", 2, re.MULTILINE
    DotAll = "s", 5, re.DOTALL
    Unicode = "u", 4, re.UNICODE
    UnicodeSets = "v", 8, re.UNICODE
    Sticky = "y", 3, re.NOFLAG
    NoFlag = "", None, re.NOFLAG

    __char: str  # only present on defined values, not combinations
    __python_flag: re.RegexFlag | None

    if not TYPE_CHECKING:  # this __new__ breaks the default Enum types if mypy sees it

        def __new__(
            cls, char: str, bit_index: int | None, python_flag: re.RegexFlag | None
        ) -> Self:
            value = 0 if bit_index is None else (1 << bit_index)
            obj = int.__new__(cls, value)
            obj._value_ = value
            obj.__char = char
            obj.__python_flag = python_flag
            return obj

    @lru_cache(maxsize=1)  # noqa: B019
    @staticmethod
    def _python_flag_mapping() -> Mapping[re.RegexFlag, JSRegExpFlag]:
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
    def from_python_flags(python_flags: re.RegexFlag) -> JSRegExpFlag:
        if python_flags & re.RegexFlag.VERBOSE:
            raise JSRegExpV8CodecError(
                "No equivalent JavaScript RegExp flags exist for RegexFlag.VERBOSE"
            )
        mapping = JSRegExpFlag._python_flag_mapping()
        return reduce(
            operator.or_,
            (mapping[f] for f in re.RegexFlag(python_flags) if f in mapping),
            JSRegExpFlag.NoFlag,
        )

    @property
    def canonical(self) -> JSRegExpFlag:
        return self & 0b111111111

    @overload
    def as_python_flags(self, *, throw: Literal[False]) -> re.RegexFlag | None: ...

    @overload
    def as_python_flags(self, *, throw: Literal[True] = True) -> re.RegexFlag: ...

    def as_python_flags(self, *, throw: bool = True) -> re.RegexFlag | None:
        """The Python re module flags that correspond to this value's active flags.

        Some flags don't have a direct equivalent, such as Linear. These result
        in there being no Python equivalent, so the result is None.

        Some flag don't affect Python because they adjust the JavaScript matching
        API which isn't used in Python. For example, HasIndices. These are ignored.
        """
        flags = reduce(
            lambda f1, f2: None if f1 is None or f2 is None else f1 | f2,
            (f.__python_flag for f in self),
            cast(re.RegexFlag | None, re.NOFLAG),
        )
        if flags is None and throw:
            incompatible = ", ".join(
                f"JSRegExp.{f.name}" for f in self if f.__python_flag is None
            )
            raise JSRegExpV8CodecError(
                f"No equivalent Python flags exist for {incompatible}"
            )
        return flags

    def __str__(self) -> str:
        return "".join(f.__char for f in self)


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


@dataclass(slots=True, frozen=True)
class TagConstraint(Generic[TagT_co]):
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
