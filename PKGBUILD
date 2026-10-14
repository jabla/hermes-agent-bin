# Build PKGBUILD for the prebuilt hermes-agent-bin package.
# Adapted from the AUR package hermes-agent (maintainer y0uCeF,
# https://aur.archlinux.org/packages/hermes-agent). Upstream pins a large,
# partly-native Python dependency set; uv's relocatable venv keeps the
# packaged environment usable after makepkg moves it under /opt. The build
# (npm ci + esbuild TUI/web bundles + uv sync) runs ONCE here in CI; the
# installed package never compiles anything.
pkgname=hermes-agent-bin
_pkgver_tag=v0.22.0
_commit=e06df9c2eae6901f4c88f464e0ae6e753c0428b8
_tagver=${_pkgver_tag#v}           # tag without the leading v — GitHub strips it from the archive dir
_optname=hermes-agent              # fixed install dir (pkgname-independent, matches source pkg)
_pyver=3.14                        # Arch's python minor; keep depends=() in step
pkgver=0.22.0
pkgrel=2
pkgdesc="Locally-run AI agent with tool use, web browsing, and automation (prebuilt binary, CI-built)"
arch=('x86_64')
url='https://github.com/NousResearch/hermes-agent'
license=('MIT')
depends=(
  'python>=3.14' 'python<3.15'   # the minor in _pyver
  'nodejs' 'npm' 'uv' 'ripgrep' 'ffmpeg'
  # the libraries of pm's Chromium (`hermes pm install agent-browser`)
  'nss' 'atk' 'at-spi2-core' 'cups' 'libdrm' 'libxkbcommon' 'mesa' 'pango'
  'cairo' 'alsa-lib' 'libxcomposite' 'libxdamage' 'libxrandr'
  'git' 'curl'
)
optdepends=(
  'agent-browser: browser tools on a system browser (AUR)'
  'chromium: system browser for the browser tools'
  'google-chrome: system browser for the browser tools (AUR)'
  'brave-bin: system browser for the browser tools (AUR)'
)
makedepends=('rsync' 'cmake')   # cmake: python-olm (matrix extra)
conflicts=('hermes-agent')
provides=('hermes-agent')
options=('!debug')
source=(
  "hermes-agent-${_tagver}.tar.gz::${url}/archive/refs/tags/${_pkgver_tag}.tar.gz"
  'keep-venv-interpreter.patch'
  'release-date-from-stamp.patch'
  'system-tools.py'
)
sha256sums=('61333ab64f7ad728bc265d103fd73b2eb4b936f9c8d9fe3ccf2531ad955e96a1'
            '8a371d1fb5e0a1fb7a20eeb1f0f4250a70cc8ce26aef47fc19fdc77af88a7d52'
            '107cf7f981e7a96466d7c3f2a2cc1b8cdf2c1a5db797c22087b27f2e7f64541f'
            '5950d73a49526767dfac20084d8c5597b7ebf5c16e7bff99e31dc4d7fe0d139d')

_extract_dir() {
  echo "${srcdir}/hermes-agent-${_tagver}"
}

prepare() {
  cd "$(_extract_dir)"

  # --fuzz=0: a hunk whose context drifted must fail loudly instead of being
  # applied at a guessed location (offsets are still accepted).
  patch --batch --fuzz=0 -Np1 -i "${srcdir}/keep-venv-interpreter.patch"
  # Upstream #135223 (draft): the banner date comes from the stamp's
  # commitDate, not the stale 2026.9.24 literal. Drop it once upstream ships
  # the fix; until then this hunk fails loudly when __init__.py moves.
  patch --batch --fuzz=0 -Np1 -i "${srcdir}/release-date-from-stamp.patch"
}

build() {
  cd "$(_extract_dir)"

  # vite-plugin-tailwindcss uses the ignore package which walks up the tree to
  # read .gitignore files. Creating an empty .git directory stops the scan.
  [ ! -d .git ] && mkdir .git

  npm ci --ignore-scripts --no-fund --no-audit --progress=false --include=dev
  npm run build --workspace web
  npm run build:ink --workspace ui-tui
  npm run build --workspace ui-tui

  # The venv runs on Arch's python (upstream supports 3.14 since v0.21.6,
  # requires-python ">=3.11,<3.15"). A venv only works on the minor version
  # it was built for, so depends=() pins it: when Arch moves python to the
  # next minor, pacman holds that update back until this package follows
  # (to the new minor if upstream supports it, else to a bundled CPython).
  UV_PYTHON_DOWNLOADS=never uv venv \
    --clear \
    --python "/usr/bin/python${_pyver}" \
    --relocatable \
    venv
  # Lazy installs are off for the root-owned venv, so the extras users
  # commonly hit ship here, as in the reference package: anthropic (Anthropic
  # provider), edge-tts (default TTS), ddgs (free web search), doc-extract and
  # the gateways beyond messaging. python-olm (matrix) builds a vendored libolm
  # whose cmake_minimum_required CMake >= 4 rejects unless the policy minimum
  # is raised.
  CMAKE_POLICY_VERSION_MINIMUM=3.5 \
  UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT="$PWD/venv" \
    uv sync --locked --no-dev --no-install-project \
      --extra all,messaging,anthropic,edge-tts,ddgs,doc-extract \
      --extra feishu,matrix,dingtalk,wecom,teams,google-chat
}

check() {
  cd "$(_extract_dir)"

  test -s hermes_cli/web_dist/index.html
  test -s ui-tui/dist/entry.js
  PYTHONPATH="$PWD" venv/bin/python -c \
    'import hermes_cli.main, anthropic, edge_tts, ddgs, lark_oapi, mautrix, dingtalk_stream, defusedxml'
}

package() {
  cd "$(_extract_dir)"

  # Install to /opt/hermes-agent (fixed, pkgname-independent — identical to the
  # source package, so switching source -> -bin is drop-in; conflicts=() keeps
  # only one variant installed).
  _optdir="$pkgdir/opt/${_optname}"
  install -d "$_optdir"

  rsync -a --exclude='__pycache__' --exclude='.git' \
    --exclude='node_modules' --exclude='web/src' \
    --exclude='web/package.json' --exclude='web/package-lock.json' \
    --exclude='web/vite.config.ts' --exclude='web/tsconfig*.json' \
    --exclude='web/eslint.config.js' --exclude='web/README.md' \
    --exclude='ui-tui/src' --exclude='ui-tui/node_modules' \
    --exclude='scripts/tests' --exclude='scripts/install.*' \
    --exclude='build' --exclude='/tests' \
    . "$_optdir/"

  echo "console.log('skipping build, using prebuilt dist/entry.js')" > "$_optdir/ui-tui/scripts/build.mjs"

  # The web build's freshness manifest (new in v0.21.6) records its inputs by
  # absolute build path; point it at the installed tree instead of $srcdir.
  sed -i "s|$(_extract_dir)|/opt/${_optname}|g" "$_optdir/hermes_cli/web_dist/hermes-build.json"

  # Since v0.21.6 the version comes from a build stamp beside the code
  # (pyproject says 0.0.0; without the stamp `hermes --version` reports
  # "unknown"). Upstream's packager script writes it. "external" keeps hermes
  # from syncing the root-owned venv and marks the tree as not its own. The
  # archive's mtimes are the commit time.
  # The script fills gaps from CI variables (GITHUB_REF_NAME, ...) and from
  # git, which would find this packaging repository around $srcdir: start it
  # with a bare environment and keep git inside $srcdir.
  env -i PATH="$PATH" GIT_CEILING_DIRECTORIES="$srcdir" \
    venv/bin/python scripts/write_install_stamp.py \
    --output "$_optdir/install-stamp.json" \
    --commit "$_commit" \
    --commit-date "$(stat -c %Y pyproject.toml)" \
    --base-version "$pkgver" \
    --distance 0 \
    --source ci \
    --update-mechanism external
  # `distribution` names the steward that owns the tree; `hermes update` then
  # refuses with "managed by pacman" before it tries to lock the root-owned
  # tree. The script only offers upstream's own stewards, the runtime takes
  # any name. `runtimeDir` points pm at the system-tools store below; the
  # runtime resolves it as given (not relative to the stamp), so absolute.
  venv/bin/python - "$_optdir/install-stamp.json" "/opt/${_optname}/system-store/tools" <<'PY'
import json, sys
path, store = sys.argv[1:]
with open(path, encoding="utf-8") as f:
    stamp = json.load(f)
stamp["distribution"] = "pacman"
stamp["runtimeDir"] = store
with open(path, "w", encoding="utf-8") as f:
    json.dump(stamp, f, indent=2)
    f.write("\n")
PY

  # pm's store of the tools depends=() provides: symlinks into /usr/bin under
  # the pins of pm/lock.json (see system-tools.py).
  venv/bin/python -B "$srcdir/system-tools.py" "$_optdir" "$_optdir/system-store/tools"

  # Ship the prebuilt TUI into hermes_cli/tui_dist/ so _find_bundled_tui()
  # finds it and skips the npm install step (which would fail with EACCES on
  # the root-owned /opt tree). hermes_cli is imported from /opt via the .pth
  # file, NOT from the venv site-packages.
  _tuidir="$_optdir/hermes_cli/tui_dist"
  install -d "$_tuidir"
  if [ -d ui-tui/dist ]; then
    cp -a ui-tui/dist/* "$_tuidir/"
  fi
  # The bundle is an ES module. Upstream's bundle ships this package.json
  # beside it (scripts/build/agent.py); without it node finds the root
  # package.json, warns MODULE_TYPELESS_PACKAGE_JSON and parses entry.js twice.
  echo '{"type":"module"}' > "$_tuidir/package.json"

  install -d "$_optdir/venv/lib/python${_pyver}/site-packages"
  {
    echo "import sys; sys.path.insert(0, \"/opt/${_optname}\")"
  } > "$_optdir/venv/lib/python${_pyver}/site-packages/hermes.pth"

  # Readable for every user: the TUI build leaves ui-tui/dist at mode 700
  # (since v0.21.6).
  chmod -R a+rX "$_optdir"
  # uv leaves its venv lock world-writable (0666); only root changes this venv.
  rm -f "$_optdir/venv/.lock"

  install -d "$pkgdir/usr/bin"
  {
    echo "#!/bin/bash"
    echo "unset PYTHONPATH"
    echo "unset PYTHONHOME"
    echo ': "${XDG_DATA_HOME:=$HOME/.local/share}"'
    echo 'export HERMES_DISABLE_LAZY_INSTALLS=1'
    echo 'export HERMES_LAZY_INSTALL_TARGET="$XDG_DATA_HOME/hermes-agent/python"'
    # The browser tools take a system browser only through this variable
    # (it wins over pm's own Chromium). Without one they need
    # `hermes pm install agent-browser`, which also fetches pm's Chromium.
    echo 'if [[ -z "${AGENT_BROWSER_EXECUTABLE_PATH:-}" ]]; then'
    echo '  for browser in chromium google-chrome-stable brave; do'
    echo '    if browser_path=$(type -P "$browser"); then'
    echo '      export AGENT_BROWSER_EXECUTABLE_PATH="$browser_path"'
    echo '      break'
    echo '    fi'
    echo '  done'
    echo 'fi'
    echo "exec /opt/${_optname}/venv/bin/python -m hermes_cli.main" '"$@"'
  } > "$pkgdir/usr/bin/hermes"

  chmod 755 "$pkgdir/usr/bin/hermes"

  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
