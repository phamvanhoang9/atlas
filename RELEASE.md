# Release Guide

ATLAS releases are GitHub Releases tied to Git tags. Pushing a tag such as `v1.0.0` starts the release workflow in `.github/workflows/release.yml`, which creates a GitHub Release and asks GitHub to generate release notes.

## Choose A Version

Use semantic versioning when possible:

- `v1.0.0` for the first stable release.
- `v1.0.1` for a bug fix.
- `v1.1.0` for backwards-compatible features.
- `v2.0.0` for breaking changes.

## Create And Push A Tag

Make sure your working tree is clean and the code you want to release is already committed on the branch you release from.

```bash
git status
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0
```

After the tag is pushed, GitHub Actions will create the release automatically.

## Download A Release

Users can download stable versions from the repository's GitHub Releases page. GitHub automatically provides source code archives for each release, and maintainers can attach binary or build files later if the project introduces distributable artifacts.

## Security

Do not include real API keys, `.env` files, local `config.json` files, credentials, SQLite databases, caches, or generated reports in a release. Users should copy `.env.example` to `.env` and provide their own API keys locally.
