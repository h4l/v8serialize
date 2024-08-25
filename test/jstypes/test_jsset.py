from math import isnan

from hypothesis import given
from hypothesis import strategies as st

from v8serialize.jstypes._equality import same_value_zero
from v8serialize.jstypes.jsset import JSSet

from .strategies import mk_values_and_objects

hashable_values_and_objects = mk_values_and_objects(allow_nan=False, only_hashable=True)
values_and_objects = mk_values_and_objects(allow_nan=False, only_hashable=False)

elements = st.lists(elements=values_and_objects, unique_by=same_value_zero)


@given(set_=st.sets(elements=hashable_values_and_objects))
def test_equal_to_other_sets(set_: set[object]) -> None:
    assert JSSet(set_) == set_


def test_eq_with_unhashable_elements() -> None:
    assert JSSet([{}, {}]) != set([1, 2])
    assert set([1, 2]) != JSSet([{}, {}])


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
