# Build PKGBUILD for the prebuilt hermes-agent-bin package.
# Adapted from the AUR package hermes-agent (maintainer y0uCeF,
# https://aur.archlinux.org/packages/hermes-agent). Upstream pins a large,
# partly-native Python dependency set; uv's relocatable venv keeps the
# packaged environment usable after makepkg moves it under /opt. The build
# (npm ci + esbuild TUI/web bundles + uv sync) runs ONCE here in CI; the
# installed package never compiles anything.
pkgname=hermes-agent-bin
_pkgver_tag=v0.22.1
_commit=297552a9d646119871391d202509822cd86330df
_tagver=${_pkgver_tag#v}           # tag without the leading v — GitHub strips it from the archive dir
_optname=hermes-agent              # fixed install dir (pkgname-independent, matches source pkg)
_pyver=3.14                        # Arch's python minor; keep depends=() in step
pkgver=0.22.1
pkgrel=1
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
options=('!debug' '!strip')   # package() strips the native libraries itself
source=(
  "hermes-agent-${_tagver}.tar.gz::${url}/archive/refs/tags/${_pkgver_tag}.tar.gz"
  'keep-venv-interpreter.patch'
  'release-date-from-stamp.patch'
  'edge-tts-7.3.0.patch'
  'system-tools.py'
)
sha256sums=('45ebe864dbf65ecd31693a811ddd6e2e449b1878b835b563cf0a28d6a9c4bf38'
            '8a371d1fb5e0a1fb7a20eeb1f0f4250a70cc8ce26aef47fc19fdc77af88a7d52'
            '107cf7f981e7a96466d7c3f2a2cc1b8cdf2c1a5db797c22087b27f2e7f64541f'
            'd1c3260e7ea4fc56894449eac5c9de04e85f0429e58dbbc1eb87e8320a814d27'
            '5950d73a49526767dfac20084d8c5597b7ebf5c16e7bff99e31dc4d7fe0d139d')

_extract_dir() {
  echo "${srcdir}/hermes-agent-${_tagver}"
}

prepare() {
  cd "$(_extract_dir)"

  # The archive's mtimes are the upstream commit time. Record it before the
  # patches below change pyproject.toml; package() writes it into the stamp.
  stat -c %Y pyproject.toml > "${srcdir}/commit-date"

  # --fuzz=0: a hunk whose context drifted must fail loudly instead of being
  # applied at a guessed location (offsets are still accepted).
  patch --batch --fuzz=0 -Np1 -i "${srcdir}/keep-venv-interpreter.patch"
  # Upstream #135223 (draft): the banner date comes from the stamp's
  # commitDate, not the stale 2026.9.24 literal. Drop it once upstream ships
  # the fix; until then this hunk fails loudly when __init__.py moves.
  patch --batch --fuzz=0 -Np1 -i "${srcdir}/release-date-from-stamp.patch"
  # Upstream #138204 (draft): edge-tts 7.3.0 handles Microsoft's new
  # Sec-MS-GEC tokens; with 7.2.7 every Edge TTS synthesis gets a 403
  # (#137944). Drop it once upstream ships the bump.
  patch --batch --fuzz=0 -Np1 -i "${srcdir}/edge-tts-7.3.0.patch"
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
  # commit time comes from prepare().
  # The script fills gaps from CI variables (GITHUB_REF_NAME, ...) and from
  # git, which would find this packaging repository around $srcdir: start it
  # with a bare environment and keep git inside $srcdir.
  env -i PATH="$PATH" GIT_CEILING_DIRECTORIES="$srcdir" \
    venv/bin/python scripts/write_install_stamp.py \
    --output "$_optdir/install-stamp.json" \
    --commit "$_commit" \
    --commit-date "$(<"${srcdir}/commit-date")" \
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

  # Bytecode for the whole tree: users cannot write __pycache__ into the
  # root-owned /opt, so without it every start compiles everything again
  # (`hermes --help` 1.15 s instead of 0.46 s). checked-hash: makepkg resets
  # every mtime to SOURCE_DATE_EPOCH, which would turn timestamp-based .pyc
  # files stale. A .py edited in place still wins over its old .pyc.
  # -s/-p record the installed paths, not $pkgdir, in tracebacks.
  "/usr/bin/python${_pyver}" -m compileall -q -j0 \
    --invalidation-mode checked-hash -s "$pkgdir" -p / "$_optdir"

  # makepkg's own strip step inspects each of the ~37k files (about three
  # minutes in CI); only the venv's native libraries are ELF objects. The
  # name test alone would also catch text files named *.so.
  find "$_optdir" -type f -name '*.so*' -print0 |
    while IFS= read -r -d '' lib; do
      if [ "$(head -c 4 "$lib")" = $'\x7fELF' ]; then
        strip --strip-unneeded "$lib"
      fi
    done

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
    # An empty value keeps pm's Chromium. The order is the desktop app's
    # launcher's, which exports its pick before it runs this one.
    echo 'if [[ -z "${AGENT_BROWSER_EXECUTABLE_PATH+set}" ]]; then'
    echo '  for browser in google-chrome-stable google-chrome chromium brave; do'
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
