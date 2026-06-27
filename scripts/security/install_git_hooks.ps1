# Run this once per clone to enable the ATLAS security git hooks:
#   powershell -File scripts/security/install_git_hooks.ps1
#
# This sets core.hooksPath to scripts/security/githooks so `git commit` and
# `git push` run the security gate locally. It is NOT run automatically by
# any agent or CI job -- it changes local git config and must be a deliberate
# step taken by the developer.
$repoRoot = (git rev-parse --show-toplevel)
git -C $repoRoot config core.hooksPath scripts/security/githooks
Write-Host "core.hooksPath set to scripts/security/githooks"
