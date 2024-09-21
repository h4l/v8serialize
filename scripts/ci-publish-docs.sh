#!/usr/bin/env bash
set -xeuo pipefail

cd "$(dirname "${BASH_SOURCE[0]:?}")/.."

built_site_dir="$(pwd)/docs/_site"
gh_pages_dir=$(mktemp -d)
git_head_sha=$(git rev-parse --short HEAD)
publish_prefix_dir=en/latest

if git rev-parse --verify gh-pages >/dev/null 2>&1; then
  git worktree add "${gh_pages_dir:?}" gh-pages
else
  git worktree add "${gh_pages_dir:?}" origin/gh-pages -b gh-pages
fi

scripts/ci-build-docs.sh
cd "${gh_pages_dir:?}"
git rm -r "${publish_prefix_dir:?}"
mkdir -p "$(dirname "${publish_prefix_dir:?}")"
cp -a "${built_site_dir:?}" "${publish_prefix_dir:?}"
git add "${publish_prefix_dir:?}"

if [[ "$(git status --porcelain)" != "" ]]; then
  if ! git config user.email >/dev/null; then
    git config user.email "${GIT_AUTHOR_EMAIL:?}"
  fi
  if ! git config user.name >/dev/null; then
    git config user.name "${GIT_AUTHOR_NAME:?}"
  fi

  git commit -m "docs: update ${publish_prefix_dir@Q} docs built at ${git_head_sha:?}"
  git push origin gh-pages
else
  echo "No changes in ${publish_prefix_dir@Q} after rebuilding docs at ${git_head_sha:?}"
fi

git worktree remove "${gh_pages_dir:?}"
