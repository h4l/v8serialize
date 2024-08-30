ARG DENO_VERSION NODE_VERSION DNT_NODE_VERSION DNT_DENO_VERSION

FROM denoland/deno:${DENO_VERSION:-alpine} AS echoserver-deno

COPY main.ts .
USER deno

ENV V8SERIALIZE_LOG_WITH_COLOR=true \
    V8SERIALIZE_LOG_LISTEN=true \
    V8SERIALIZE_LOG_RE_SERIALIZATION=text \
    V8SERIALIZE_PORT=8000 \
    V8SERIALIZE_HOSTNAME=0.0.0.0

EXPOSE 8000

CMD ["run", "--no-remote", "--allow-net", "--allow-env", "main.ts"]


FROM denoland/deno:bin-${DNT_DENO_VERSION:-latest} AS dnt-deno


FROM node:${DNT_NODE_VERSION:-latest} AS npm-package

COPY --from=dnt-deno /deno /usr/local/bin/deno

WORKDIR /build

COPY . ./
RUN deno -A scripts/build_npm.ts
RUN npm pack ./npm


FROM node:${NODE_VERSION:-alpine} AS echoserver-node
ARG ECHOSERVER_VERSION

RUN apk add --no-cache tini
WORKDIR /app

RUN --mount=from=npm-package,source=/build/,target=/build/ \
  npm install "/build/v8serialize-echoserver-${ECHOSERVER_VERSION:?}.tgz"

ENV V8SERIALIZE_LOG_WITH_COLOR=true \
    V8SERIALIZE_LOG_LISTEN=true \
    V8SERIALIZE_LOG_RE_SERIALIZATION=text \
    V8SERIALIZE_PORT=8000 \
    V8SERIALIZE_HOSTNAME=0.0.0.0

EXPOSE 8000
USER node

ENTRYPOINT ["/sbin/tini", "--", "docker-entrypoint.sh"]
CMD ["-e", "require('v8serialize-echoserver').main()"]
