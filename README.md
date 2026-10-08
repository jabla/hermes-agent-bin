# hermes-agent-bin

Prebuilt Arch Linux package for [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) — the locally-run AI agent CLI. **Nothing is compiled at install time**: GitHub Actions builds the complete relocatable Python environment once per upstream release and publishes the finished `.pkg.tar.zst`; the AUR `-bin` wrapper just downloads and extracts it.

## Install

```bash
yay -S hermes-agent-bin
```

This replaces the source package `hermes-agent` (they conflict). Installs to
`/opt/hermes-agent` with the `hermes` launcher in `/usr/bin`.

## How it works

- `PKGBUILD` — the *build* recipe, run in CI (archlinux container, non-root
  makepkg, including `check()`). Runs `npm ci` + esbuild (TUI `entry.js`, web `web_dist`) and
  `uv sync --locked` into a venv on Arch's `python` 3.14 (upstream supports
  `>=3.11,<3.15` since v0.21.6). A venv only works on the minor version it was
  built for, so `depends=()` pins `python>=3.14` and `python<3.15`. When Arch
  moves `python` to 3.15, pacman holds that update back (`pacman -Syu` reports
  the conflict) until this package follows: to 3.15 if upstream supports it by
  then, otherwise to a bundled standalone CPython as up to 0.21.5. `package()`
  also writes upstream's `install-stamp.json`, where hermes reads its version
  from since v0.21.6.
- `aur/PKGBUILD` — the AUR *wrapper*, source of truth for
  [hermes-agent-bin on the AUR](https://aur.archlinux.org/packages/hermes-agent-bin).
  Its `source` points at the GitHub Release artifact, stored under a name that
  differs from the package makepkg writes; `package()` only extracts the
  payload (`opt/` and `usr/`).
- `scripts/bump-pkgbuild.py` — bump automation, runs every 2 hours: detects a new upstream
  tag, edits both PKGBUILDs + `.SRCINFO`, opens an auto-merge PR, and reports
  drift from the AUR source package `hermes-agent`.
- `scripts/check-metadata.sh` — fails the build when `PKGBUILD` and
  `aur/PKGBUILD` disagree on version, dependencies, provides or conflicts.
- `.github/workflows/build.yml` — `bump` / `build` / `smoke` / `release` /
  `aur-sync` pipeline.

## Maintenance

- **New upstream release**: the scheduled `bump` job checks every 2 hours, moves `PKGBUILD` to the new tag (tag, commit, source checksum), updates `aur/PKGBUILD` and `.SRCINFO`, and opens an auto-merge PR. A new version starts at `pkgrel=1`; a new tag with an unchanged version gets the next `pkgrel` (otherwise its release tag would already exist); an older version aborts the bump. An open bump PR is updated with `main` on every run, because the ruleset only merges up-to-date branches. The job authenticates with the `BUMP_TOKEN` secret — a fine-grained PAT (Contents + Pull requests: read/write) — because the default `GITHUB_TOKEN` produces a bot-authored PR whose checks need manual approval and whose merge never triggers the release pipeline. The job logs the token identity it used and fails if the secret is missing or rejected; its read-only calls to upstream's API use the workflow token, because unauthenticated calls hit the runners' shared rate limit. The PAT is created without an expiry date, so revocation — not rotation — is the deliberate step: delete it under *Settings > Developer settings > Fine-grained tokens* and `gh secret delete BUMP_TOKEN` here and in `hermes-agent-desktop-bin`.
- **Pipeline**: `build` -> `smoke` -> `release` -> `aur-sync`. The first two also run on pull requests (merge gate): `build` runs `check()`, validates `aur/.SRCINFO` and the metadata of both PKGBUILDs, and builds `aur/PKGBUILD` from the fresh artifact the way AUR users' makepkg does — its payload must match the artifact file for file (paths, modes, links, sha256), and a rebuild must still pass the checksum. `smoke` installs the package in a clean container with the dependencies pacman resolves from its `depends=()` and checks the import, that the venv runs on the system Python, the version and upstream commit `hermes --version` reports, the prebuilt TUI and web bundles and `hermes --help`. `release` and `aur-sync` only run for `main`; `release` tags the built commit and writes notes linking the upstream release and the upstream compare view, and `aur-sync` injects the released artifact's sha256 into `aur/` and pushes to the AUR only while its commit is still `main`'s HEAD. Upstream tag and commit are pinned in `PKGBUILD` (`_pkgver_tag`, `_commit`).
- **Pausing the bump**: `gh variable set BUMP_PAUSED --body true` stops the scheduled bump (for example while a packaging change is in progress), `gh variable delete BUMP_PAUSED` resumes it. A manual dispatch with `bump` still runs while paused.
- **Copies of this repository** (forks, a private CI test repository): the scheduled bump and the AUR push only run in `jabla/hermes-agent-bin`. Elsewhere the bump runs on manual dispatch only and `aur-sync` prints the diff it would push, so pipeline changes can be tested end to end without publishing anything.
- **Upgrading from 0.21.5 or older** (bundled CPython 3.11): pacman removes the old interpreter, but files a root run of hermes created there (bytecode, packages installed into the venv) belong to no package. If pacman warns that a `python3.11` directory under `/opt/hermes-agent` is not empty, remove it: nothing uses it any more.
- **Packaging-only changes** (build steps, launcher, dependencies, the wrapper): bump `pkgrel` in both PKGBUILDs, or the release tag already exists and nothing new is published.
- **Reference package**: `PKGBUILD` follows the AUR source package `hermes-agent` (build steps, launcher and its environment), except for the Python version (the reference uses `python311` from the AUR) and the install stamp. The bump job warns ("Drift from hermes-agent", also in the bump PR) when that PKGBUILD changes beyond its version fields. Review the change in its [AUR history](https://aur.archlinux.org/cgit/aur.git/log/?h=hermes-agent), port what applies, then set `REFERENCE_PKGBUILD_SHA256` in `scripts/bump-pkgbuild.py` to the value the warning prints.
- **AUR wrapper**: only `pkgver`/`pkgrel` are bumped there; its `sha256sums` is the release artifact's, computed after the build by `aur-sync` (a local `makepkg` yields a different hash).
- **hermes-agent-desktop-bin** runs the desktop app on this package's runtime: its launcher points the app at `/opt/hermes-agent/venv/bin/python` and exports the same environment as `/usr/bin/hermes` (`HERMES_DISABLE_LAZY_INSTALLS`, `HERMES_LAZY_INSTALL_TARGET`), and its smoke job installs a pinned release artifact of this repository by its asset name. Changing the install layout, the launcher's exports or the asset names needs the same change there.
- **AUR key**: keep `AUR_SSH_KEY` as a secret of the `aur` environment, with deployment branches limited to `main` — repository secrets are readable by pull requests from branches of this repository. The same key also publishes `hermes-agent-desktop-bin`, and AUR keys can push to every package of the account, so both repositories need the same environment setup.

## License

Repository content: [BSD Zero Clause (0BSD)](LICENSE). The packaged app is MIT (Nous Research).
