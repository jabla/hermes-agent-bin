# hermes-agent-bin

Prebuilt Arch Linux package for [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) — the locally-run AI agent CLI. **Nothing is compiled at install time**: GitHub Actions builds the complete relocatable Python environment once per upstream release and publishes the finished `.pkg.tar.zst`; the AUR `-bin` wrapper just downloads and extracts it.

## Install

```bash
yay -S hermes-agent-bin
```

This replaces the source package `hermes-agent` (they conflict). It provides
`hermes-agent` with its version, so packages that need a minimum version
(`hermes-agent>=<version>`, like the desktop apps) accept it. Installs to
`/opt/hermes-agent` with the `hermes` launcher in `/usr/bin`.

### Browser tools

The browser tools drive a Chromium through `agent-browser`. Either use a
system browser:

```bash
yay -S agent-browser-bin chromium   # or google-chrome / brave-bin
```

`/usr/bin/hermes` points the tools at the first of `google-chrome-stable`,
`google-chrome`, `chromium` and `brave` on `PATH` (`AGENT_BROWSER_EXECUTABLE_PATH`;
set it yourself to pick another). Or let hermes fetch its pinned agent-browser
and Chromium into `~/.hermes/tools`, once per user:

```bash
hermes pm install agent-browser
```

A system browser wins over pm's Chromium; an empty
`AGENT_BROWSER_EXECUTABLE_PATH=` keeps pm's. Processes started without
`/usr/bin/hermes`, like the gateway service, get the same pick from the venv
itself (`hermes_agent_bin_env.py`). Since 0.22.4 that service also runs the
CLI, TUI and desktop sessions. `~/.hermes/.env` wins over both.

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
  from since v0.21.6. It compiles every module to bytecode (checked-hash
  `.pyc`): users cannot write `__pycache__` into the root-owned `/opt`, so
  without it each start compiles hermes again (`hermes --help` 1.15 s instead
  of 0.46 s). A `.py` edited in place still wins over its shipped `.pyc`.
  Lazy installs are off for the root-owned venv, so it
  ships the extras users commonly need beyond `all` and `messaging`, as the
  reference package does: `anthropic`, `edge-tts` (default TTS), `ddgs` (free
  web search), `doc-extract` and the gateways feishu, matrix, dingtalk, wecom,
  teams and google-chat.
- `system-tools.py` — run by `package()`: builds `/opt/hermes-agent/system-store`,
  a store for upstream's package manager (pm) whose required tools (node, npm,
  ffmpeg, ripgrep, python, uv) are symlinks into `/usr/bin` under the pins of
  `pm/lock.json`. Since v0.21.6 hermes resolves these tools only through pm
  and never takes a PATH copy: without such a store the TUI and npx/uvx MCP
  servers fail (lazy installs are off), and a partial per-user store in
  `~/.hermes/tools` makes every start warn "install out of sync". Optional
  tools (browser, ...) still go to `~/.hermes/tools`. pm puts the node and
  npm entries first on PATH for every process hermes starts, so its children
  run the system node and npm even when the user's PATH prefers nvm or volta
  (upstream's store-first design). If upstream's set of required tools changes,
  the build stops until `TOOLS` in the script is updated.
  The store runs Arch's `uv`, so `depends=()` asks for at least the uv
  version `pm/lock.json` pins (`_uvmin`): enabling a plugin with Python
  dependencies re-resolves upstream's `uv.lock`, which an older uv can fail
  (uv 0.13.4 on v0.22.5, NousResearch/hermes-agent#143254). `check()` stops
  when upstream moves the pin.
- `keep-venv-interpreter.patch` — applied in `prepare()`. Upstream runs its
  child processes and service units on a python from the pm store when the
  store has one, without the venv; the patch keeps them on the venv for this
  pacman-managed tree. `patch --fuzz=0` stops the build when upstream changes
  the lines around it; a new place that reads the store python does not, so
  `smoke` checks where the child command, the installation command, cron
  scripts and the gateway unit end up.
- `release-date-from-stamp.patch` — applied in `prepare()`: the `hermes_cli/__init__.py`
  part of upstream's draft fix
  [#135223](https://github.com/NousResearch/hermes-agent/pull/135223). Since the
  switch to tag-based releases upstream no longer bumps `__release_date__`, so
  `hermes --version` and the banners show 2026.9.24 for every release. The patch
  dates them from the stamp's `commitDate` (the tagged commit); `smoke` checks the
  date `hermes --version` prints. Drop it once upstream ships the fix: the
  build then stops on it.

  These two patches are the only changes to upstream's code. `package()` only
  rewrites build paths in `web_dist/hermes-build.json`, stubs out the TUI's
  `build.mjs`, strips the venv's native libraries and adds files beside the code (bytecode, install stamp, system-tools
  store, the TUI bundle's `package.json`). The release notes link every patch.
- `aur/PKGBUILD` — the AUR *wrapper*, source of truth for
  [hermes-agent-bin on the AUR](https://aur.archlinux.org/packages/hermes-agent-bin).
  Its `source` points at the GitHub Release artifact, stored under a name that
  differs from the package makepkg writes; `package()` only extracts the
  payload (`opt/` and `usr/`).
- `scripts/bump-pkgbuild.py` — bump automation, run by hand: detects a new upstream
  tag, edits both PKGBUILDs + `.SRCINFO`, opens an auto-merge PR, and reports
  drift from the AUR source package `hermes-agent`.
- `scripts/check-metadata.sh` — fails the build when `PKGBUILD` and
  `aur/PKGBUILD` disagree on version, dependencies, provides or conflicts.
- `.github/workflows/build.yml` — `bump` / `plan` / `build` / `smoke` /
  `wrapper` / `release` / `aur-sync` pipeline.

## Maintenance

- **New upstream release**: there is no scheduled check; watch the upstream repository's releases (*Watch > Custom > Releases*) and read the release notes first: a new release needs thorough testing before it is packaged, and a change around the patched lines stops the build until the patch is rebased or dropped. Then run the workflow by hand with `bump` (`gh workflow run build-package -f bump=true`). The `bump` job moves `PKGBUILD` to the new tag (tag, commit, source checksum), updates `aur/PKGBUILD` and `.SRCINFO`, and opens an auto-merge PR. A new version starts at `pkgrel=1`; a new tag with an unchanged version gets the next `pkgrel` (otherwise its release tag would already exist); an older version aborts the bump. An open bump PR is updated with `main` when the job runs again, because the ruleset only merges up-to-date branches. The job authenticates with the `BUMP_TOKEN` secret — a fine-grained PAT (Contents + Pull requests: read/write) — because the default `GITHUB_TOKEN` produces a bot-authored PR whose checks need manual approval and whose merge never triggers the release pipeline. The job logs the token identity it used and fails if the secret is missing or rejected; its read-only calls to upstream's API use the workflow token, because unauthenticated calls hit the runners' shared rate limit. The PAT is created without an expiry date, so revocation — not rotation — is the deliberate step: delete it under *Settings > Developer settings > Fine-grained tokens* and `gh secret delete BUMP_TOKEN` here and in `hermes-agent-desktop-bin`.
- **Pipeline**: `plan` -> `build` -> `smoke` and `wrapper` (side by side) -> `release` -> `aur-sync`. On a push to `main` whose `pkgver-pkgrel` is already released (CI, scripts, docs, `aur/`), `plan` skips `build`, `smoke`, `wrapper` and `release`: the pull request run checked the change. `aur-sync` publishes `aur/` against the existing release. A new version is built once: on the push of a merged pull request from this repository, `plan` finds that pull request's last green run (both lookups are retried for up to 45 s: GitHub links the merge commit to its pull request a few seconds late). When that run built the same tree (`build-info`), `release` publishes its package without building again. A fork pull request, an expired artifact (3 days), another tree or a failed lookup builds as before; the release notes link the run that built the package. A manual dispatch on `main` always builds. If `plan` fails, everything builds. `build`, `smoke` and `wrapper` also run on pull requests (merge gate): `build` runs `check()` and validates `aur/.SRCINFO` and the metadata of both PKGBUILDs. `wrapper` builds `aur/PKGBUILD` from the fresh artifact the way AUR users' makepkg does: its payload must match the artifact file for file (paths, modes, links, sha256). The download must also keep its checksum for a rebuild. `smoke` installs the package in a clean container with the dependencies pacman resolves from its `depends=()` and checks that every module ships valid bytecode, the import, that the venv runs on the system Python, that everything under `/opt` is readable for other users, the version, upstream commit and commit date `hermes --version` reports (the date checked against GitHub), the prebuilt TUI and web bundles, `hermes --help`, the runtime command `hermes --print-runtime-command` reports (the venv python, also when asked from a directory holding a `hermes_cli/`) and that this command runs. For a fresh non-root user it checks that pm finds node, npx and uvx in the system-tools store with a clean startup check, hermes keeps its children, cron scripts and gateway unit on the venv. Bare MCP commands like ffmpeg must not be shadowed by the store. Another fresh user enables a local plugin with a Python dependency, which makes pm re-resolve `uv.lock` on the system uv. It also checks that pm finds the shipped extras, that upstream's tests stay out of `/opt` and that the launcher picks a system browser while hermes takes `agent-browser` from `PATH`. A venv python started without the launcher (the gateway service) gets the same environment. `release` and `aur-sync` only run for `main`; `release` tags the built commit and writes notes linking the upstream release and the upstream compare view. `aur-sync` injects the released artifact's sha256 into `aur/` and pushes to the AUR only while its commit is still `main`'s HEAD. Upstream tag and commit are pinned in `PKGBUILD` (`_pkgver_tag`, `_commit`).
- **Copies of this repository** (forks, a private CI test repository): the AUR push only runs in `jabla/hermes-agent-bin`. Elsewhere `aur-sync` prints the diff it would push, so pipeline changes can be tested end to end without publishing anything.
- **Files from root runs**: hermes run as root writes into `/opt/hermes-agent` (bytecode, packages a lazy install puts into the venv). These files belong to no package. When an update ships a file at the same path, pacman stops with `... exists in filesystem`: since 0.22.1-1 for bytecode (`__pycache__/*.cpython-314.pyc`), since 0.22.0-2 for `venv/bin/ddgs`. Both are safe to replace: `yay -S hermes-agent-bin --overwrite '/opt/hermes-agent/*.pyc'` (or `--overwrite '/opt/hermes-agent/venv/bin/ddgs'`). After an update from 0.21.5 or older (bundled CPython 3.11), pacman may warn that a `python3.11` directory under `/opt/hermes-agent` is not empty: remove it, nothing uses it any more.
- **Packaging-only changes** (build steps, launcher, dependencies, the wrapper): bump `pkgrel` in both PKGBUILDs, or the release tag already exists and nothing new is published.
- **Reference package**: `PKGBUILD` follows the AUR source package `hermes-agent` (build steps, extras, launcher and its environment). It took over `system-tools.py` and an adapted `keep-venv-interpreter.patch` (it also accepts `distribution: package-manager`) from this repository. Differences: the upper Python pin (`python<3.15`), the install stamp (upstream's script, `distribution: pacman`), `release-date-from-stamp.patch`, the bytecode, the TUI bundle's `package.json`, the rewritten `hermes-build.json` paths, the browser setup (`agent-browser` and a browser are optional here; the launcher stays silent without one), the launcher's answer to `--print-runtime-command` (desktop 0.22.4), `uv>=` pm's uv pin (`_uvmin`, see `system-tools.py` above), `hermes_agent_bin_env.py` (the launcher's environment for venv processes started without it) and the reference's `HERMES_NODE` export (the system-tools store already supplies node). The bump job warns ("Drift from hermes-agent", also in the bump PR) when that PKGBUILD changes beyond its version fields (`pkgver`, `pkgrel`, `_commit`, `_commit_date`, the tarball checksum, comment lines); the checksums of the reference's own files count as a change. Review the change in its [AUR history](https://aur.archlinux.org/cgit/aur.git/log/?h=hermes-agent), port what applies, then set `REFERENCE_PKGBUILD_SHA256` in `scripts/bump-pkgbuild.py` to the value the warning prints.
- **AUR wrapper**: only `pkgver`/`pkgrel` are bumped there; its `sha256sums` is the release artifact's, computed after the build by `aur-sync` (a local `makepkg` yields a different hash).
- **hermes-agent-desktop-bin** runs the desktop app's backend through this package's `/usr/bin/hermes`. It depends on `hermes-agent>=<version>` like the AUR source package `hermes-agent-desktop`, which is why `provides=()` carries the version (the smoke job checks it). Its smoke job installs a pinned release artifact of this repository by its asset name. The app asks `/usr/bin/hermes --print-runtime-command` for the interpreter it mints gateway tickets with; the launcher answers through upstream's `hermes_cli._launchers` (the venv python). Changing the launcher path, the provides entry or the asset names needs the same change there.
- **AUR key**: keep `AUR_SSH_KEY` as a secret of the `aur` environment, with deployment branches limited to `main` — repository secrets are readable by pull requests from branches of this repository. The same key also publishes `hermes-agent-desktop-bin`, and AUR keys can push to every package of the account, so both repositories need the same environment setup.

## License

Repository content: [BSD Zero Clause (0BSD)](LICENSE). The packaged app is MIT (Nous Research).
