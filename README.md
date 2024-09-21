<p align="center">
  <img src="docs/v8serialize_logo_auto.svg" width="300" alt="The v8serialize logo. Monochome. Large &quot;V8&quot; and smaller &quot;serialize&quot; in a handwritten style, with the 8 stylized to look like a snake.">
</p>

# `v8serialize`

Read & write JavaScript values in [V8 serialization format] with Python.

[V8 serialization format]:
  https://chromium.googlesource.com/v8/v8/+/refs/heads/main/src/objects/value-serializer.cc

## Byte order/endianness

V8 uses the native byte order when serialising data. This library explicitly
uses little endian. This is because:

- The vast majority of systems using V8 are little endian
- Because the serialized byte order is native, when people use it to store
  persistent data they are probably assuming little-endian systems will read it
  later.
- I don't have a big-endian system or VM to test against

In principle there's no thing to stop prevent adding big endian support though.
