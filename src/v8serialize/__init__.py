"""The main public API of v8serialize."""

from __future__ import annotations

from v8serialize._errors import DecodeV8SerializeError as DecodeV8SerializeError
from v8serialize._errors import EncodeV8SerializeError as EncodeV8SerializeError
from v8serialize._errors import (
    FeatureNotEnabledEncodeV8SerializeError as FeatureNotEnabledEncodeV8SerializeError,
)
from v8serialize._errors import JSRegExpV8SerializeError as JSRegExpV8SerializeError
from v8serialize._errors import (
    UnhandledTagDecodeV8SerializeError as UnhandledTagDecodeV8SerializeError,
)
from v8serialize._errors import (
    UnhandledValueEncodeV8SerializeError as UnhandledValueEncodeV8SerializeError,
)
from v8serialize._errors import V8SerializeError as V8SerializeError
from v8serialize._pycompat.typing import Buffer as Buffer
from v8serialize._pycompat.typing import BufferSequence as BufferSequence
from v8serialize._pycompat.typing import ReadableBinary as ReadableBinary
from v8serialize._references import (
    IllegalCyclicReferenceV8SerializeError as IllegalCyclicReferenceV8SerializeError,
)
from v8serialize._typing import SparseMutableSequence as SparseMutableSequence
from v8serialize._typing import SparseSequence as SparseSequence
from v8serialize.constants import JSErrorName as JSErrorName
from v8serialize.constants import JSRegExpFlag as JSRegExpFlag
from v8serialize.constants import SerializationFeature as SerializationFeature
from v8serialize.constants import SymbolicVersion as SymbolicVersion
from v8serialize.decode import Decoder as Decoder
from v8serialize.decode import DecodeStep as DecodeStep
from v8serialize.decode import DecodeStepFn as DecodeStepFn
from v8serialize.decode import DecodeStepObject as DecodeStepObject
from v8serialize.decode import TagReader as TagReader
from v8serialize.decode import default_decode_steps as default_decode_steps
from v8serialize.decode import loads as loads
from v8serialize.encode import Encoder as Encoder
from v8serialize.encode import default_encode_steps as default_encode_steps
from v8serialize.encode import dumps as dumps
