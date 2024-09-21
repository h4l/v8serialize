#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]:?}")/../docs"

rm -rf _site
quartodoc interlinks
quartodoc build
quarto render
