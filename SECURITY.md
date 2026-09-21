# Security

## Scope

This repository contains packaging automation for the upstream Hermes Agent
CLI:

- `PKGBUILD` / `aur/PKGBUILD` — recipes, no application code
- `.github/workflows/build.yml` — CI pipeline (bump, build, smoke, release,
  aur-sync)
- `scripts/` — bump automation and the metadata check

The packaged application itself lives at
https://github.com/NousResearch/hermes-agent — report application
vulnerabilities there.

## Supply-chain notes

- Builds run in a fresh `archlinux:latest` container per run; the base image
  is not pinned to a digest (rolling distro).
- The package bundles a standalone CPython 3.11 that `uv python install`
  downloads in the build; uv checks it against the checksums it ships, so the
  interpreter follows the container's `uv` version. Python dependencies come
  from upstream's `uv.lock` (`uv sync --locked`), Node dependencies from its
  `package-lock.json` (`npm ci --ignore-scripts`).
- GitHub Actions are pinned to commit SHAs (official `actions/*`), kept current by Dependabot (weekly, grouped).
- The `AUR_SSH_KEY` secret is used only by the `aur-sync` job; `release` and
  `aur-sync` run exclusively for `main` (push or manual dispatch on `main`),
  never on pull requests or other branches. The key belongs in the `aur`
  environment with deployment branches limited to `main`: pull requests from
  branches of this repository can read repository-level secrets, environment
  secrets they cannot. AUR keys are not per package: the key can push to every
  package of the AUR account, and `hermes-agent-desktop-bin` publishes with the
  same key, so both repositories must protect it the same way.
- `PKGBUILD` follows the AUR source package `hermes-agent` after review; the
  bump job only reports drift from it and never copies anything automatically.
- `hermes-agent-desktop-bin`'s smoke job installs a pinned release artifact of
  this repository (version and sha256 hard-coded there, verified before
  install).
- `main` is protected: pull requests required, `build` + `smoke` checks
  mandatory, force-push blocked.

## Reporting

To report a security issue in this repository's automation, open a private
vulnerability report via GitHub: *Security → Report a vulnerability* (or
contact the maintainer through the AUR package page).
