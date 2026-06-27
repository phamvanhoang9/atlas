#!/bin/sh
# Run this once per clone to enable the ATLAS security git hooks:
#   sh scripts/security/install_git_hooks.sh
#
# This sets core.hooksPath to scripts/security/githooks so `git commit` and
# `git push` run the security gate locally. It is NOT run automatically by
# any agent or CI job -- it changes local git config and must be a deliberate
# step taken by the developer.
set -e
REPO_ROOT="$(git rev-parse --show-toplevel)"
git -C "$REPO_ROOT" config core.hooksPath scripts/security/githooks
echo "core.hooksPath set to scripts/security/githooks"
