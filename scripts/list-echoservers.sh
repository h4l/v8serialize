#!/usr/bin/env bash
set -euo pipefail

# Output a JSON object listing URLs of running echoserver containers
#
# e.g. '{"echoserver-node-18":"http://v8serialize-echoserver-node-18:8000/"}'
#
# Containers must be labelled as indicated by --filter.
docker container ls \
  --filter=label=com.github.h4l.v8serialize.echoserver=true \
  --format=json \
  | jq -sce '[
    .[]
    | (.Names | (capture("^v8serialize-(?<name>.*)$") | .name) // .) as $name
    | "http://\(.Names):8000/" as $url
    | { key: $name, value: $url }
  ] | from_entries'
