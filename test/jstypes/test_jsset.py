from math import isnan

from hypothesis import given
from hypothesis import strategies as st

from v8serialize.jstypes._equality import same_value_zero
from v8serialize.jstypes._v8 import V8SharedObjectReference, V8SharedValueId
from v8serialize.jstypes.jsset import JSSet

from .strategies import mk_values_and_objects

hashable_values_and_objects = mk_values_and_objects(allow_nan=False, only_hashable=True)
values_and_objects = mk_values_and_objects(allow_nan=False, only_hashable=False)

elements = st.lists(elements=values_and_objects, unique_by=same_value_zero)


@given(set_=st.sets(elements=hashable_values_and_objects))
def test_equal_to_other_sets(set_: set[object]) -> None:
    assert JSSet(set_) == set_


ID = V8SharedValueId(0)


def test_equal_to_other_sets_containing_different_object_instances() -> None:
    k1, k2 = V8SharedObjectReference(ID), V8SharedObjectReference(ID)
    assert k1 is not k2
    assert k1 == k2

    # JSSet instances are eq from the outside if they contain equal elements in
    # the same order
    jsset_1_2, jsset_2_1 = JSSet([k1, k2]), JSSet([k2, k1])

    assert jsset_1_2 == jsset_2_1

    # Regular sets are equal by set's idea of equality (de-dupe equal members)
    jsset_1, jsset_2 = JSSet([k1, 0]), JSSet([0, k2])
    assert jsset_1 == {V8SharedObjectReference(ID), 0}
    assert jsset_2 == {V8SharedObjectReference(ID), 0}

    # JSSets with different member orders are not equal
    assert jsset_1 != jsset_2

    # Unequal lengths are not equal
    assert jsset_1_2 != {V8SharedObjectReference(ID)}
    assert jsset_2_1 != {V8SharedObjectReference(ID)}
    # ... despite them being equal if they were de-duped
    assert set(jsset_1_2) == {V8SharedObjectReference(ID)}
    assert set(jsset_2_1) == {V8SharedObjectReference(ID)}


def test_eq_with_unhashable_elements() -> None:
    assert JSSet([{}, {}]) != set([1, 2])
    assert set([1, 2]) != JSSet([{}, {}])


def test_eq_with_other_type() -> None:
    assert JSSet().__eq__(object()) is NotImplemented
    assert not (JSSet() == object())


def test_nan() -> None:
    s = JSSet[float]()
    nan = float("nan")
    s.add(nan)
    assert len(s) == 1
    assert isnan(next(iter(s)))
    assert nan in s
    s.add(nan)
    assert len(s) == 1
    s.remove(nan)
    assert len(s) == 0


@given(elements=elements)
def test_crud(elements: list[object]) -> None:
    s = JSSet()
    assert len(s) == 0
    for i, e in enumerate(elements):
        assert e not in s
        s.add(e)
        assert len(s) == i + 1
        assert e in s

    assert list(s) == elements

    for i, e in enumerate(elements):
        assert e in s
        s.remove(e)
        assert e not in s
        assert len(s) == len(elements) - 1 - i

    assert s == set()


def test_jsset__init_types() -> None:
    assert JSSet() == set()

    s = JSSet(["c", "a", "b"])
    assert s == {"c", "a", "b"}
    assert list(s) == ["c", "a", "b"]


def test_repr() -> None:
    assert repr(JSSet(["a", True, {}])) == "JSSet(['a', True, {}])"


def test_str() -> None:
    s = JSSet([1, 2])
    assert str(s) == repr(s)


def test_abc_register() -> None:
    class FooSet:
        pass

    JSSet.register(FooSet)
    assert isinstance(FooSet(), JSSet)
