from __future__ import annotations

from math import isnan
from test.strategies import values_and_objects as mk_values_and_objects

from hypothesis import given
from hypothesis import strategies as st

from v8serialize.jstypes._equality import same_value_zero
from v8serialize.jstypes._v8 import V8SharedObjectReference, V8SharedValueId
from v8serialize.jstypes.jsmap import JSMap

hashable_values_and_objects = mk_values_and_objects(allow_nan=False, only_hashable=True)
values_and_objects = mk_values_and_objects(allow_nan=False, only_hashable=False)

entries = st.lists(
    elements=st.tuples(values_and_objects, values_and_objects),
    unique_by=lambda t: same_value_zero(t[0]),
)


@given(
    mapping=st.dictionaries(keys=hashable_values_and_objects, values=values_and_objects)
)
def test_equal_to_other_mappings_containing_same_object_instances(
    mapping: dict[object, object]
) -> None:
    assert JSMap(mapping.items()) == mapping


ID = V8SharedValueId(0)


def test_equal_to_other_mappings_containing_different_object_instances() -> None:
    k1, k2 = V8SharedObjectReference(ID), V8SharedObjectReference(ID)
    assert k1 is not k2
    assert k1 == k2

    # JSMap instances are eq from the outside if they contain equal elements in
    # the same order
    jsmap_1_2, jsmap_2_1 = JSMap([(k1, 0), (k2, 0)]), JSMap([(k2, 0), (k1, 0)])

    assert jsmap_1_2 == jsmap_2_1

    # Regular dicts are equal by dict's idea of equality (de-dupe equal keys)
    jsmap_1, jsmap_2 = JSMap([(k1, 0), (0, 0)]), JSMap([(0, 0), (k2, 0)])
    assert jsmap_1 == {V8SharedObjectReference(ID): 0, 0: 0}
    assert jsmap_2 == {V8SharedObjectReference(ID): 0, 0: 0}

    # JSMaps with different item orders are not equal
    assert jsmap_1 != jsmap_2

    # Unequal lengths are not equal
    assert jsmap_1_2 != {V8SharedObjectReference(ID): 0}
    assert jsmap_2_1 != {V8SharedObjectReference(ID): 0}
    # ... despite them being equal if they were de-duped
    assert dict(jsmap_1_2.items()) == {V8SharedObjectReference(ID): 0}
    assert dict(jsmap_2_1.items()) == {V8SharedObjectReference(ID): 0}


def test_eq_with_unhashable_keys() -> None:
    assert JSMap([({}, 1), ({}, 2)]) != {1: "a", 2: "b"}
    assert {1: "a", 2: "b"} != JSMap([({}, 1), ({}, 2)])


def test_eq_with_other_type() -> None:
    assert JSMap().__eq__(object()) is NotImplemented
    assert not (JSMap() == object())


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
