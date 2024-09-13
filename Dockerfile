ARG PYTHON_VER

FROM python:${PYTHON_VER:?} AS python-base
ENV PIP_DISABLE_PIP_VERSION_CHECK=1


FROM python-base AS poetry
RUN --mount=type=cache,target=/root/.cache pip install poetry
RUN python -m venv /venv
ENV VIRTUAL_ENV=/venv \
    PATH="/venv/bin:$PATH"
RUN poetry config virtualenvs.create false
WORKDIR /workspace
COPY pyproject.toml poetry.lock /workspace/

# Poetry needs these to exist to setup the editable install
RUN mkdir -p src/v8serialize && touch src/v8serialize/__init__.py README.md
RUN --mount=type=cache,target=/root/.cache poetry install


FROM poetry AS test
RUN --mount=source=.,target=/workspace,rw \
    --mount=type=cache,uid=1000,target=.pytest_cache \
    --mount=type=cache,uid=1000,target=.hypothesis \
    pytest


FROM poetry AS lint-setup
# invalidate cache so that the lint tasks run. We use no-cache-filter here but
# not on the lint-* tasks so that the tasks can mount cache dirs themselves.
RUN touch .now


FROM lint-setup AS lint-flake8
RUN --mount=source=.,target=/workspace,rw \
    flake8


FROM lint-setup AS lint-black
RUN --mount=source=.,target=/workspace,rw \
    poetry run black --check --diff .


FROM lint-setup AS lint-isort
RUN --mount=source=.,target=/workspace,rw \
    poetry run isort --check --diff .


FROM lint-setup AS lint-mypy
RUN --mount=source=.,target=/workspace,rw \
    --mount=type=cache,target=.mypy_cache \
    poetry run mypy .


FROM poetry AS smoketest-pkg-build
RUN --mount=source=testing/smoketest,target=.,rw \
  mkdir /dist && poetry build -o /dist


FROM scratch AS smoketest-pkg
COPY --from=smoketest-pkg-build /dist/* .


FROM poetry AS v8serialize-pkg-build
RUN --mount=source=.,target=/workspace,rw \
  mkdir /dist && poetry build -o /dist


FROM scratch AS v8serialize-pkg
COPY --from=v8serialize-pkg-build /dist/* .


FROM python-base AS test-package
RUN python -m venv /env
ENV PATH=/env/bin:$PATH
RUN --mount=from=smoketest-pkg,target=/pkg/smoketest \
    --mount=from=v8serialize-pkg,target=/pkg/v8serialize \
  pip install /pkg/smoketest/*.whl /pkg/v8serialize/*.whl
RUN pip list
RUN python -m smoketest
