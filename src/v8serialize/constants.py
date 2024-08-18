from dataclasses import dataclass
from enum import IntEnum
from typing import AbstractSet, Final, Literal

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


TagSet = AbstractSet[SerializationTag]


@dataclass(slots=True, frozen=True)
class TagConstraint:
    name: str
    allowed_tags: TagSet

    def __contains__(self, tag: SerializationTag) -> bool:
        """True if `tag` is allowed by the constraint."""
        return tag in self.allowed_tags

    @property
    def allowed_tag_names(self) -> str:
        """The"""
        return ", ".join(sorted(t.name for t in self.allowed_tags))

    def __str__(self) -> str:
        return f"{self.name}: {self.allowed_tag_names}"


JS_OBJECT_KEY_TAGS: Final = TagConstraint(
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

JS_CONSTANT_TAGS: Final = TagConstraint(
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
