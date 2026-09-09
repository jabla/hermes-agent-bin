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
  makepkg). Runs `npm ci` + esbuild (TUI `entry.js`, web `web_dist`) and
  `uv sync --locked` into a self-contained `python3.11` venv (upstream pins
  `>=3.11,<3.14`, but Arch dropped `python311` from its repos, so a standalone
  CPython 3.11 is bundled in — the package needs no system Python).
- `aur/PKGBUILD` — the AUR *wrapper*, source of truth for
  [hermes-agent-bin on the AUR](https://aur.archlinux.org/packages/hermes-agent-bin).
  Its `source` URL points at the GitHub Release artifact; `package()` only
  extracts the payload.
- `scripts/bump-pkgbuild.py` — daily bump automation: detects a new upstream
  tag, edits both PKGBUILDs + `.SRCINFO`, opens an auto-merge PR.
- `.github/workflows/build.yml` — `bump` / `build` / `smoke` / `release` /
  `aur-sync` pipeline.

## License

MIT (Nous Research). This repo only packages their software.
