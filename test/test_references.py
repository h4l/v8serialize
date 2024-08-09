from copy import copy

import pytest

from v8serialize.references import (
    ObjectNotSerializedV8CodecError,
    SerializedId,
    SerializedIdOutOfRangeV8CodecError,
    SerializedObjectLog,
)


def test_serialized_object_log__objects_receive_sequential_ids_from_0() -> None:
    objects = SerializedObjectLog()

    assert objects.record_reference(object()) == SerializedId(0)
    assert objects.record_reference(object()) == SerializedId(1)
    same_obj = set[object]()
    assert objects.record_reference(same_obj) == SerializedId(2)
    assert objects.record_reference(same_obj) == SerializedId(3)


def test_serialized_object_log__can_be_retrieved_by_id() -> None:
    obj1, obj2, set1, set2 = object(), object(), set[object](), set[object]()
    objects = SerializedObjectLog()

    obj1_id = objects.record_reference(obj1)
    obj2_id = objects.record_reference(obj2)
    set1_id = objects.record_reference(set1)
    set2_id = objects.record_reference(set2)

    assert objects.get_object(obj1_id) is obj1
    assert objects.get_object(obj2_id) is obj2
    assert objects.get_object(set1_id) is set1
    assert objects.get_object(set2_id) is set2


def test_serialized_object_log__id_can_be_retrieved_by_object() -> None:
    obj1, obj2, set1, set2 = object(), object(), set[object](), set[object]()
    objects = SerializedObjectLog()

    obj1_id = objects.record_reference(obj1)
    obj2_id = objects.record_reference(obj2)
    set1_id = objects.record_reference(set1)
    set2_id = objects.record_reference(set2)

    assert objects.get_serialized_id(obj1) == obj1_id
    assert objects.get_serialized_id(obj2) == obj2_id
    assert objects.get_serialized_id(set1) == set1_id
    assert objects.get_serialized_id(set2) == set2_id


def test_serialized_object_log__contains_referenced_objects() -> None:
    obj1, obj2, set1, set2 = object(), object(), set[object](), set[object]()
    objects = SerializedObjectLog()

    objects.record_reference(obj1)
    objects.record_reference(obj2)
    objects.record_reference(set1)
    objects.record_reference(set2)

    assert obj1 in objects
    assert obj2 in objects
    assert set1 in objects
    assert set2 in objects


def test_serialized_object_log__does_not_contain_unreferenced_objects() -> None:
    obj1, obj2, set1, set2 = object(), object(), set[object](), set[object]()
    objects = SerializedObjectLog()

    objects.record_reference(obj1)
    objects.record_reference(obj2)
    objects.record_reference(set1)
    objects.record_reference(set2)

    assert copy(obj1) not in objects
    assert copy(obj2) not in objects
    assert copy(set1) not in objects
    assert copy(set2) not in objects


def test_serialized_object_log__getting_unrecorded_id_throws() -> None:
    objects = SerializedObjectLog()

    with pytest.raises(SerializedIdOutOfRangeV8CodecError) as exc_info:
        objects.get_object(SerializedId(42))

    assert exc_info.value.serialized_id == SerializedId(42)
    assert exc_info.value.message == "Serialized ID has not been recorded in the log"


def test_serialized_object_log__getting_unrecorded_object_throws() -> None:
    objects = SerializedObjectLog()

    unrecorded = object()
    with pytest.raises(ObjectNotSerializedV8CodecError) as exc_info:
        objects.get_serialized_id(unrecorded)

    assert exc_info.value.obj is unrecorded
    assert exc_info.value.message == "Object has not been recorded in the log"
