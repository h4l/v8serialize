from contextlib import contextmanager
from typing import Generator
from unittest import mock

from v8serialize.jstypes import _repr
from v8serialize.jstypes.jsarray import JSArray
from v8serialize.jstypes.jsobject import JSObject


def doctest_jsobject_repr() -> None:
    """
    >>> JSObject()
    JSObject()
    >>> JSObject({'z': 1, 'b': 2, 'c': 3})
    JSObject(
      z=1,
      b=2,
      c=3,
    )
    >>> JSObject({"1001": "b", "1000": "a", "z": "Z", "x": "X"}, z='other')
    JSObject({
      1000: 'a',
      1001: 'b',
    },
      z='other',
      x='X',
    )

    When some properties can't be represented as kwargs we don't split up the
    properties, because order is significant.

    >>> JSObject({'foo bar': 1, 'b': 2, 'c': 3})
    JSObject({
      'foo bar': 1,
      'b': 2,
      'c': 3,
    })
    >>> a = JSObject(a=1)
    >>> a['b'] = a
    >>> a
    JSObject(
      a=1,
      b=JSObject(
        a=1,
        b=JSObject(
          a=1,
          b=JSObject(
            a=1,
            b=JSObject(
              a=1,
              b=JSObject(
                a=1,
                b=JSObject(...),
              ),
            ),
          ),
        ),
      ),
    )
    >>> JSObject(a=JSArray([JSObject(name="Bob"), JSObject(name="Alice", id=2)]))
    JSObject(
      a=JSArray([
        JSObject(name='Bob'),
        JSObject(
          name='Alice',
          id=2,
        ),
      ]),
    )
    """


def doctest_jsobject_maxjsobject() -> None:
    """
    >>> with repr_settings(maxjsobject=1):
    ...     JSObject(a=1, b=2)
    ...     JSObject({"!": 1, "@": 2})
    ...     JSObject({0: "a"}, b=1)
    JSObject(a=1, ...)
    JSObject({'!': 1, ...})
    JSObject({0: 'a'}, ...)

    >>> with repr_settings(indent=2, maxjsobject=1):
    ...     JSObject(a=1, b=2)
    ...     JSObject({"!": 1, "@": 2})
    ...     JSObject({0: "a"}, one='b')
    ...     JSObject({0: "a", 1: 'b'}, two='c')
    JSObject(
      a=1,
      ...,
    )
    JSObject({
      '!': 1,
      ...,
    })
    JSObject({
      0: 'a',
    },
      ...,
    )
    JSObject({
      0: 'a',
      ...,
    },
      ...,
    )
    """


def doctest_jsarray_repr() -> None:
    """
    >>> JSArray()
    JSArray()
    >>> JSArray(["a", "b"])
    JSArray([
      'a',
      'b',
    ])
    >>> JSArray(["a", "b"], x="y")
    JSArray([
      'a',
      'b',
    ],
      x='y',
    )
    >>> JSArray({"1000": "a"})
    JSArray({
      1000: 'a',
    })
    >>> JSArray({"1000": "a", "x": "y"})
    JSArray({
      1000: 'a',
    },
      x='y',
    )
    >>> JSArray(x=1)
    JSArray(x=1)
    >>> JSArray(x=1, y=2)
    JSArray(
      x=1,
      y=2,
    )
    >>> JSArray({'!': 1})
    JSArray({'!': 1})
    >>> JSArray({'!': 1, '!!': 2})
    JSArray({
      '!': 1,
      '!!': 2,
    })
    >>> JSArray({0: 'a', '!': 1, '!!': 2})
    JSArray([
      'a',
    ], **{
      '!': 1,
      '!!': 2,
    })
    >>> a = JSArray(["a"])
    >>> a.array.append(a)
    >>> a
    JSArray([
      'a',
      JSArray([
        'a',
        JSArray([
          'a',
          JSArray([
            'a',
            JSArray([
              'a',
              JSArray([
                'a',
                JSArray(...),
              ]),
            ]),
          ]),
        ]),
      ]),
    ])
    >>> JSArray([JSObject({"names": JSArray(["Bill", "Bob"])})])
    JSArray([
      JSObject(
        names=JSArray([
          'Bill',
          'Bob',
        ]),
      ),
    ])
    """


def doctest_jsarray_maxlevel() -> None:
    """
    >>> with repr_settings(maxlevel=0):
    ...     JSArray(['a'])
    JSArray(...)
    """


def doctest_jsarray_maxjsarray() -> None:
    """
    >>> with repr_settings(maxjsarray=1):
    ...     JSArray(c='C')
    ...     JSArray(c='C', d='D')
    JSArray(c='C')
    JSArray(c='C', ...)

    >>> with repr_settings(maxjsarray=1):
    ...     JSArray(**{'!': 'C'})
    ...     JSArray(**{'!': 'C', '!!': 'D'})
    JSArray({'!': 'C'})
    JSArray({'!': 'C', ...})

    >>> with repr_settings(maxjsarray=1):
    ...     JSArray(['a'])
    ...     JSArray(['a', 'b'])
    ...     JSArray(['a', 'b'], c='C')
    ...     JSArray(['a', 'b'], **{'!': 'C'})
    JSArray(['a'])
    JSArray(['a', ...])
    JSArray(['a', ...], ...)
    JSArray(['a', ...], ...)

    # TODO: test trunction part way through kwargs/obj
    >>> with repr_settings(indent=2, maxjsarray=1):
    ...     JSArray(c='C')
    ...     JSArray(c='C', d='D')
    JSArray(c='C')
    JSArray(
      c='C',
      ...
    )

    >>> with repr_settings(indent=2, maxjsarray=1):
    ...     JSArray(**{'!': 'C'})
    ...     JSArray(**{'!': 'C', '!!': 'D'})
    JSArray({'!': 'C'})
    JSArray({
      '!': 'C',
      ...,
    })

    >>> with repr_settings(indent=2, maxjsarray=1):
    ...     JSArray(['a'])
    ...     JSArray(['a', 'b'])
    ...     JSArray(['a', 'b'], c='C')
    ...     JSArray(['a', 'b'], **{'!': 'C'})
    JSArray([
      'a',
    ])
    JSArray([
      'a',
      ...,
    ])
    JSArray([
      'a',
      ...,
    ],
      ...,
    )
    JSArray([
      'a',
      ...,
    ], **{
      ...,
    })
    """


def test_repr_uses_patched_repr_module_js_repr() -> None:
    # We also want to allow people to hack the _repr module to change the
    # repr, e.g. to disable indentation. We make this easy by referencing the
    # exported js_repr function from the module itself, so patching the module
    # will change the JSArray repr automatically

    no_indent_repr = _repr.JSRepr()
    with mock.patch.object(_repr, "js_repr", no_indent_repr.repr):
        assert repr(JSObject({"a": 1})) == "JSObject(a=1)"
        assert repr(JSArray(["a", "b"])) == "JSArray(['a', 'b'])"


@contextmanager
def repr_settings(
    *,
    indent: int | None = None,
    maxlevel: int | None = None,
    maxjsarray: int | None = None,
    maxjsobject: int | None = None
) -> Generator[None, None, None]:
    custom_repr = _repr.JSRepr(indent=indent)
    if maxlevel is not None:
        custom_repr.maxlevel = maxlevel
    if maxjsarray is not None:
        custom_repr.maxjsarray = maxjsarray
    if maxjsobject is not None:
        custom_repr.maxjsobject = maxjsobject
    with mock.patch.object(_repr, "js_repr", custom_repr.repr):
        yield
