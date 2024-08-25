from math import isnan

from hypothesis import example, given
from hypothesis import strategies as st

from v8serialize.jstypes._equality import same_value_zero
from v8serialize.jstypes._v8 import V8SharedObjectReference
from v8serialize.jstypes.jsmap import JSMap

from .strategies import mk_values_and_objects

hashable_values_and_objects = mk_values_and_objects(allow_nan=False, only_hashable=True)
values_and_objects = mk_values_and_objects(allow_nan=False, only_hashable=False)

entries = st.lists(
    elements=st.tuples(values_and_objects, values_and_objects),
    unique_by=lambda t: same_value_zero(t[0]),
)


@given(
    mapping=st.dictionaries(keys=hashable_values_and_objects, values=values_and_objects)
)
@example({V8SharedObjectReference(shared_value_id=0): 0})
def test_equal_to_other_mappings_containing_same_object_instances(
    mapping: dict[object, object]
) -> None:
    assert JSMap(mapping.items()) == mapping


def test_not_equal_to_other_mappings_containing_different_object_instances():
    a, b = {V8SharedObjectReference(0): 0}, JSMap([(V8SharedObjectReference(0), 0)])
    assert a != b  # the keys are different instances
    assert a == dict(b.items())  # regular dicts are equal by value


def test_eq_with_unhashable_keys() -> None:
    assert JSMap([({}, 1), ({}, 2)]) != {1: "a", 2: "b"}
    assert {1: "a", 2: "b"} != JSMap([({}, 1), ({}, 2)])


def test_jsmap_nan() -> None:
    m = JSMap[float]()
    nan = float("nan")
    m[nan] = 1
    assert m[nan] == 1
    assert isnan(list(m)[0])
    assert nan in m
    m[nan] = 2
    assert len(m) == 1
    assert m[nan] == 2
    del m[nan]
    assert len(m) == 0


@given(entries=entries)
def test_crud(entries: list[tuple[object, object]]) -> None:
    m = JSMap()
    assert len(m) == 0
    for i, (k, v) in enumerate(entries):
        assert k not in m
        m[k] = v
        assert len(m) == i + 1
        assert k in m
        assert m[k] is v

    assert list(m.items()) == entries
    assert list(m) == [k for k, _ in entries]
    assert list(m.values()) == [v for _, v in entries]

    for i, (k, _) in enumerate(entries):
        assert k in m
        del m[k]
        assert k not in m
        assert len(m) == len(entries) - 1 - i

    assert m == {}


def test_init_types() -> None:
    assert JSMap() == {}

    a = JSMap(a=1, b=2)
    b = JSMap([("a", 1), ("b", 2)])
    c = JSMap([("a", 1)], b=2)
    d = JSMap({"a": 1, "b": 2})
    e = JSMap({"a": 1}, b=2)

    maps = [a, b, c, d, e]
    for m in maps:
        assert m == {"a": 1, "b": 2}
        assert list(m) == ["a", "b"]


def test_repr() -> None:
    assert repr(JSMap(c=5, a=1, b=2)) == "JSMap({'c': 5, 'a': 1, 'b': 2})"


def test__str() -> None:
    m = JSMap({"a": 1})
    assert str(m) == repr(m)


def test_abc_register() -> None:
    class FooMapping:
        pass

    JSMap.register(FooMapping)
    assert isinstance(FooMapping(), JSMap)
