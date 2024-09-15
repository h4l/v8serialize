from __future__ import annotations

import json
import os
import subprocess
import warnings
from base64 import b64decode
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final
from typing_extensions import Generator, Self

import httpx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from packaging.version import InvalidVersion, Version

from v8serialize._pycompat.enum import StrEnum
from v8serialize._versions import parse_lenient_version
from v8serialize.constants import SerializationFeature
from v8serialize.decode import AnyTagMapper, TagMapper, loads
from v8serialize.encode import DefaultEncodeContext, ObjectMapper, WritableTagStream
from v8serialize.extensions import node_js_array_buffer_view_host_object_handler

from .strategies import any_object

if TYPE_CHECKING:
    # not exported publicly :/
    from _pytest.mark import ParameterSet

pytestmark = pytest.mark.integration

MIN_ECHOSERVER_VERSION: Final = Version("0.2.0")


def get_echoserver_urls() -> Mapping[str, httpx.URL]:
    value = os.environ.get("V8SERIALIZE_ECHOSERVERS")

    if not value:
        return {}

    if value.lstrip().startswith("{"):
        return parse_echoserver_urls(value)

    if value == "scripts/list-echoservers.sh":
        script_path = Path(__file__).parent.parent / value
        try:
            output = subprocess.check_output(script_path)
        except subprocess.CalledProcessError as e:
            raise ValueError(
                f"Failed to run {value!r} to find available echoservers "
                "(see pytest captured stderr for output)"
            ) from e
        return parse_echoserver_urls(output.decode())

    raise ValueError(
        f"Unable to list available echoservers: V8SERIALIZE_ECHOSERVERS is not "
        f"a recognised value: {value!r}"
    )


def parse_echoserver_urls(raw_urls_json: str | None = None) -> Mapping[str, httpx.URL]:
    if not raw_urls_json:
        return {}
    try:
        raw_urls = json.loads(raw_urls_json)
    except ValueError as e:
        raise ValueError(f"V8SERIALIZE_ECHOSERVERS envar is not valid JSON: {e}") from e

    if not isinstance(raw_urls, dict):
        raise ValueError(
            f"V8SERIALIZE_ECHOSERVERS value does not contain "
            f"an object/dict of URLs: {raw_urls!r}"
        )
    try:
        return {name: httpx.URL(raw_url) for name, raw_url in raw_urls.items()}
    except ValueError as e:
        raise ValueError(
            f"V8SERIALIZE_ECHOSERVERS value contains an invalid URL: {e}"
        ) from e


def get_get_echoserver_urls_as_params() -> Sequence[ParameterSet]:
    return [pytest.param(url, id=name) for name, url in get_echoserver_urls().items()]


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
    echoserver: EchoServer

    def round_trip_serialized_value(
        self, serialized_value: bytes
    ) -> ReSerializedValue | ReSerializationError:
        try:
            resp = self.httpclient.post(
                self.echoserver.server_url,
                content=serialized_value,
                headers={"content-type": "application/x-v8-serialized"},
            )
            resp.raise_for_status()
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


@dataclass
class EchoServer:
    server_url: httpx.URL
    meta: EchoServerMeta

    @property
    def v8_version(self) -> Version:
        try:
            return self.meta.versions["v8"]
        except KeyError as e:
            raise LookupError("echoserver meta has no 'v8' version") from e

    @property
    def supported_features(self) -> SerializationFeature:
        features = SerializationFeature.MaxCompatibility
        for feature, is_supported in self.meta.supported_serialization_features.items():
            if is_supported:
                features |= feature
        return features

    def __repr__(self) -> str:
        return (
            f"<EchoServer "
            f"server_url={self.server_url} "
            f"v8_version={self.v8_version} "
            f"supported_features={self.supported_features!r}"
            ">"
        )


@dataclass
class EchoServerMeta:
    name: str
    server_version: Version
    versions: Mapping[str, Version]
    supported_serialization_features: Mapping[SerializationFeature, bool]

    @classmethod
    def from_json_object(cls, value: object) -> Self:
        if not isinstance(value, dict):
            raise ValueError("value is not a dict")

        name = value.get("name")
        if not isinstance(name, str):
            raise ValueError('"name" is not a string')

        raw_server_version = value.get("serverVersion")
        if not isinstance(raw_server_version, str):
            raise ValueError('"serverVersion is not a string')
        try:
            server_version = Version(raw_server_version)
        except InvalidVersion as e:
            raise ValueError(f'"serverVersion" is not a valid version: {e}') from e

        def parse_version(name: str, value: object) -> Version:
            err: str | InvalidVersion | None = None
            if not isinstance(value, str):
                err = f"value is not a string: {value!r}"
            else:
                try:
                    return parse_lenient_version(value)
                except InvalidVersion as e:
                    err = e
            raise ValueError(f"versions[{name!r}] is not a valid version: {err}")

        raw_versions = value.get("versions")
        if not isinstance(raw_versions, dict):
            raise ValueError(f'"versions" is not an object: {raw_versions}')
        versions = {n: parse_version(n, v) for n, v in raw_versions.items()}

        raw_features = value.get("supportedSerializationFeatures")
        if not isinstance(raw_features, dict):
            raise ValueError(
                f'"supportedSerializationFeatures" is not an object: {raw_features}'
            )

        def parse_feature(
            name: str, value: object
        ) -> tuple[SerializationFeature, bool] | None:
            if not isinstance(value, bool):
                raise ValueError(
                    f"['supportedSerializationFeatures'][{name!r}] "
                    f"is not a boolean: {value!r}"
                )
            try:
                return SerializationFeature.for_name(name), bool(value)
            except ValueError:
                warnings.warn(UnknownSerializationFeature(name), stacklevel=1)
                return None

        supported_serialization_features = {
            item[0]: item[1]
            for item in (parse_feature(n, v) for n, v in raw_features.items())
            if item is not None
        }

        return cls(
            name=name,
            server_version=server_version,
            versions=versions,
            supported_serialization_features=supported_serialization_features,
        )


class UnknownSerializationFeature(UserWarning):
    pass


@pytest.fixture(params=get_get_echoserver_urls_as_params(), scope="session")
def echoserver_url(request: pytest.FixtureRequest) -> httpx.URL:
    assert isinstance(request.param, httpx.URL)
    return request.param


@pytest.fixture(scope="session")
def httpclient() -> Generator[httpx.Client]:
    with httpx.Client() as client:
        yield client


@pytest.fixture(scope="session")
def echoserver(httpclient: httpx.Client, echoserver_url: httpx.URL) -> EchoServer:
    try:
        resp = httpclient.get(echoserver_url)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise RuntimeError(f"V8 echo server is not contactable: {e}") from e

    try:
        meta = EchoServerMeta.from_json_object(resp.json())
    except Exception as e:
        raise RuntimeError(
            f"Unable to read metadata from V8 echoserver {echoserver_url}: {e}"
        ) from e

    if meta.server_version < MIN_ECHOSERVER_VERSION:
        pytest.skip(
            f"Server {echoserver_url} version {meta.server_version} is less "
            f"than the MIN_ECHOSERVER_VERSION {MIN_ECHOSERVER_VERSION}",
            allow_module_level=True,
        )

    echoserver = EchoServer(server_url=echoserver_url, meta=meta)
    print(echoserver)
    return echoserver


@pytest.fixture(scope="session")
def echoclient(
    httpclient: httpx.Client, echoserver: EchoServer
) -> V8SerializationEchoServerClient:
    return V8SerializationEchoServerClient(httpclient=httpclient, echoserver=echoserver)


@pytest.fixture(scope="session", params=["max-features", "min-features"])
def enabled_features(
    echoserver: EchoServer, request: pytest.FixtureRequest
) -> SerializationFeature:
    supported_features = echoserver.supported_features
    if request.param == "max-features":
        if supported_features == SerializationFeature.MaxCompatibility:
            pytest.skip(
                "Server supports no features above baseline, no features to enable."
            )
        return supported_features
    assert request.param == "min-features"
    return SerializationFeature.MaxCompatibility


# TODO: also test with serialize_object_references (default_object_mappers)
object_mappers = [ObjectMapper()]
tag_mappers: Sequence[AnyTagMapper] = [
    TagMapper(host_object_deserializer=node_js_array_buffer_view_host_object_handler)
]


def get_any_object_strategy(
    supported_features: SerializationFeature,
) -> st.SearchStrategy[object]:
    return any_object(
        allow_theoretical=False, max_leaves=10, features=supported_features
    )


@settings(max_examples=1000, deadline=1000)
@given(data=st.data())
def test_codec_rt_object(
    data: st.DataObject,
    echoclient: V8SerializationEchoServerClient,
    enabled_features: SerializationFeature,
) -> None:
    start_value = data.draw(get_any_object_strategy(enabled_features))

    # TODO: support feature flags in dumps()
    encode_ctx = DefaultEncodeContext(
        object_mappers=object_mappers,
        stream=WritableTagStream(features=enabled_features),
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
