# Build PKGBUILD for the prebuilt hermes-agent-bin package.
# Adapted from the AUR package hermes-agent (maintainer y0uCeF,
# https://aur.archlinux.org/packages/hermes-agent). Upstream pins a large,
# partly-native Python dependency set; uv's relocatable venv keeps the
# packaged environment usable after makepkg moves it under /opt. The build
# (npm ci + esbuild TUI/web bundles + uv sync) runs ONCE here in CI; the
# installed package never compiles anything.
pkgname=hermes-agent-bin
_pkgver_tag=v2026.8.31
_commit=29112bef099274229cadff79cdff7bf7b99c4b77
_tagver=${_pkgver_tag#v}           # 2026.8.31 — GitHub strips the leading v from the archive dir
_optname=hermes-agent              # fixed install dir (pkgname-independent, matches source pkg)
pkgver=0.21.0
pkgrel=1
pkgdesc="Locally-run AI agent with tool use, web browsing, and automation (prebuilt binary, CI-built)"
arch=('x86_64')
url='https://github.com/NousResearch/hermes-agent'
license=('MIT')
depends=(
  'nodejs' 'uv' 'ripgrep' 'ffmpeg'
  'nss' 'atk' 'at-spi2-core' 'cups' 'libdrm' 'libxkbcommon' 'mesa' 'pango'
  'cairo' 'alsa-lib' 'git' 'curl'
)
makedepends=('npm' 'rsync')
conflicts=('hermes-agent')
provides=('hermes-agent')
options=('!debug')
source=(
  "hermes-agent-${_tagver}.tar.gz::${url}/archive/refs/tags/${_pkgver_tag}.tar.gz"
)
sha256sums=('78fb3ff707ec1d17044b875ecac8bef28aa39d44242824f6871ca40afe7bf217')

_extract_dir() {
  echo "${srcdir}/hermes-agent-${_tagver}"
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

  # Upstream requires-python is ">=3.11,<3.14", but Arch dropped python311
  # from its repos (only python 3.14 remains). Bundle a standalone CPython
  # 3.11 via uv so the package is self-contained and needs no system python.
  uv python install 3.11
  UV_PYTHON_PREFERENCE=only-managed uv venv \
    --clear \
    --python 3.11 \
    --relocatable \
    venv
  UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT="$PWD/venv" \
    uv sync --locked --no-dev --no-install-project --extra all,messaging
}

check() {
  cd "$(_extract_dir)"

  test -s hermes_cli/web_dist/index.html
  test -s ui-tui/dist/entry.js
  PYTHONPATH="$PWD" venv/bin/python -c 'import hermes_cli.main'
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
    --exclude='build' \
    . "$_optdir/"

  # Bundle the standalone CPython into the package so the venv is fully
  # self-contained. uv's venv symlinks bin/python to the uv-managed interpreter
  # at an absolute path, which breaks after the package moves to /opt. Copy the
  # interpreter (bin/ + lib/) in and repoint bin/python relative so base + venv
  # relocate together. Skip include/ (headers) and share/ (man pages) — not
  # needed at runtime.
  _pybin="$(UV_PYTHON_PREFERENCE=only-managed uv python find 3.11)"
  _pyhome="$(dirname "$(dirname "$_pybin")")"
  install -d "$_optdir/python"
  cp -a "$_pyhome"/bin "$_pyhome"/lib "$_optdir/python/"
  rm -f "$_optdir/venv/bin/python"
  ln -s ../../python/bin/python3.11 "$_optdir/venv/bin/python"
  sed -i "s|^home = .*|home = /opt/hermes-agent/python/bin|" "$_optdir/venv/pyvenv.cfg"

  echo "console.log('skipping build, using prebuilt dist/entry.js')" > "$_optdir/ui-tui/scripts/build.mjs"

  # Ship the prebuilt TUI into hermes_cli/tui_dist/ so _find_bundled_tui()
  # finds it and skips the npm install step (which would fail with EACCES on
  # the root-owned /opt tree). hermes_cli is imported from /opt via the .pth
  # file, NOT from the venv site-packages.
  _tuidir="$_optdir/hermes_cli/tui_dist"
  install -d "$_tuidir"
  if [ -d ui-tui/dist ]; then
    cp -a ui-tui/dist/* "$_tuidir/"
  fi

  install -d "$_optdir/venv/lib/python3.11/site-packages"
  {
    echo "import sys; sys.path.insert(0, \"/opt/${_optname}\")"
  } > "$_optdir/venv/lib/python3.11/site-packages/hermes.pth"

  install -d "$pkgdir/usr/bin"
  {
    echo "#!/bin/bash"
    echo "unset PYTHONPATH"
    echo "unset PYTHONHOME"
    echo ': "${XDG_DATA_HOME:=$HOME/.local/share}"'
    echo 'export HERMES_DISABLE_LAZY_INSTALLS=1'
    echo 'export HERMES_LAZY_INSTALL_TARGET="$XDG_DATA_HOME/hermes-agent/python"'
    echo "exec /opt/${_optname}/venv/bin/python -m hermes_cli.main" '"$@"'
  } > "$pkgdir/usr/bin/hermes"

  chmod 755 "$pkgdir/usr/bin/hermes"

  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
