from hypothesis import strategies as st

from v8serialize.constants import SerializationTag
from v8serialize.jstypes.jsprimitiveobject import JSPrimitiveObject
from v8serialize.jstypes.jsregexp import JSRegExp
from v8serialize.jstypes.jsundefined import JSUndefined

float_safe_integers = st.integers(min_value=-(2**53 - 1), max_value=2**53 - 1)

js_string_objects = st.builds(
    JSPrimitiveObject, value=st.text(), tag=st.just(SerializationTag.kStringObject)
)


def js_number_objects(allow_nan: bool = True) -> st.SearchStrategy[int | float]:
    return st.builds(
        JSPrimitiveObject,  # type: ignore[arg-type]
        value=float_safe_integers | st.floats(allow_nan=allow_nan),
        tag=st.just(SerializationTag.kNumberObject),
    )


js_bigint_objects = st.builds(
    JSPrimitiveObject, value=st.integers(), tag=st.just(SerializationTag.kBigIntObject)
)
js_true_objects = st.builds(
    JSPrimitiveObject, value=st.just(True), tag=st.just(SerializationTag.kTrueObject)
)
js_false_objects = st.builds(
    JSPrimitiveObject, value=st.just(False), tag=st.just(SerializationTag.kFalseObject)
)


def mk_js_primitive_objects(
    allow_nan: bool = True,
) -> st.SearchStrategy[JSPrimitiveObject]:
    return st.one_of(
        js_string_objects,
        js_number_objects(allow_nan=allow_nan),
        js_bigint_objects,
        js_true_objects,
        js_false_objects,
    )


def mk_values_and_objects(
    *, allow_nan: bool = True, only_hashable: bool = False
) -> st.SearchStrategy[object]:

    hashable_objects = [
        st.from_type(JSRegExp),
        mk_js_primitive_objects(allow_nan=allow_nan),
    ]

    if only_hashable:
        objects = st.one_of(*hashable_objects)
    else:
        objects = st.one_of(st.from_type(object), *hashable_objects)

    return st.one_of(
        st.just(JSUndefined),
        st.none(),
        st.just(True),
        st.just(False),
        st.text(),
        st.binary(),
        st.integers(),
        st.floats(allow_nan=allow_nan),
        objects,
    )
