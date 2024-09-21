SHELL := bash
.ONESHELL:
.SHELLFLAGS := -eu -o pipefail -c
.RECIPEPREFIX = >
.DELETE_ON_ERROR:
MAKEFLAGS += --warn-undefined-variables
MAKEFLAGS += --no-builtin-rules

# This should be the first rule so that it runs by default when running `$ make`
# without arguments.
help:
> @echo "Targets:"
> grep -P '^([\w-]+)(?=:)' --only-matching Makefile | sort
.PHONY: default

clean:
> rm -rf dist out
.PHONY: clean

install:
> poetry install
.PHONY: install

test:
> pytest
.PHONY: test

test-cov:
> pytest --cov=v8serialize --cov-report=html
.PHONY: test

out/:
> mkdir out

typecheck:
> @if dmypy status; then
>  dmypy run src test
> else
>   mypy src test
> fi
.PHONY: typecheck

lint: check-code-issues check-code-import-order check-code-format check-misc-file-formatting
.PHONY: lint

check-code-issues:
> ruff check src test
.PHONY: check-code-issues

check-code-format:
> ruff format --check src test
.PHONY: check-code-format

check-misc-file-formatting:
> npx prettier --check .
.PHONY: check-misc-file-formatting

reformat-code:
> @if [[ "$$(git status --porcelain)" != "" ]]; then
>   echo "Refusing to reformat code: files have uncommitted changes" >&2 ; exit 1
> fi
> ruff format src test
.PHONY: reformat-code
