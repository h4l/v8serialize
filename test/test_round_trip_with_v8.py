import os
from base64 import b64decode
from dataclasses import dataclass
from typing import Generator, Self

import httpx
import pytest
from hypothesis import given

from v8serialize.decode import loads
from v8serialize.encode import dumps

from .strategies import any_object


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

    def round_trip_serialized_value(self, serialized_value: bytes) -> ReSerializedValue:
        try:
            resp = self.httpclient.post(
                self.server_url,
                content=serialized_value,
                headers={"content-type": "application/x-v8-serialized"},
            )
            if (
                resp.status_code == 400
                and "Unable to deserialize V8-serialized data" in resp.text
            ):
                raise DeserializationError(
                    f"V8 serialization echo server was unable to deserialize "
                    f"our data: {resp.text}",
                    serialized_value,
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
            return ReSerializedValue.from_echo_result_json(echo_result)
        except Exception as e:
            raise RuntimeError(
                f"Failed to parse serialization echo response: {e}"
            ) from e


@pytest.fixture(scope="session")
def httpclient() -> Generator[httpx.Client, None, None]:
    with httpx.Client() as client:
        yield client


@pytest.fixture(autouse=True, scope="session")
def check_v8_echoserver(httpclient: httpx.Client) -> None:
    try:
        resp = httpclient.get("http://localhost:8000/")
        resp.raise_for_status
    except httpx.HTTPError as e:
        raise RuntimeError(f"V8 echo server is not contactable: {e}") from e


@pytest.fixture(scope="session")
def server_url() -> httpx.URL:
    raw_url = os.environ.get("V8CODEC_V8_ECHO_SERVER_URL") or "http://localhost:8000/"
    try:
        return httpx.URL(raw_url)
    except Exception as e:
        raise RuntimeError(
            f"V8CODEC_V8_ECHO_SERVER_URL envar is not a valid URL. "
            f"V8CODEC_V8_ECHO_SERVER_URL={raw_url!r}, error={e}"
        )


@pytest.fixture(scope="session")
def echoclient(
    httpclient: httpx.Client, server_url: httpx.URL
) -> V8SerializationEchoServerClient:
    return V8SerializationEchoServerClient(httpclient, server_url)


@given(start_value=any_object(allow_theoretical=False))
def test_codec_rt_object(
    start_value: object, echoclient: V8SerializationEchoServerClient
) -> None:
    our_serialized_value = dumps(start_value)
    v8_result = echoclient.round_trip_serialized_value(our_serialized_value)
    round_tripped_value = loads(v8_result.reserialized_value)

    if start_value != round_tripped_value:
        print(f"start_value: {start_value!r}")
        print(f"Echo server interpretation: {v8_result.interpretation}")
    assert start_value == round_tripped_value
