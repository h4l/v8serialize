from __future__ import annotations

import pytest
from hypothesis import strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine,
    initialize,
    invariant,
    precondition,
    rule,
)

from v8serialize._errors import NormalizedKeyError
from v8serialize._pycompat.builtins import callable_staticmethod
from v8serialize.jstypes._normalise_property_key import normalise_property_key
from v8serialize.jstypes.jsarrayproperties import (
    MAX_ARRAY_LENGTH,
    MIN_DENSE_ARRAY_USED_RATIO,
    MIN_SPARSE_ARRAY_SIZE,
    DenseArrayProperties,
)
from v8serialize.jstypes.jsobject import JSObject

integer_name = st.one_of(
    st.integers(max_value=-1), st.integers(min_value=MAX_ARRAY_LENGTH)
)
"""
int values that are not valid as array indexes (due to being negative or too
large).
"""

property_names = st.text().filter(lambda n: isinstance(normalise_property_key(n), str))
"""
JavaScript object property names that are not valid array indexes.
"""

array_indexes = st.integers(min_value=0, max_value=MAX_ARRAY_LENGTH - 1)
usable_array_indexes = st.integers(min_value=0, max_value=200)


class JSObjectComparisonMachine(RuleBasedStateMachine):
    """
    A Hypothesis stateful test for JSObject.

    This Verifies the behaviour of JSObject by driving it through various
    state-mutating actions and verifying the actual state matches a reference
    model.
    """

    actual: JSObject
    reference_array: dict[int, object]
    reference_properties: dict[str, object]

    @initialize()
    def init(self) -> None:
        self.actual = JSObject()
        self.reference_array = {}
        self.reference_properties = {}

    ############################
    # State-dependant strategies

    @property
    def nonexistant_array_indexes(self) -> st.SearchStrategy[int]:
        """
        Get a strategy that generates array indexes without values.

        The generated index values that are in the array's length but empty, or
        above the array's range.
        """
        return array_indexes.filter(lambda i: i not in self.reference_array.keys())

    @callable_staticmethod
    def get_nonexistant_array_indexes(
        self: JSObjectComparisonMachine,
    ) -> st.SearchStrategy[int]:
        return self.nonexistant_array_indexes

    @property
    def existant_array_indexes(self) -> st.SearchStrategy[int]:
        """
        Get a strategy that returns array indexes with values.

        The generated index values have values present in the JSObject array.
        """
        if len(self.reference_array) == 0:
            return st.nothing()
        return st.sampled_from(list(self.reference_array.keys()))

    @callable_staticmethod
    def get_existant_array_indexes(
        self: JSObjectComparisonMachine,
    ) -> st.SearchStrategy[int]:
        return self.existant_array_indexes

    @property
    def existant_property_names(self) -> st.SearchStrategy[str]:
        """
        Get a strategy that returns property names with values.

        The generated property names have values present in the JSObject
        properties.
        """
        if len(self.reference_properties) == 0:
            return st.nothing()
        return st.sampled_from(list(self.reference_properties.keys()))

    @callable_staticmethod
    def get_existant_property_names(
        self: JSObjectComparisonMachine,
    ) -> st.SearchStrategy[str]:
        return self.existant_property_names

    @property
    def nonexistant_property_names(self) -> st.SearchStrategy[str]:
        """
        Get a strategy that returns property names without values.

        The generated property names do not currently have values set in the
        JSObject properties.
        """
        return property_names.filter(
            lambda n: n not in self.reference_properties.keys()
        )

    @callable_staticmethod
    def get_nonexistant_property_names(
        self: JSObjectComparisonMachine,
    ) -> st.SearchStrategy[str]:
        return self.nonexistant_property_names

    #########################
    # Precondition Predicates

    @callable_staticmethod
    def array_not_empty(self: JSObjectComparisonMachine) -> bool:
        return len(self.reference_array) > 0

    @callable_staticmethod
    def properties_not_empty(self: JSObjectComparisonMachine) -> bool:
        return len(self.reference_properties) > 0

    ####################
    # Rules: __getitem__

    @rule(
        index=st.runner().flatmap(get_nonexistant_array_indexes), via_str=st.booleans()
    )
    def getitem_array_non_existant(self, index: int, via_str: bool) -> None:
        key: int | str = str(index) if via_str else index

        assert index not in self.reference_array

        with pytest.raises(NormalizedKeyError) as exc_info:
            self.actual[key]

        assert exc_info.value.raw_key == key

    @rule(index=st.runner().flatmap(get_existant_array_indexes), via_str=st.booleans())
    @precondition(array_not_empty)
    def getitem_array_existant(self, index: int, via_str: bool) -> None:
        key: int | str = str(index) if via_str else index

        assert index in self.reference_array
        assert self.reference_array[index] == self.actual[key]

    @rule(name=st.runner().flatmap(get_existant_property_names))
    @precondition(properties_not_empty)
    def getitem_property_existant(self, name: str) -> None:
        assert name in self.reference_properties

        assert self.reference_properties[name] == self.actual[name]

        # Verify that names that are also ints are treated as name properties
        try:
            index = int(name)
        except ValueError:
            return
        assert index not in self.reference_array
        assert self.reference_properties[name] == self.actual[index]

    @rule(name=st.runner().flatmap(get_nonexistant_property_names))
    def getitem_properties_non_existant(self, name: str) -> None:
        assert name not in self.reference_properties

        with pytest.raises(NormalizedKeyError) as exc_info:
            self.actual[name]

        assert exc_info.value.raw_key == name

        # Verify that names that are also ints are treated as name properties
        try:
            index = int(name)
        except ValueError:
            return

        with pytest.raises(NormalizedKeyError) as exc_info:
            self.actual[index]

        assert exc_info.value.raw_key == index

    ###################
    # Rule: __setitem__

    @rule(
        index=usable_array_indexes,
        via_str=st.booleans(),
        value=st.integers(),
    )
    def setitem_array(self, index: int, via_str: bool, value: int) -> None:
        key: int | str = str(index) if via_str else index
        self.reference_array[index] = value
        self.actual[key] = value

    @rule(
        name=integer_name,
        via_str=st.booleans(),
        value=st.integers(),
    )
    def setitem_property_non_index_int(
        self, name: int, via_str: bool, value: int
    ) -> None:
        name_used: int | str = str(name) if via_str else name
        self.reference_properties[str(name)] = value
        self.actual[name_used] = value

    @rule(
        name=property_names,
        value=st.integers(),
    )
    def setitem_property(self, name: str, value: int) -> None:
        self.reference_properties[name] = value
        self.actual[name] = value

    ###################
    # Rule: __delitem__

    @rule(
        index=st.runner().flatmap(get_nonexistant_array_indexes), via_str=st.booleans()
    )
    def delitem_array_non_existant(self, index: int, via_str: bool) -> None:
        key: int | str = str(index) if via_str else index

        assert index not in self.reference_array

        with pytest.raises(NormalizedKeyError) as exc_info:
            del self.actual[key]

        assert exc_info.value.raw_key == key

    @rule(index=st.runner().flatmap(get_existant_array_indexes), via_str=st.booleans())
    @precondition(array_not_empty)
    def delitem_array_existant(self, index: int, via_str: bool) -> None:
        key: int | str = str(index) if via_str else index

        assert index in self.reference_array

        del self.reference_array[index]
        del self.actual[key]

    @rule(name=st.runner().flatmap(get_existant_property_names))
    @precondition(properties_not_empty)
    def delitem_property_existant(self, name: str) -> None:
        assert name in self.reference_properties

        del self.reference_properties[name]
        del self.actual[name]

    @rule(name=st.runner().flatmap(get_nonexistant_property_names))
    def delitem_properties_non_existant(self, name: str) -> None:
        assert name not in self.reference_properties

        with pytest.raises(NormalizedKeyError) as exc_info:
            del self.actual[name]

        assert exc_info.value.raw_key == name

    ############
    # Invariants

    @invariant()
    def assert_jsobject_len_matches_reference(self) -> None:
        assert len(self.actual) == len(self.reference_array) + len(
            self.reference_properties
        )

    @invariant()
    def assert_jsobject_array_matches_reference_array(self) -> None:
        assert dict(self.actual.array.elements()) == self.reference_array

    @invariant()
    def assert_jsobject_properties_matches_reference_properties(self) -> None:
        assert self.actual.properties == self.reference_properties

    @invariant()
    def assert_jsobject_iter_matches_reference(self) -> None:
        assert list(self.actual) == [
            # ascending numerical order
            *sorted(self.reference_array.keys()),
            # insertion order
            *self.reference_properties.keys(),
        ]

    @invariant()
    def assert_array_is_sparse_when_sparsely_populated(self) -> None:
        array = self.actual.array
        if (
            len(array) >= MIN_SPARSE_ARRAY_SIZE
            and len(self.reference_array) / len(array) < MIN_DENSE_ARRAY_USED_RATIO
        ):
            assert not isinstance(array, DenseArrayProperties)


TestJSObjectComparison = JSObjectComparisonMachine.TestCase
