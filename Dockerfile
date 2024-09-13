ARG PYTHON_VER

FROM python:${PYTHON_VER:?} AS python-base


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
