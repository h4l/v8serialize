import re

from v8serialize.constants import JSRegExpFlag
from v8serialize.decode import DefaultDecodeContext
from v8serialize.encode import DefaultEncodeContext, ObjectMapper
from v8serialize.jstypes import JSRegExp


def test_python_re_pattern() -> None:
    encode_ctx = DefaultEncodeContext([ObjectMapper()])

    re_pattern = re.compile("[a-z].*", re.DOTALL | re.IGNORECASE | re.ASCII)
    encode_ctx.serialize(re_pattern)

    decode_ctx = DefaultDecodeContext(data=encode_ctx.stream.data)
    regexp = decode_ctx.decode_object()

    assert regexp == JSRegExp("[a-z].*", JSRegExpFlag.DotAll | JSRegExpFlag.IgnoreCase)
