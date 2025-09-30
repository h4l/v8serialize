# Changelog

All notable changes to v8serialize will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

## [0.4.0]

### Backwards-incompatible changes

#### Dependency changes

- Removed support for Python 3.9 (which is out of support from 1st October 2025)

### Added

- Support for reading Float16Array from Node.js 24

  Although support for Float16Array was added in v8serialize 0.1.0, support for
  them in Node.js was added more recently in version 24. We now support reading
  and writing Float16Array from/to the custom V8 serialization format extension
  Node.js uses to serialize array buffer views. Versions before this would fail
  to decode Float16Array serialised by Node.js 24. ([#12])

### Changed

- Improved typing of JavaScript buffer types (`JSArrayBuffer`,
  `JSArrayBufferView`, `JS*Array`, `JSDataView`). ([#12])

  Assigning These types often required explicit casting, e.g.
  `view: JSTypedArray = JSUint8Array(b'')` would previously be a type error, but
  now works. They now use covariant rather than invariant generic type
  parameters, which allows assigning subtypes to a more general type without
  casting.

[#12]: https://github.com/h4l/v8serialize/issues/12

## [0.3.0] — 2025-09-26

> [!IMPORTANT]
>
> This version made some backwards-incompatible changes, but they are not likely
> to affect typical users, unless they're explicitly creating and persisting
> `JSPrimitiveObject` or customising decoding.

### Backwards-incompatible changes

#### Encoding/decoding changes

- <details>
    <summary>
      Encoding/decoding of
      <a
        href="https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/String"
        >JavaScript boxed String objects</a
      >
      (not regular <code>string</code>) was incorrect and has changed to match the
      current V8 serialization format.
    </summary>
    <br />
    (See the <a href="#0.3.0-fixed">fixed section</a>). The backwards
    compatibility impact of this is that <code>JSPrimitiveObject</code> values
    containing strings serialized by <code>v8serialize</code> before 0.3.0 are not
    deserializable in this version. (Note that this does not affect normal
    JavaScript string values, only wrapped/boxed <code>String</code> objects.)
    These objects are not created by default, so to be affected, code would need
    to have explicitly created and serialised instances and persisted the
    serialised representation to be loaded by this version. Instances of this
    value sent to or received from real V8 implementations are not affected in a
    backwards-incompatible way, as values would fail to decode in either direction
    because of the mutually-incompatible encoding.
  </details>

#### Python API changes

- The `v8serialize.decode.ReadableTagStream.read_js_primitive_object` method now
  requires a `ctx: DecodeContext` argument (as many other methods on this type
  do). This was required to fix [#8].

[#8]: https://github.com/h4l/v8serialize/issues/8

### <a id="0.3.0-fixed"></a>Fixed

- [Wrapped/boxed string values][MDN Primitive] (JavaScript `new String("x")` /
  Python `JSPrimitiveObject("x")`, (used to distinguish `new String("x")` from
  `"x"`)) are now encoded/decoded correctly. Previously they were incorrectly
  being encoded/decoded using an obsolete version of the V8 serialization
  format, earlier than the currently-used format, and earlier than the minimum
  version `v8serialize` supports. ([#8])

### Added

- Support for round-tripping wrapped/boxed JavaScript primitive type objects.

  The `loads()` function and `TagReader` class now take a `js_primitive_objects`
  bool option (defaulting `False`) that uses `JSPrimitiveObject` values in
  decoded values rather than their unwrapped primitive value.

[MDN Primitive]: https://developer.mozilla.org/en-US/docs/Glossary/Primitive

## [0.2.0-alpha.0] - 2024-12-30

I never tagged & published a stable release of this alpha release, I forgot as I
was installing the project from git and then working on other things, sorry!

### Added

- Marked SerializationFeature.Float16Array as released from V8 13.1.201 (was
  marked as unreleased). ([#3](https://github.com/h4l/v8serialize/pull/3))
- `JSBigInt` type — a Python `int` subclass that always encodes to BigInt.
  ([#7](https://github.com/h4l/v8serialize/pull/7))

### Changed

- The API docs now include type annotations in the textual function signatures.
  Previously types were only shown in the table of parameters. Overloaded
  functions with multiple signatures are not shown, only the catch-all signature
  is (this is a limitation of quartodoc).
  ([#6](https://github.com/h4l/v8serialize/pull/6))
- Adjust number encoding rules.

  - The JSBigInt type added in this release always encodes to JavaScript bigint,
    and serialized bigints always decode to JSBigInt.
    - Previously bigint decoded to plain `int`, which meant that bigints in the
      safe float range would not round-trip as bigint, they'd be encoded as one
      of the int types, like Int32, or Double.
  - JavaScript Numbers encoded as Double (float64) now decode to Python `int` if
    they are exact integers in the range of integers that float64 can represent
    exactly.
    - Previously JavaScript Numbers that weren't serialized as one of the int
      types (like Int32) were always decoded as Python `float`.

  The encoding rules now are:

  - Python `float` always encodes to Double/float64.
  - Python `int` encodes to Double/float64 if it's within the float-safe range
    but too large for the int types, like Int32.
  - Python `int` encodes to JavaScript bigint if it's outside than the
    float-safe range.
  - Python `JSBigInt` always encodes to JavaScript bigint.

  The decoding rules now are:

  - JavaScript Double/float64 decodes to Python `float`, unless it's an exact
    integer within the float-safe integer range, in which case it decodes as
    Python `int`.
  - Small int values like Int32 decode as Python `int`.
  - JavaScript bigint values decode as Python `JSBigInt`.

  So values round-trip with the same types consistently, with the exceptions of:

  - large Python `int` which becomes `JSBigInt` after a round-trip.
  - exact integer Python `float` round-trip to Python `int`
    - This is compatible with Python's numeric type system as `int` types are
      accepted by types requiring `float`, and the `/` and `//` operators work
      equivalently with `int` and `float` representations of the same value.
      ([#7](https://github.com/h4l/v8serialize/pull/7))

## [0.1.0] - 2024-09-24

### Added

- The first stable release.

[unreleased]: https://github.com/h4l/v8serialize/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/h4l/v8serialize/releases/tag/v0.1.0
[0.2.0-alpha.0]: https://github.com/h4l/v8serialize/releases/tag/v0.2.0-alpha.0
[0.3.0]: https://github.com/h4l/v8serialize/releases/tag/v0.3.0
[0.4.0]: https://github.com/h4l/v8serialize/releases/tag/v0.4.0
