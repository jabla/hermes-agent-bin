# hermes-agent-bin

Prebuilt Arch Linux package of [Hermes Agent](https://github.com/NousResearch/hermes-agent) from Nous Research. Nothing is compiled at install time.

The source package [hermes-agent](https://aur.archlinux.org/packages/hermes-agent) builds the same recipe on your machine. The two conflict.

## Install

```bash
yay -S hermes-agent-bin
```

Hermes goes to `/opt/hermes-agent`, the launcher to `/usr/bin/hermes`. Update with your AUR helper, not `hermes update`. After an update, restart a running gateway: `hermes gateway restart`.

## Optional features

Hermes cannot install optional Python packages into the root-owned tree, so the package ships these extras: `all`, `messaging`, `anthropic`, `edge-tts` (default TTS), `ddgs` (free web search), `doc-extract`, `keychain` (`hermes vault key migrate --to keychain`) and the gateways `feishu`, `matrix`, `dingtalk`, `wecom`, `teams` and `google-chat`. Open an issue if you need another one.

### Browser tools

`browser_exec` drives a Chromium. It takes the first of these:

1. `browser.executable_path`: `hermes config set browser.executable_path /usr/bin/chromium`
2. Hermes' pinned Chromium in `~/.hermes/tools`, fetched once per user with `hermes pm install chromium`
3. A system browser on `PATH`: `google-chrome-stable`, `google-chrome`, `chromium`, `chromium-browser` or `brave` (packages `chromium`, `google-chrome` or `brave-bin`)

### Webapp

`hermes webapp` opens the browser-hosted desktop that the gateway serves. Turn it on first:

```bash
hermes config set webapp.enabled true
hermes webapp
```

## Troubleshooting

**`exists in filesystem` on an update**: files a root run wrote into `/opt/hermes-agent` (bytecode, Python packages) belong to no package. pacman stops when an update ships a file at the same path. These files are safe to replace:

```bash
yay -S hermes-agent-bin --overwrite '/opt/hermes-agent/*'
```

Run hermes as your own user to keep the tree clean.

## What differs from upstream

- `keep-venv-interpreter.patch`: processes Hermes starts (cron scripts, the gateway service) run on the package's venv, not on a Python from Hermes' tool store.
- `release-date-from-stamp.patch`: `hermes --version` and the banners show the release's date (upstream [#135223](https://github.com/NousResearch/hermes-agent/pull/135223)).
- `system-browser-fallback.patch`: the browser tools fall back to a system browser (see [Browser tools](#browser-tools)).
- Hermes' tool store links the system's `node`, `npm`, `pnpm`, `ffmpeg`, `ripgrep`, `python` and `uv` from the package's dependencies instead of downloading them. Processes Hermes starts get this node and npm first on `PATH`, ahead of nvm or volta, as upstream does with its downloaded tools.

## Bugs

Packaging problems: open an issue here. Bugs in Hermes itself: [upstream](https://github.com/NousResearch/hermes-agent/issues).

## License

Repository content: [BSD Zero Clause (0BSD)](LICENSE). The packaged app is MIT (Nous Research).
