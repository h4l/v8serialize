from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from v8serialize._recursive_eq import recursive_eq


@recursive_eq
@dataclass
class Node:
    value: int
    child: Node | tuple[Node, ...] | None = field(default=None)


def test_recursive_eq__same_instance() -> None:
    b = Node(2)
    a = Node(1, child=b)

    for _ in range(2):
        assert b == b
        assert a == a
        assert a != b

        a.child = a

        assert a == a
        assert a != b


def test_recursive_eq__same_structure_same_identity() -> None:
    b = Node(2)
    a = Node(1, child=b)

    _b = Node(2)
    _a = Node(1, child=_b)

    for _ in range(2):
        assert b == _b
        assert a == _a

    b.child = a
    _b.child = _a

    for _ in range(2):
        assert a == _a

    c = Node(3, child=a)
    b.child = c
    _c = Node(3, child=_a)
    _b.child = _c

    for _ in range(2):
        assert a == _a


def test_recursive_eq__same_structure_different_identity() -> None:
    # value:    #1 -> #2 -> #1 -> #2 ...
    # identity: a  -> b  -> a  -> b ...
    b = Node(2)
    a = Node(1, child=b)
    b.child = a

    # value:    #1  -> #2  -> #1  -> #2 ...
    # identity: _a1 -> _b1 -> _a2 -> _b2 -> _a1 ...
    _b2 = Node(2)
    _a2 = Node(1, child=_b2)
    _b1 = Node(2, child=_a2)
    _a1 = Node(1, child=_b1)
    _b2.child = _a1

    # These are not equal because the recursive identity structure is different.
    for _ in range(2):
        assert a != _a1
    # Could be made eq by using a key based on the node's state rather than id(node)


def test_recursive_eq__handles_failure_in_wrapped_eq() -> None:
    class FailingNode(Node):
        def __eq__(self, value: object) -> bool:
            raise RuntimeError("oops")

    b = Node(2)
    a = Node(1, child=b)
    b.child = a

    _b = Node(2)
    _a = Node(1, child=_b)
    _b.child = _a

    for _ in range(2):
        assert a == _a

    bad_b = Node(2, child=FailingNode(1))  # like a, but eq fails
    bad_a = Node(1, child=bad_b)

    with pytest.raises(RuntimeError, match="oops"):
        a.__eq__(bad_a)

    # State tracking in-progress eq was correctly reset after the error
    for _ in range(2):
        assert a == _a
