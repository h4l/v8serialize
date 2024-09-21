"""Support for platform-specific data in HostObject extension tags."""

from __future__ import annotations

import functools
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from v8serialize._enums import frozen
from v8serialize._errors import DecodeV8SerializeError
from v8serialize._pycompat.dataclasses import slots_if310
from v8serialize.constants import ArrayBufferViewTag
from v8serialize.jstypes.jsbuffers import (
    ArrayBufferViewStructFormat,
    JSArrayBuffer,
    JSDataView,
    JSTypedArray,
)

if TYPE_CHECKING:
    from v8serialize.decode import ReadableTagStream
    from v8serialize.encode import EncodeContext, EncodeNextFn, WritableTagStream


class NodeJsArrayBufferViewHostObjectHandler:
    """
    Support for deserializing ArrayBuffer views from NodeJS's custom serialization.

    NodeJS uses its own method of serializing ArrayBuffer views instead of the
    default V8 serialization. It encodes them in HostObject tag data (HostObject
    tags are the V8 serialization format's way to allow an application to insert
    their own custom data into the serialized data).

    Examples
    --------
    Serialize a Buffer from Node.JS something like:
    ```bash
    $ node --version
    v22.4.0
    $ node -e 'console.log(
        require("v8").serialize(Uint8Array.from([1, 2, 3]))
            .toString("base64"))'
    /w9cAQMBAgM=
    ```

    >>> from v8serialize import loads, TagReader
    >>> from base64 import b64decode
    >>> decode_steps = [TagReader(
    ...   host_object_deserializer=NodeJsArrayBufferViewHostObjectHandler()
    ... )]
    >>> loads(b64decode('/w9cAQMBAgM='), decode_steps=decode_steps)
    JSUint8Array(JSArrayBuffer(b'\\x01\\x02\\x03'))
    """  # noqa: D301

    def deserialize_host_object(
        self, *, stream: ReadableTagStream
    ) -> JSDataView | JSTypedArray:
        """
        Read a HostObject from the stream as a Node.JS ArrayBuffer/TypedArray.

        Returns
        -------
        :
            The buffer wrapped in a view.

        Raises
        ------
        NodeJsArrayBufferViewHostObjectHandlerDecodeError
            When the stream's HostObject data is not a valid Node.JS Buffer.
        """
        raw_view_code = stream.read_uint32()
        byte_length = stream.read_uint32()
        try:
            buffer_format = NodeBufferFormat(raw_view_code)
        except ValueError:
            raise NodeJsArrayBufferViewHostObjectHandlerDecodeError(
                "Failed to deserialize HostObject with Node.js ArrayBuffer format: "
                f"view code is not a known value: {raw_view_code}",
                position=stream.pos,
                data=stream.data,
            ) from None
        data_start_pos = stream.pos
        data_end_pos = data_start_pos + byte_length
        if data_end_pos > len(stream.data):
            raise NodeJsArrayBufferViewHostObjectHandlerDecodeError(
                "Failed to deserialize HostObject with Node.js ArrayBuffer format: "
                "Data range exceeds the bounds of the available data: "
                f"{data_start_pos}:{data_end_pos}",
                position=stream.pos,
                data=stream.data,
            )
        buffer = JSArrayBuffer(stream.data[data_start_pos:data_end_pos])
        stream.pos = data_end_pos
        return buffer_format.view_format.view_type(buffer)

    def serialize_host_object(
        self, *, stream: WritableTagStream, value: JSDataView | JSTypedArray
    ) -> None:
        """
        Serialize JSDataView and JSTypedArray using Node.js's custom HostObject format.

        [`serialize_js_array_buffer_views_as_nodejs_host_object`]: \
`v8serialize.extensions.serialize_js_array_buffer_views_as_nodejs_host_object`

        See Also
        --------
        [`serialize_js_array_buffer_views_as_nodejs_host_object`]
        """
        # The backing buffer is not shared as a whole, just the portion
        # referenced by the view.
        buffer_format = NodeBufferFormat(value.view_tag)
        with value.get_buffer_as_memoryview().cast("c") as data:
            byte_length = len(data)
            stream.write_uint32(buffer_format.nodejs_code, tag=None)
            stream.write_uint32(byte_length, tag=None)
            stream.data.extend(data)


_node_js_array_buffer_view_host_object_handler = (
    NodeJsArrayBufferViewHostObjectHandler()
)


def serialize_js_array_buffer_views_as_nodejs_host_object(
    value: object, /, ctx: EncodeContext, next: EncodeNextFn
) -> None:
    """
    Serialize JSDataView and JSTypedArray using node.js's custom HostObject format.

    Notes
    -----
    This is an Object Mapper (`SerializeObjectFn`) that can be used to encode
    JSDataView and JSTypedArray in the same custom HostObject format that
    Node.JS writes using the Node.JS `v8.serialize()` function.

    Because Node.JS is capable of reading the normal encoding of
    `JSArrayBuffer`, `JSDataView` and `JSTypedArray`, this doesn't need to be
    used to send data to Node.JS (unlike on the deserializing side, where
    `NodeJsArrayBufferViewHostObjectHandler` must be used to read Node.JS's
    custom encoding).
    """
    if isinstance(value, (JSDataView, JSTypedArray)) and NodeBufferFormat.supports(
        value.view_tag
    ):
        ctx.stream.write_host_object(
            value, serializer=_node_js_array_buffer_view_host_object_handler
        )
        return
    next(value)


@dataclass(unsafe_hash=True, **slots_if310())
class ViewFormat:
    nodejs_code: int
    view_format: ArrayBufferViewStructFormat


@frozen
class NodeBufferFormat(ViewFormat, Enum):
    # These are defined in node.js's v8 module:
    # https://github.com/nodejs/node/blob/821ffab0f78972d6e63bafa598b0c6d92550072b/lib/v8.js#L296
    Int8Array = 0, ArrayBufferViewStructFormat.Int8Array
    Uint8Array = 1, ArrayBufferViewStructFormat.Uint8Array
    Uint8ClampedArray = 2, ArrayBufferViewStructFormat.Uint8ClampedArray
    Int16Array = 3, ArrayBufferViewStructFormat.Int16Array
    Uint16Array = 4, ArrayBufferViewStructFormat.Uint16Array
    Int32Array = 5, ArrayBufferViewStructFormat.Int32Array
    Uint32Array = 6, ArrayBufferViewStructFormat.Uint32Array
    Float32Array = 7, ArrayBufferViewStructFormat.Float32Array
    Float64Array = 8, ArrayBufferViewStructFormat.Float64Array
    DataView = 9, ArrayBufferViewStructFormat.DataView
    # FastBuffer is node.js's internal Uint8Array variant that has its bytes
    # stored in a buffer shared by multiple FastBuffers. We'll just represent it
    # as a Uint8Array.
    FastBuffer = 10, ArrayBufferViewStructFormat.Uint8Array
    BigInt64Array = 11, ArrayBufferViewStructFormat.BigInt64Array
    BigUint64Array = 12, ArrayBufferViewStructFormat.BigUint64Array

    @staticmethod
    @functools.lru_cache  # noqa: B019 # OK because static method
    def _missing_(arg: object) -> NodeBufferFormat | None:
        # Allow looking up values by nodejs_code enum value
        for value in NodeBufferFormat:
            if value.nodejs_code == arg or value.view_format.view_tag is arg:
                return value
        return None

    @staticmethod
    def supports(view_tag: ArrayBufferViewTag) -> bool:
        try:
            NodeBufferFormat(view_tag)
            return True
        except ValueError:
            return False

    if TYPE_CHECKING:

        def __init__(
            self,
            value: int | ArrayBufferViewTag | NodeBufferFormat,
        ) -> None: ...


class NodeJsArrayBufferViewHostObjectHandlerDecodeError(DecodeV8SerializeError):
    """Raised when decoding a HostObject as a Node.JS Buffer fails."""

    pass
