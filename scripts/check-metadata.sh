#!/bin/bash
# Fail when PKGBUILD (built and smoke-tested in CI) and aur/PKGBUILD (what AUR
# users install) disagree on the metadata that ends up in the installed
# package. pkgdesc, makedepends, options and sources differ on purpose.
set -euo pipefail
cd "$(dirname "$0")/.."

fields='pkgver|pkgrel|url|arch|license|depends|optdepends|provides|conflicts|replaces'
extract() {
  (cd "$1" && makepkg --printsrcinfo) |
    sed -nE "s/^\t(${fields}) = /\1 = /p" | sort
}

if ! diff -u --label PKGBUILD --label aur/PKGBUILD <(extract .) <(extract aur); then
  echo "ERROR: PKGBUILD and aur/PKGBUILD metadata differ (see diff above)" >&2
  exit 1
fi
echo "PKGBUILD and aur/PKGBUILD metadata agree"
