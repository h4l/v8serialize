from __future__ import annotations

from base64 import b64decode
from dataclasses import dataclass
from enum import Enum, StrEnum, auto
from typing import Generator, Self, Sequence

import httpx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from packaging.version import Version

from v8serialize.constants import SerializationFeature
from v8serialize.decode import AnyTagMapper, TagMapper, loads
from v8serialize.encode import (
    DefaultEncodeContext,
    Encoder,
    ObjectMapper,
    WritableTagStream,
    dumps,
)
from v8serialize.extensions import node_js_array_buffer_view_host_object_handler

from .strategies import any_object


class V8Target(Enum):
    Node18 = auto()
    Node22 = auto()
    Deno1_46 = auto()


@dataclass
class ReSerializationError:
    name: ReSerializationErrorName
    message: str
    interpretation: str | None

    @classmethod
    def from_echo_result_json(cls, data: dict[object, object]) -> Self:
        error_data = data.get("error")
        if not isinstance(error_data, dict):
            raise ValueError('"error" is not a dict')
        raw_name = error_data.get("name")
        if not (isinstance(raw_name, str) and raw_name in ReSerializationErrorName):
            raise ValueError(
                f'"error" "name" is not one of {ReSerializationErrorName}: {raw_name!r}'
            )
        name = ReSerializationErrorName(raw_name)
        interpretation = error_data.get("interpretation")
        if not (interpretation is None or isinstance(interpretation, str)):
            raise ValueError(
                f'"error" "interpretation" is not a string: {interpretation!r}'
            )
        message = error_data.get("message")
        if not isinstance(message, str):
            raise ValueError(f'"error" "message" is not a string: {message!r}')

        return cls(name=name, message=message, interpretation=interpretation)


class ReSerializationErrorName(StrEnum):
    Deserialize = "deserialize-failed"
    Serialize = "serialize-failed"


@dataclass
class ReSerializedValue:
    interpretation: str
    reserialized_value: bytes

    @classmethod
    def from_echo_result_json(cls, data: dict[object, object]) -> Self:
        interpretation = data.get("interpretation")
        if not isinstance(interpretation, str):
            raise ValueError('"interpretation" is not a string')
        serialization = data.get("serialization")
        if not isinstance(serialization, dict):
            raise ValueError('"serialization" is not a dict')
        if serialization.get("encoding") != "base64":
            raise ValueError('"serialization" "encoding" is not a base64')
        raw_data = serialization.get("data")
        if not isinstance(raw_data, str):
            raise ValueError('"Serialization" "data" is not a string')
        try:
            reserialized_value = b64decode(raw_data)
        except Exception as e:
            raise ValueError(
                f'"Serialization" "data" is not a valid base64 string: {e}'
            ) from e
        return cls(interpretation=interpretation, reserialized_value=reserialized_value)


@dataclass
class DeserializationError(ValueError):
    message: str
    serialized_value: bytes

    def __init__(self, message: str, serialized_value: bytes) -> None:
        super().__init__(message)
        self.message = message
        self.serialized_value = serialized_value


@dataclass
class V8SerializationEchoServerClient:
    httpclient: httpx.Client
    server_url: httpx.URL
    v8_version: Version

    def round_trip_serialized_value(
        self, serialized_value: bytes
    ) -> ReSerializedValue | ReSerializationError:
        try:
            resp = self.httpclient.post(
                self.server_url,
                content=serialized_value,
                headers={"content-type": "application/x-v8-serialized"},
            )
            resp.raise_for_status
        except httpx.HTTPError as e:
            raise RuntimeError(
                f"Failed to get serialization echo response from server: {e}"
            ) from e

        try:
            echo_result = resp.json()
            if not isinstance(echo_result, dict):
                raise ValueError("JSON body is not a dict")
            if echo_result.get("success"):
                return ReSerializedValue.from_echo_result_json(echo_result)
            else:
                return ReSerializationError.from_echo_result_json(echo_result)
        except Exception as e:
            raise RuntimeError(
                f"Failed to parse serialization echo response: {e}"
            ) from e


@pytest.fixture(scope="session")
def httpclient() -> Generator[httpx.Client, None, None]:
    with httpx.Client() as client:
        yield client


@pytest.fixture(autouse=True, scope="session")
def check_v8_echoserver(httpclient: httpx.Client, server_meta: EchoServerMeta) -> None:
    try:
        resp = httpclient.get(server_meta.server_url)
        resp.raise_for_status
    except httpx.HTTPError as e:
        raise RuntimeError(f"V8 echo server is not contactable: {e}") from e


@dataclass
class EchoServerMeta:
    server_url: httpx.URL
    v8_version: Version
    extra_features: SerializationFeature


@pytest.fixture(
    scope="session",
    params=[
        pytest.param(
            (
                "http://v8serialize-echoserver-deno:8000/",
                "12.9.202",
                SerializationFeature.Float16Array,
            ),
            id="deno",
        ),
        pytest.param(
            ("http://v8serialize-echoserver-node-22:8000/", "12.4.254", None),
            id="node-22",
        ),
        pytest.param(
            ("http://v8serialize-echoserver-node-18:8000/", "10.2.154", None),
            id="node-18",
        ),
    ],
)
def server_meta(request: pytest.FixtureRequest) -> EchoServerMeta:
    # raw_url = os.environ.get("V8CODEC_V8_ECHO_SERVER_URL") or "http://localhost:8000/"
    raw_url, raw_version, extra_features = request.param
    try:
        return EchoServerMeta(
            server_url=httpx.URL(raw_url),
            v8_version=Version(raw_version),
            extra_features=SerializationFeature(extra_features or 0),
        )
    except Exception as e:
        raise
        # FIXME:
        # raise RuntimeError(
        #     f"V8CODEC_V8_ECHO_SERVER_URL envar is not a valid URL. "
        #     f"V8CODEC_V8_ECHO_SERVER_URL={raw_url!r}, error={e}"
        # )


@pytest.fixture(scope="session")
def echoclient(
    httpclient: httpx.Client, server_meta: EchoServerMeta
) -> V8SerializationEchoServerClient:
    return V8SerializationEchoServerClient(
        httpclient=httpclient,
        server_url=server_meta.server_url,
        v8_version=server_meta.v8_version,
    )


@pytest.fixture(scope="session")
def features(server_meta: EchoServerMeta) -> SerializationFeature:
    """The serialization features supported by the server's V8 version."""
    assert (
        server_meta.v8_version >= SerializationFeature.MaxCompatibility.first_v8_version
    )

    features = SerializationFeature.MaxCompatibility | server_meta.extra_features
    for feature in SerializationFeature:
        if feature.first_v8_version <= server_meta.v8_version:
            features |= feature

    return features


# TODO: also test with serialize_object_references (default_object_mappers)
object_mappers = [ObjectMapper()]
tag_mappers: Sequence[AnyTagMapper] = [
    TagMapper(host_object_deserializer=node_js_array_buffer_view_host_object_handler)
]
# @pytest.mark.parametrize("object_mappers", [[ObjectMapper()]])


def get_any_object_strategy_for_v8target(
    features: SerializationFeature,
) -> st.SearchStrategy[object]:
    return any_object(allow_theoretical=False, max_leaves=10, features=features)


@settings(max_examples=1000, deadline=1000)
@given(data=st.data())
def test_codec_rt_object(
    data: st.DataObject,
    echoclient: V8SerializationEchoServerClient,
    features: SerializationFeature,
) -> None:
    start_value = data.draw(get_any_object_strategy_for_v8target(features))

    # TODO: support feature flags in dumps()
    encode_ctx = DefaultEncodeContext(
        object_mappers=object_mappers, stream=WritableTagStream(features=features)
    )
    encode_ctx.stream.write_header()
    encode_ctx.encode_object(start_value)
    our_serialized_value = bytes(encode_ctx.stream.data)

    v8_result = echoclient.round_trip_serialized_value(our_serialized_value)
    assert isinstance(v8_result, ReSerializedValue)
    round_tripped_value = loads(v8_result.reserialized_value, tag_mappers=tag_mappers)

    if start_value != round_tripped_value:
        print(f"start_value: {start_value!r}")
        print(f"Echo server interpretation: {v8_result.interpretation}")
    assert start_value == round_tripped_value
