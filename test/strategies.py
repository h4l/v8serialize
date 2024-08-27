from datetime import datetime
from typing import Optional, TypeVar, cast

from hypothesis import strategies as st

from v8serialize._values import SharedArrayBufferId, TransferId
from v8serialize.constants import MAX_ARRAY_LENGTH, JSErrorName, JSRegExpFlag
from v8serialize.jstypes import JSObject, JSUndefined
from v8serialize.jstypes._equality import same_value_zero
from v8serialize.jstypes._normalise_property_key import normalise_property_key
from v8serialize.jstypes._v8 import V8SharedObjectReference
from v8serialize.jstypes.jsarray import JSArray
from v8serialize.jstypes.jsarrayproperties import JSHole
from v8serialize.jstypes.jsbuffers import (
    ArrayBufferViewStructFormat,
    JSArrayBuffer,
    JSArrayBufferTransfer,
    JSDataView,
    JSSharedArrayBuffer,
    JSTypedArray,
    ViewFormat,
)
from v8serialize.jstypes.jserror import JSError, JSErrorData
from v8serialize.jstypes.jsmap import JSMap
from v8serialize.jstypes.jsregexp import JSRegExp
from v8serialize.jstypes.jsset import JSSet

_all_excluded = set(globals().keys())

K = TypeVar("K")
T = TypeVar("T")


any_int_or_text = st.one_of(st.integers(), st.text())
uint32s = st.integers(min_value=0, max_value=2**32 - 1)

name_properties = st.text().filter(
    lambda name: isinstance(normalise_property_key(name), str)
)
"""Generate JavaScript object property strings which aren't array indexes."""


def js_objects(
    values: st.SearchStrategy[T],
    *,
    keys: st.SearchStrategy[str | int] = any_int_or_text,
    min_size: int = 0,
    max_size: int | None = None,
) -> st.SearchStrategy[JSObject[T]]:
    """Generates `JSObject` instances with keys drawn from `keys` argument
    and values drawn from `values` argument.

    Behaves like the default `hypothesis.strategies.lists`.
    """
    if (min_size < 0) if max_size is None else not (0 <= min_size <= max_size):
        raise ValueError(
            f"0 <= min_size <= max_size does not hold: {min_size=}, {max_size=}"
        )

    return st.lists(
        st.tuples(keys, values),
        min_size=min_size,
        max_size=max_size,
        # Ensure generated int/str keys are not aliases of each other, which
        # would allow the obj to be less than min_size.
        unique_by=lambda kv: normalise_property_key(kv[0]),
    ).map(JSObject)


def dense_js_arrays(
    elements: st.SearchStrategy[T],
    *,
    min_size: int = 0,
    max_size: Optional[int] = None,
    properties: st.SearchStrategy[JSObject[T]] | None = None,
) -> st.SearchStrategy[JSArray[T]]:

    if (min_size < 0) if max_size is None else not (0 <= min_size <= max_size):
        raise ValueError(
            f"0 <= min_size <= max_size does not hold: {min_size=}, {max_size=}"
        )

    def create_array(content: tuple[list[T], JSObject[T] | None]) -> JSArray[T]:
        elements, properties = content
        js_array = JSArray[T]()
        js_array.array.extend(elements)
        if properties is not None:
            js_array.update(properties)
        return js_array

    return st.tuples(
        st.lists(
            elements,
            min_size=min_size,
            max_size=max_size,
        ),
        st.none() if properties is None else properties,
    ).map(create_array)


def sparse_js_arrays(
    elements: st.SearchStrategy[T],
    *,
    min_element_count: int = 0,
    max_element_count: int = 512,
    max_size: int = MAX_ARRAY_LENGTH,
    properties: st.SearchStrategy[JSObject[T]] | None = None,
) -> st.SearchStrategy[JSArray[T]]:

    if (
        max_size is not None
        and max_element_count is not None
        and max_size < max_element_count
    ):
        raise ValueError("max_size must be >= max_element_count when both are set")
    if max_size is not None and not (0 <= max_size <= MAX_ARRAY_LENGTH):
        raise ValueError(f"max_size must be >=0 and <= {MAX_ARRAY_LENGTH}")

    def create_array(
        content: tuple[st.DataObject, list[T], JSObject[T] | None]
    ) -> JSArray[T]:
        data, values, properties = content
        length = data.draw(st.integers(min_value=len(values), max_value=max_size))
        possible_indexes = st.lists(
            st.integers(min_value=0, max_value=max(0, length - 1)),
            unique=True,
            min_size=len(values),
            max_size=len(values),
        )

        indexes = data.draw(possible_indexes)
        items = zip(indexes, values)

        js_array = JSArray[T]()
        if length > 0:
            js_array[length - 1] = cast(T, JSHole)
        js_array.update(items)
        assert js_array.array.elements_used == len(values)
        if properties:
            js_array.update(properties.items())
        return js_array

    return st.tuples(
        st.data(),
        st.lists(elements, min_size=min_element_count, max_size=max_element_count),
        properties if properties is not None else st.none(),
    ).map(create_array)


fixed_js_array_buffers = st.binary().map(lambda data: JSArrayBuffer(data))

resizable_js_array_buffers = st.builds(
    lambda data, headroom_byte_length: JSArrayBuffer(
        data, max_byte_length=len(data) + headroom_byte_length, resizable=True
    ),
    st.binary(),
    st.integers(min_value=0),
)

normal_js_array_buffers = st.one_of(fixed_js_array_buffers, resizable_js_array_buffers)

shared_array_buffers = uint32s.map(
    lambda value: JSSharedArrayBuffer(SharedArrayBufferId(value))
)
array_buffer_transfers = uint32s.map(
    lambda value: JSArrayBufferTransfer(TransferId(value))
)

js_array_buffers = st.one_of(
    fixed_js_array_buffers,
    resizable_js_array_buffers,
    shared_array_buffers,
    array_buffer_transfers,
)


def js_array_buffer_views(
    backing_buffers: st.SearchStrategy[
        JSArrayBuffer | JSSharedArrayBuffer | JSArrayBufferTransfer
    ] = js_array_buffers,
    view_formats: st.SearchStrategy[ViewFormat] | None = None,
) -> st.SearchStrategy[JSTypedArray | JSDataView]:
    if view_formats is None:
        view_formats = st.sampled_from(ArrayBufferViewStructFormat)

    def create(
        data: st.DataObject,
        view_format: ViewFormat,
        backing_buffer: JSArrayBuffer | JSSharedArrayBuffer | JSArrayBufferTransfer,
    ) -> JSTypedArray | JSDataView:

        if isinstance(backing_buffer, JSArrayBuffer):
            buffer_byte_length = len(backing_buffer.data)
        else:
            # make up a length — the buffer is not connected
            buffer_byte_length = data.draw(
                st.integers(min_value=0, max_value=2**32 - 1)
            )

        byte_offset = data.draw(st.integers(min_value=0, max_value=buffer_byte_length))
        item_length = data.draw(
            st.integers(
                min_value=0,
                max_value=(buffer_byte_length - byte_offset) // view_format.itemsize,
            )
        )
        byte_length = item_length * view_format.itemsize

        return view_format.view_type(
            backing_buffer, byte_offset=byte_offset, byte_length=byte_length
        )

    return st.builds(
        create, data=st.data(), view_format=view_formats, backing_buffer=backing_buffers
    )


def js_errors(
    names: st.SearchStrategy[str] | None = None,
    messages: st.SearchStrategy[str | None] | None = None,
    stacks: st.SearchStrategy[str | None] | None = None,
    causes: st.SearchStrategy[object] | None = None,
) -> st.SearchStrategy[JSError]:
    return st.builds(
        JSError,
        name=st.sampled_from(JSErrorName) if names is None else names,
        message=st.text() | st.none() if messages is None else messages,
        stack=st.text() | st.none() if stacks is None else stacks,
        cause=st.none() if causes is None else causes,
    )


def js_error_data(
    names: st.SearchStrategy[str] | None = None,
    messages: st.SearchStrategy[str | None] | None = None,
    stacks: st.SearchStrategy[str | None] | None = None,
    causes: st.SearchStrategy[object] | None = None,
) -> st.SearchStrategy[JSErrorData]:
    return st.builds(
        JSErrorData,
        name=st.sampled_from(JSErrorName) if names is None else names,
        message=st.text() | st.none() if messages is None else messages,
        stack=st.text() | st.none() if stacks is None else stacks,
        cause=st.none() if causes is None else causes,
    )


def js_regexp_flags(allow_linear: bool = False) -> st.SearchStrategy[JSRegExpFlag]:
    values = st.integers(min_value=JSRegExpFlag.NoFlag, max_value=~JSRegExpFlag.NoFlag)
    if not allow_linear:
        values = values.map(lambda x: x & ~JSRegExpFlag.Linear)  # unset Linear
    return st.builds(JSRegExpFlag, values)


def js_regexps(allow_linear: bool = False) -> st.SearchStrategy[JSRegExp]:
    return st.builds(
        JSRegExp, source=st.text(), flags=js_regexp_flags(allow_linear=allow_linear)
    )


naive_timestamp_datetimes = st.datetimes(min_value=datetime(1, 1, 2)).map(
    # Truncate timestamp precision to nearest 0.25 milliseconds to avoid lossy
    # float operations breaking equality. We don't really care about testing the
    # precision of float operations, just that the values are encoded and
    # decoded as provided.
    lambda dt: datetime.fromtimestamp(round(dt.timestamp() * 4) / 4)
)
"""datetime values rounded slightly by passing through timestamp() representation.

These datetime values can be represented exactly as their timestamp value.
The datetime code does some rounding when converting a timestamp to a datetime,
so if we start form an arbitrary datetime, the fromtimestamp result can be
slightly different, which breaks round-trip equality.
"""

v8_shared_object_references = st.builds(
    V8SharedObjectReference, shared_value_id=uint32s
)


def js_maps(
    keys: st.SearchStrategy[K],
    values: st.SearchStrategy[T],
    min_size: int = 0,
    max_size: int | None = None,
) -> st.SearchStrategy[JSMap[K, T]]:
    return st.builds(
        JSMap,
        st.lists(
            elements=st.tuples(keys, values),
            min_size=min_size,
            max_size=max_size,
            unique_by=lambda i: same_value_zero(i[0]),
        ),
    )


def js_sets(
    elements: st.SearchStrategy[T], min_size: int = 0, max_size: int | None = None
) -> st.SearchStrategy[JSSet[T]]:
    return st.builds(
        JSSet,
        st.lists(
            elements=elements,
            min_size=min_size,
            max_size=max_size,
            unique_by=same_value_zero,
        ),
    )


any_atomic = st.one_of(
    st.integers(),
    # NaN breaks equality when nested inside objects. We test with nan in
    # test_codec_rt_double.
    st.floats(allow_nan=False),
    st.text(),
    st.just(JSUndefined),
    st.just(None),
    st.just(True),
    st.just(False),
    js_regexps(),
    # Use naive datetimes for general tests to avoid needing to normalise tz.
    # (Can't serialize tz, so aware datetimes come back as naive or a fixed tz;
    # epoch timestamp always matches though.)
    naive_timestamp_datetimes,
    v8_shared_object_references,
)

non_hashable_atomic = st.one_of(
    js_array_buffers,
)


# https://hypothesis.works/articles/recursive-data/
any_object = st.recursive(
    any_atomic | non_hashable_atomic,
    lambda children: st.one_of(
        # The rest are recursive types
        st.dictionaries(
            keys=any_atomic,
            values=children,
        ),
        # JSMap can handle non-hashable objects as keys
        js_maps(keys=children, values=children),
        js_objects(values=children),
        dense_js_arrays(
            elements=children,
            properties=js_objects(
                # Extra properties should only be names, not extra array indexes
                keys=name_properties,
                values=children,
                max_size=10,
            ),
            max_size=10,
        ),
        sparse_js_arrays(
            elements=children,
            max_element_count=32,
            properties=js_objects(
                # Extra properties should only be names, not extra array indexes
                keys=name_properties,
                values=children,
                max_size=10,
            ),
        ),
        st.sets(elements=any_atomic),
        # JSSet can handle non-hashable elements
        js_sets(elements=children),
        js_errors(causes=children),
    ),
    max_leaves=3,  # TODO: tune this, perhaps increase in CI
)
