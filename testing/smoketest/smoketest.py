from v8serialize import SerializationFeature, dumps, loads


def main() -> None:
    msg = "Don't let the smoke out!"
    msg_out = loads(
        dumps(
            "Don't let the smoke out!",
            v8_version=SerializationFeature.MaxCompatibility.first_v8_version,
        )
    )
    if msg != msg_out:
        raise AssertionError("Smoke test failed")
    print(msg_out)


if __name__ == "__main__":
    main()
