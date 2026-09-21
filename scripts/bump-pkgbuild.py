#!/usr/bin/env python3
"""Bump hermes-agent-bin to the latest upstream release.

Two modes:
  * default (dry run): report what a bump would change, write nothing.
  * --pr: create branch + commit (PKGBUILD, aur/PKGBUILD, aur/.SRCINFO),
    push it and open an auto-merge PR. Never commits to main directly.

Every run also compares the AUR source package hermes-agent, which PKGBUILD
is adapted from, with the state last reviewed here and reports drift as a
warning.

Exits 0 without changes when PKGBUILD already tracks the latest upstream tag.
Requires: gh (GH_TOKEN + GH_REPO env), makepkg available for .SRCINFO regen,
vercmp (pacman) for the version order. UPSTREAM_API_TOKEN, when set,
authenticates the GitHub API reads.
Must not run as root: makepkg refuses to run as root, so the container job
runs this script through runuser as an unprivileged user.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request

REPO = "NousResearch/hermes-agent"
REFERENCE = "hermes-agent"
REFERENCE_PKGBUILD = f"https://aur.archlinux.org/cgit/aur.git/plain/PKGBUILD?h={REFERENCE}"
REFERENCE_LOG = f"https://aur.archlinux.org/cgit/aur.git/log/?h={REFERENCE}"
# Fingerprint (see reference_fingerprint) of the hermes-agent PKGBUILD that
# PKGBUILD was last compared with: hermes-agent 0.21.3-1. Update it after
# porting a reference change.
REFERENCE_PKGBUILD_SHA256 = "3e895d53d7bea262542f45acc42250a234b38d9890de326f50ff4bb347e94cfa"
SHA_RE = re.compile(r"^sha256sums=\('([0-9a-f]{64})'", re.M)
# The fields every reference release changes; everything else is packaging.
VERSION_FIELDS_RE = re.compile(
    r"(?ms)^(?:pkgver|_tagver|pkgrel)=[^\n]*\n"
    r"|^(?:sha256sums|sha512sums|b2sums|md5sums)=\(.*?\)[^\n]*\n")


def api(path: str):
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": "hermes-agent-arch-builder"}
    # Unauthenticated requests share a 60/hour limit per runner IP and fail
    # with "HTTP Error 403: rate limit exceeded" on busy hosted runners.
    token = os.environ.get("UPSTREAM_API_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request("https://api.github.com" + path, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=600) as r:
        return r.read()


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def vercmp(a: str, b: str) -> int:
    """pacman's version order, the one users' updates follow (<0, 0, >0)."""
    r = run(["vercmp", a, b])
    if r.returncode != 0:
        sys.exit(f"vercmp {a} {b} failed: {r.stderr.strip()}")
    return int(r.stdout)


def next_pkgrel(version: str, cur_version: str, cur_pkgrel: str) -> int:
    """pkgrel for a new upstream tag that builds `version`.

    A new version starts at 1. A new tag with the same version (upstream
    re-tagged a release) needs pkgrel+1: with pkgrel=1 again, the release tag
    v<pkgver>-1 already exists, the release job skips and the new build never
    reaches the AUR. An older version means the release name was misparsed or
    upstream moved "latest" back; publishing it would downgrade users.
    """
    order = vercmp(version, cur_version)
    if order > 0:
        return 1
    if order < 0:
        sys.exit(f"upstream version {version} is older than PKGBUILD pkgver "
                 f"{cur_version}; refusing to downgrade (check the release name)")
    if not cur_pkgrel.isdigit():
        sys.exit(f"cannot increment non-integer pkgrel {cur_pkgrel!r}")
    return int(cur_pkgrel) + 1


def edit_pkgbuild(path: str, tag: str, version: str, commit: str, checksum: str,
                  pkgrel: int):
    """Edit the GitHub build PKGBUILD (has _pkgver_tag/_commit)."""
    pkg = open(path).read()
    pkg = re.sub(r"(?m)^_pkgver_tag=.*$", f"_pkgver_tag={tag}", pkg)
    pkg = re.sub(r"(?m)^_commit=.*$", f"_commit={commit}", pkg)
    pkg = re.sub(r"(?m)^pkgver=.*$", f"pkgver={version}", pkg)
    pkg = re.sub(r"(?m)^pkgrel=.*$", f"pkgrel={pkgrel}", pkg)
    pkg = SHA_RE.sub(f"sha256sums=('{checksum}'", pkg)
    # Fail loudly if any field stopped matching, instead of shipping the old value.
    for field in (f"_pkgver_tag={tag}", f"_commit={commit}", f"pkgver={version}",
                  f"pkgrel={pkgrel}", f"sha256sums=('{checksum}'"):
        if not starts_line(pkg, field):
            sys.exit(f"failed to write {field!r} into {path}")
    open(path, "w").write(pkg)


def starts_line(text: str, prefix: str) -> bool:
    """Whether a line starts with prefix (a plain substring test would also
    accept it inside another assignment, e.g. _commit= in _upstream_commit=)."""
    return re.search(r"(?m)^" + re.escape(prefix), text) is not None


def edit_aur_pkgbuild(path: str, version: str, pkgrel: int):
    """Edit the AUR wrapper PKGBUILD (no _pkgver_tag/_commit; source URL is
    variable-driven and follows pkgver/pkgrel automatically).

    Deliberately does NOT touch sha256sums: the wrapper's source is the
    release ARTIFACT, whose sha only exists AFTER the CI build. The
    post-release sync job computes the real artifact sha and injects it —
    writing the upstream source-tarball sha here would break `yay -S`
    checksums on the first automated bump."""
    pkg = open(path).read()
    pkg = re.sub(r"(?m)^pkgver=.*$", f"pkgver={version}", pkg)
    pkg = re.sub(r"(?m)^pkgrel=.*$", f"pkgrel={pkgrel}", pkg)
    for field in (f"pkgver={version}", f"pkgrel={pkgrel}"):
        if not starts_line(pkg, field):
            sys.exit(f"failed to write {field!r} into {path}")
    open(path, "w").write(pkg)


def require_non_root():
    """makepkg refuses to run as root — fail before anything is written."""
    if os.geteuid() == 0:
        sys.exit(
            "refusing to run as root: makepkg (used to regenerate aur/.SRCINFO) "
            "will not run as root. Run this script as an unprivileged user — "
            "see the 'bump' job in .github/workflows/build.yml."
        )


def regen_srcinfo(aur_dir: str):
    require_non_root()
    r = run(["makepkg", "--printsrcinfo"], cwd=aur_dir)
    if r.returncode != 0:
        print("makepkg --printsrcinfo failed:", r.stderr)
        sys.exit(1)
    with open(os.path.join(aur_dir, ".SRCINFO"), "w") as f:
        f.write(r.stdout)


def reference_fingerprint(text: str) -> str:
    """sha256 of a PKGBUILD without the fields every release changes."""
    return hashlib.sha256(VERSION_FIELDS_RE.sub("", text).encode()).hexdigest()


def check_reference_drift() -> list[str]:
    """Report when the AUR source package changed beyond its version fields.

    PKGBUILD is adapted from it: build(), package(), the launcher and its
    environment follow the reference, apart from the bundled CPython. A
    change there usually has to be ported. Warns instead of failing (the
    reference may simply have been reworded) and never copies anything.
    """
    try:
        text = fetch(REFERENCE_PKGBUILD).decode()
    except Exception as exc:        # AUR outages must not block the bump
        print(f"::warning::{REFERENCE} drift check skipped: {exc}")
        return []
    current = reference_fingerprint(text)
    if current == REFERENCE_PKGBUILD_SHA256:
        print(f"PKGBUILD is in sync with the reviewed {REFERENCE} PKGBUILD")
        return []
    drift = (f"the {REFERENCE} PKGBUILD changed beyond its version fields since "
             f"it was last reviewed ({REFERENCE_LOG}); port what applies to "
             f"PKGBUILD, then set REFERENCE_PKGBUILD_SHA256 in "
             f"scripts/bump-pkgbuild.py to {current}")
    print(f"::warning title=Drift from {REFERENCE}::{drift}")
    return [drift]


def gh(args: list[str]) -> subprocess.CompletedProcess:
    return run(["gh", *args])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pr", action="store_true",
                    help="push bump branch and open auto-merge PR")
    args = ap.parse_args()

    require_non_root()
    drift = check_reference_drift()

    rel = api(f"/repos/{REPO}/releases/latest")
    tag = rel["tag_name"]
    # Release names read "Hermes Agent v0.21.3 (v2026.9.14)": take the first
    # vX.Y.Z that is not the date tag itself, whatever order upstream uses.
    date_version = tag.lstrip("v")
    candidates = [v for v in re.findall(r"\bv(\d+\.\d+\.\d+)\b", rel.get("name") or "")
                  if not date_version.startswith(v)]
    if not candidates:
        print(f"cannot parse version from release name: {rel.get('name')!r}")
        return 2
    version = candidates[0]

    pkg = open("PKGBUILD").read()
    cur_tag = re.search(r"(?m)^_pkgver_tag=(.+)$", pkg).group(1)
    if cur_tag == tag:
        print(f"PKGBUILD already at latest tag {tag}, nothing to do")
        return 0
    cur_version = re.search(r"(?m)^pkgver=(.+)$", pkg).group(1)
    cur_pkgrel = re.search(r"(?m)^pkgrel=(.+)$", pkg).group(1)
    pkgrel = next_pkgrel(version, cur_version, cur_pkgrel)
    full_version = version if pkgrel == 1 else f"{version}-{pkgrel}"

    ref = api(f"/repos/{REPO}/git/refs/tags/{tag}")
    obj = ref["object"]
    commit = obj["sha"]
    if obj["type"] == "tag":
        commit = api(f"/repos/{REPO}/git/tags/{commit}")["object"]["sha"]

    checksum = hashlib.sha256(
        fetch(f"https://github.com/{REPO}/archive/refs/tags/{tag}.tar.gz")
    ).hexdigest()
    print(f"upstream tag={tag} version={version} pkgrel={pkgrel} commit={commit} "
          f"sha256={checksum}")

    if not args.pr:
        print("dry run: no files changed (use --pr to open the bump PR)")
        return 0

    # No PR yet open for this tag?
    existing = gh(["pr", "list", "--state", "open",
                   "--search", f"in:title \"chore: bump to {tag}\"",
                   "--json", "number,url"])
    if existing.returncode == 0 and json.loads(existing.stdout):
        pr = json.loads(existing.stdout)[0]
        # main's ruleset requires branches to be up to date with main, so
        # auto-merge waits forever once main moves. Merging main into the bump
        # branch re-runs the checks and lets auto-merge proceed.
        r = gh(["pr", "update-branch", pr["url"]])
        if r.returncode != 0:
            print(f"PR for {tag} is open but cannot be updated with main "
                  f"({pr['url']}): {r.stderr.strip()}")
            return 1
        print(f"PR for {tag} already open ({pr['url']}): {r.stdout.strip()}")
        return 0

    edit_pkgbuild("PKGBUILD", tag, version, commit, checksum, pkgrel)
    edit_aur_pkgbuild("aur/PKGBUILD", version, pkgrel)
    regen_srcinfo("aur")

    branch = f"bump/{tag}"
    gh_repo = os.environ["GH_REPO"]
    push_url = f"https://x-access-token:{os.environ['GH_TOKEN']}@github.com/{gh_repo}.git"

    # -B (not -b): a previous run may have left the branch behind after
    # failing further down, and re-runs must not die on "branch exists".
    run(["git", "checkout", "-B", branch])
    run(["git", "config", "user.email", "jabla@users.noreply.github.com"])
    run(["git", "config", "user.name", "hermes-agent-bin CI"])
    run(["git", "add", "PKGBUILD", "aur/PKGBUILD", "aur/.SRCINFO"])
    r = run(["git", "commit", "-m", f"chore: bump to {tag} (v{full_version})"])
    if r.returncode != 0:
        print("commit failed:", r.stderr)
        return 1
    # --force: this branch is owned by the bump job and only ever carries this
    # one bump commit; retries after a partial run must be able to reset it.
    # No -u: it would store the token-bearing push URL in .git/config.
    r = run(["git", "push", "--force", push_url, f"HEAD:{branch}"])
    if r.returncode != 0:
        print("push failed:", r.stderr)
        return 1

    body = (f"Automated bump to upstream [release {tag}]"
            f"(https://github.com/{REPO}/releases/tag/{tag}).\n\n"
            "Build + smoke run as required checks; auto-merge after green.")
    if drift:
        body += (f"\n\n**Drift from {REFERENCE}** (review before or after the merge):\n"
                 + "\n".join(f"- {line}" for line in drift))
    r = gh(["pr", "create", "--base", "main", "--head", branch,
            "--title", f"chore: bump to {tag} (v{full_version})",
            "--body", body])
    if r.returncode != 0:
        print("pr create failed:", r.stderr)
        return 1
    pr_url = r.stdout.strip().splitlines()[-1]
    print(pr_url)

    r = gh(["pr", "merge", pr_url, "--auto", "--squash"])
    if r.returncode != 0:
        print("auto-merge enable failed:", r.stderr)
        return 1
    print("auto-merge enabled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
