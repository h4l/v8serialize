# Changelog

All notable changes to v8serialize/echoserver will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

## [0.3.0] - 2024-09-24

### Added

- Container healthcheck — The container image now includes a HEALTHCHECK that
  passes when the server is listening.
  ([#4](https://github.com/h4l/v8serialize/pull/4))

## [0.2.0] - 2024-09-24

### Added

- Server introspection — `GET /` reports supported serialization features and
  software version numbers of the running server.

## [0.1.0] - 2024-08-28

- The first stable release.

[unreleased]:
  https://github.com/h4l/v8serialize/compare/echoserver-v0.3.0...HEAD
[0.3.0]: https://github.com/h4l/v8serialize/releases/tag/echoserver-v0.3.0
[0.2.0]: https://github.com/h4l/v8serialize/releases/tag/echoserver-v0.2.0
[0.1.0]: https://github.com/h4l/v8serialize/releases/tag/echoserver-v0.1.0
