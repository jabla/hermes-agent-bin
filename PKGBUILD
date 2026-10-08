# Build PKGBUILD for the prebuilt hermes-agent-bin package.
# Adapted from the AUR package hermes-agent (maintainer y0uCeF,
# https://aur.archlinux.org/packages/hermes-agent). Upstream pins a large,
# partly-native Python dependency set; uv's relocatable venv keeps the
# packaged environment usable after makepkg moves it under /opt. The build
# (npm ci + esbuild TUI/web bundles + uv sync) runs ONCE here in CI; the
# installed package never compiles anything.
pkgname=hermes-agent-bin
_pkgver_tag=v0.21.6
_commit=818c13be1dc4fd28987e1e881a9408224afd4535
_tagver=${_pkgver_tag#v}           # tag without the leading v — GitHub strips it from the archive dir
_optname=hermes-agent              # fixed install dir (pkgname-independent, matches source pkg)
_pyver=3.14                        # Arch's python minor; keep depends=() in step
pkgver=0.21.6
pkgrel=1
pkgdesc="Locally-run AI agent with tool use, web browsing, and automation (prebuilt binary, CI-built)"
arch=('x86_64')
url='https://github.com/NousResearch/hermes-agent'
license=('MIT')
depends=(
  'python>=3.14' 'python<3.15'   # the minor in _pyver
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
sha256sums=('1ba3500cdbe876bb9d347b3c12f41c591a421293eac58faba23571287dfe1cf8')

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

  echo "console.log('skipping build, using prebuilt dist/entry.js')" > "$_optdir/ui-tui/scripts/build.mjs"

  # The web build's freshness manifest (new in v0.21.6) records its inputs by
  # absolute build path; point it at the installed tree instead of $srcdir.
  sed -i "s|$(_extract_dir)|/opt/${_optname}|g" "$_optdir/hermes_cli/web_dist/hermes-build.json"

  # Since v0.21.6 the version comes from a build stamp beside the code
  # (pyproject says 0.0.0; without the stamp `hermes --version` reports
  # "unknown"). Upstream's packager script writes it. "external" keeps hermes
  # from syncing the root-owned venv and marks the tree as not its own; there
  # is no steward value for distro packages yet, so `hermes update` still
  # refuses with a generic message. The archive's mtimes are the commit time.
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

  # Ship the prebuilt TUI into hermes_cli/tui_dist/ so _find_bundled_tui()
  # finds it and skips the npm install step (which would fail with EACCES on
  # the root-owned /opt tree). hermes_cli is imported from /opt via the .pth
  # file, NOT from the venv site-packages.
  _tuidir="$_optdir/hermes_cli/tui_dist"
  install -d "$_tuidir"
  if [ -d ui-tui/dist ]; then
    cp -a ui-tui/dist/* "$_tuidir/"
  fi

  install -d "$_optdir/venv/lib/python${_pyver}/site-packages"
  {
    echo "import sys; sys.path.insert(0, \"/opt/${_optname}\")"
  } > "$_optdir/venv/lib/python${_pyver}/site-packages/hermes.pth"

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
