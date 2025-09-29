ARG QUARTO_VERSION=1.8.24


FROM scratch AS quarto-linux-deb
ARG QUARTO_VERSION TARGETARCH

# URL from # https://quarto.org/docs/download/
ADD https://github.com/quarto-dev/quarto-cli/releases/download/v${QUARTO_VERSION:?}/quarto-${QUARTO_VERSION:?}-linux-${TARGETARCH:?}.deb .


FROM scratch AS deno-install-sh
ADD https://deno.land/install.sh .


FROM mcr.microsoft.com/devcontainers/python:3.12-bookworm AS devcontainer-base
ENV DENO_INSTALL=/opt/deno


FROM devcontainer-base AS devcontainer-deno

RUN --mount=from=deno-install-sh,source=install.sh,target=/tmp/install.sh \
  sh /tmp/install.sh --yes --no-modify-path


FROM devcontainer-base AS devcontainer

# We use direnv to dynamically set envars for docker compose
RUN apt-get update && apt-get install direnv \
  && printf '\n%s\n' 'eval "$(direnv hook bash)"' >> /etc/bash.bashrc

# Install quarto, which we use to build the documentation. Quarto is an
# open-source scientific and technical publishing system built on Pandoc.
RUN --mount=from=quarto-linux-deb,target=/debfiles dpkg -i /debfiles/quarto-*.deb

ENV PATH=${PATH:?}:${DENO_INSTALL:?}/bin
COPY --chown=vscode:vscode --from=devcontainer-deno ${DENO_INSTALL:?} ${DENO_INSTALL:?}
