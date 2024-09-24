<p align="center">
  <img src="docs/v8serialize_logo_auto.svg" width="300" alt="The v8serialize logo. Monochome. Large &quot;V8&quot; and smaller &quot;serialize&quot; in a handwritten style, with the 8 stylized to look like a snake.">
</p>

<p align="center"><em>Imagine having <a href="https://developer.mozilla.org/en-US/docs/Web/API/Window/postMessage"><code>postMessage()</code></a> between JavaScript and Python.</em></p>

<table align="center">
  <tr>
    <td><pre lang="shell">pip install v8serialize</pre></td>
  </tr>
</table>

<p align="center"><a href="https://h4l.github.io/v8serialize/en/latest/">Documentation</a></p>

---

# `v8serialize`

A Python library to read & write JavaScript values in [V8 serialization format]
with Python.

[V8 serialization format]:
  https://h4l.github.io/v8serialize/en/latest/explanation/v8_serialization_format.html

## Examples

These examples demonstrate serializing and deserializing the same selection of
JavaScript values in Python and JavaScript. JavaScript types supported by
JavaScript's [`structuredClone()` algorithm] can be serialized.

[`structuredClone()` algorithm]:
  https://developer.mozilla.org/en-US/docs/Web/API/Web_Workers_API/Structured_clone_algorithm

### Serialize with Python

```python
from base64 import b64encode
from datetime import datetime, UTC
import re

from v8serialize import dumps
from v8serialize.jstypes import JSObject, JSArray, JSUndefined

serialized = dumps(
    [
        "strings 🧵🧶🪡",
        123,
        None,
        JSUndefined,
        JSArray({0: 'a', 1: 'b', 123456789: 'sparse'}),
        JSObject({"msg": "Hi"}),
        b"\xc0\xff\xee",
        2**128,
        {"maps": True},
        {"sets", "yes"},
        re.compile(r"^\w+$"),
        datetime(2024, 1, 1, tzinfo=UTC),
    ]
)

print(b64encode(serialized).decode())
```

**Output**

```
/w9BDFMUc3RyaW5ncyDwn6e18J+ntvCfqqFVezBfYZaa7zpVAFMBYVUBUwFiVZWa7zpTBnNwYXJzZUADlprvOm9TA21zZ1MCSGl7AUIDwP/uWiIAAAAAAAAAAAAAAAAAAAAAATtTBG1hcHNUOgInUwRzZXRzUwN5ZXMsAlJTBV5cdyskgAJEAABAHyXMeEIkAAw=
```

### Deserialize with Python

```python
from base64 import b64decode
from v8serialize import loads

# The output of the JavaScript example
serialized = b64decode(
    "/w9BDGMccwB0AHIAaQBuAGcAcwAgAD7Y9d0+2PbdPtih3kn2ATBfYZaa7zpJACIBYUkCIgFiSaq03nUiBnNwYXJzZUADlprvOm8iA21zZyICSGl7AUIDwP/uWjAAAAAAAAAAAAAAAAAAAAAAAQAAAAAAAAA7IgRtYXBzVDoCJyIDeWVzIgRzZXRzLAJSIgVeXHcrJIACRAAAQB8lzHhCJAAM"
)
print(loads(serialized))
```

**Output**

```python
JSArray([
  'strings 🧵🧶🪡',
  123,
  None,
  JSUndefined,
  JSArray({
    0: 'a',
    1: 'b',
    123456789: 'sparse',
  }),
  JSObject(msg='Hi'),
  JSArrayBuffer(b'\xc0\xff\xee'),
  340282366920938463463374607431768211456,
  JSMap({
    'maps': True,
  }),
  JSSet([
    'yes',
    'sets',
  ]),
  JSRegExp(source='^\\w+$', flags=<JSRegExpFlag.UnicodeSets: 256>),
  datetime.datetime(2024, 1, 1, 0, 0),
])
```

### Serialize with Node.js / Deno

```javascript
import * as v8 from "node:v8";

const sparseArray = ["a", "b"];
sparseArray[123456789] = "sparse";

const buffer = v8.serialize([
  "strings 🧵🧶🪡",
  123,
  null,
  undefined,
  sparseArray,
  { msg: "Hi" },
  Uint8Array.from([0xc0, 0xff, 0xee]).buffer,
  2n ** 128n,
  new Map([["maps", true]]),
  new Set(["yes", "sets"]),
  /^\w+$/v,
  new Date(Date.UTC(2024, 0, 1)),
]);

console.log(buffer.toString("base64"));
```

**Output**

```
/w9BDGMccwB0AHIAaQBuAGcAcwAgAD7Y9d0+2PbdPtih3kn2ATBfYZaa7zpJACIBYUkCIgFiSaq03nUiBnNwYXJzZUADlprvOm8iA21zZyICSGl7AUIDwP/uWjAAAAAAAAAAAAAAAAAAAAAAAQAAAAAAAAA7IgRtYXBzVDoCJyIDeWVzIgRzZXRzLAJSIgVeXHcrJIACRAAAQB8lzHhCJAAM
```

## Deserialize with Node.js / Deno

```javascript
import * as v8 from "node:v8";

// The output of the Python example
const buffer = Buffer.from(
  "/w9BDFMUc3RyaW5ncyDwn6e18J+ntvCfqqFVezBfYZaa7zpVAFMBYVUBUwFiVZWa7zpTBnNwYXJzZUADlprvOm9TA21zZ1MCSGl7AUIDwP/uWiIAAAAAAAAAAAAAAAAAAAAAATtTBG1hcHNUOgInUwN5ZXNTBHNldHMsAlJTBV5cdyskgAJEAABAHyXMeEIkAAw=",
  "base64"
);
console.log(v8.deserialize(buffer));
```

**Output**

```javascript
[
  'strings 🧵🧶🪡',
  123,
  null,
  undefined,
  [ 'a', 'b', <123456787 empty items>, 'sparse' ],
  { msg: 'Hi' },
  ArrayBuffer { [Uint8Contents]: <c0 ff ee>, byteLength: 3 },
  340282366920938463463374607431768211456n,
  Map(1) { 'maps' => true },
  Set(2) { 'yes', 'sets' },
  /^\w+$/v,
  2024-01-01T00:00:00.000Z
]
```
