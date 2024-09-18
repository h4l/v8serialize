"""The main public API of v8serialize."""

from __future__ import annotations

from v8serialize._errors import DecodeV8CodecError as DecodeV8CodecError
from v8serialize._errors import JSRegExpV8CodecError as JSRegExpV8CodecError
from v8serialize._errors import (
    UnmappedTagDecodeV8CodecError as UnmappedTagDecodeV8CodecError,
)
from v8serialize._errors import V8CodecError as V8CodecError
from v8serialize._pycompat.typing import Buffer as Buffer
from v8serialize._pycompat.typing import ReadableBinary as ReadableBinary
from v8serialize._references import (
    IllegalCyclicReferenceV8CodecError as IllegalCyclicReferenceV8CodecError,
)
from v8serialize._typing import SparseMutableSequence as SparseMutableSequence
from v8serialize._typing import SparseSequence as SparseSequence
from v8serialize.constants import JSErrorName as JSErrorName
from v8serialize.constants import JSRegExpFlag as JSRegExpFlag
from v8serialize.constants import SerializationFeature as SerializationFeature
from v8serialize.constants import SymbolicVersion as SymbolicVersion
from v8serialize.decode import AnyTagMapper as AnyTagMapper
from v8serialize.decode import Decoder as Decoder
from v8serialize.decode import DeserializeTagFn as DeserializeTagFn
from v8serialize.decode import TagMapper as TagMapper
from v8serialize.decode import TagMapperObject as TagMapperObject
from v8serialize.decode import default_tag_mappers as default_tag_mappers
from v8serialize.decode import loads as loads
from v8serialize.encode import Encoder as Encoder
from v8serialize.encode import EncodeV8CodecError as EncodeV8CodecError
from v8serialize.encode import (
    FeatureNotEnabledEncodeV8CodecError as FeatureNotEnabledEncodeV8CodecError,
)
from v8serialize.encode import (
    UnhandledValueEncodeV8CodecError as UnhandledValueEncodeV8CodecError,
)
from v8serialize.encode import default_encode_steps as default_encode_steps
from v8serialize.encode import dumps as dumps
