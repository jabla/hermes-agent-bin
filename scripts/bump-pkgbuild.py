#!/usr/bin/env python3
"""Bump hermes-agent-bin to the latest upstream release.

Two modes:
  * default (dry run): report what a bump would change, write nothing.
  * --pr: create branch + commit (PKGBUILD, aur/PKGBUILD, aur/.SRCINFO),
    push it and open an auto-merge PR. Never commits to main directly.

Exits 0 without changes when PKGBUILD already tracks the latest upstream tag.
Requires: gh (GH_TOKEN + GH_REPO env), makepkg available for .SRCINFO regen.
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


def api(path: str):
    req = urllib.request.Request(
        "https://api.github.com" + path,
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "hermes-agent-arch-builder"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=600) as r:
        return r.read()


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


SHA_RE = re.compile(r"^sha256sums=\('([0-9a-f]{64})'", re.M)


def edit_pkgbuild(path: str, tag: str, version: str, commit: str, checksum: str):
    """Edit the GitHub build PKGBUILD (has _pkgver_tag/_commit)."""
    pkg = open(path).read()
    pkg = re.sub(r"(?m)^_pkgver_tag=.*$", f"_pkgver_tag={tag}", pkg)
    pkg = re.sub(r"(?m)^_commit=.*$", f"_commit={commit}", pkg)
    pkg = re.sub(r"(?m)^pkgver=.*$", f"pkgver={version}", pkg)
    pkg = re.sub(r"(?m)^pkgrel=.*$", "pkgrel=1", pkg)
    pkg = SHA_RE.sub(f"sha256sums=('{checksum}'", pkg)
    open(path, "w").write(pkg)


def edit_aur_pkgbuild(path: str, version: str, checksum: str):
    """Edit the AUR wrapper PKGBUILD (no _pkgver_tag/_commit; source URL is
    variable-driven and follows pkgver/pkgrel automatically)."""
    pkg = open(path).read()
    pkg = re.sub(r"(?m)^pkgver=.*$", f"pkgver={version}", pkg)
    pkg = re.sub(r"(?m)^pkgrel=.*$", "pkgrel=1", pkg)
    pkg = SHA_RE.sub(f"sha256sums=('{checksum}'", pkg)
    open(path, "w").write(pkg)


def regen_srcinfo(aur_dir: str):
    r = run(["makepkg", "--printsrcinfo"], cwd=aur_dir)
    if r.returncode != 0:
        print("makepkg --printsrcinfo failed:", r.stderr)
        sys.exit(1)
    with open(os.path.join(aur_dir, ".SRCINFO"), "w") as f:
        f.write(r.stdout)


def gh(args: list[str]) -> subprocess.CompletedProcess:
    return run(["gh", *args])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pr", action="store_true",
                    help="push bump branch and open auto-merge PR")
    args = ap.parse_args()

    rel = api(f"/repos/{REPO}/releases/latest")
    tag = rel["tag_name"]
    m = re.search(r"\bv(\d+\.\d+\.\d+)\b", rel.get("name") or "")
    if not m:
        print(f"cannot parse version from release name: {rel.get('name')!r}")
        return 2
    version = m.group(1)

    pkg = open("PKGBUILD").read()
    cur_tag = re.search(r"(?m)^_pkgver_tag=(.+)$", pkg).group(1)
    if cur_tag == tag:
        print(f"PKGBUILD already at latest tag {tag}, nothing to do")
        return 0

    ref = api(f"/repos/{REPO}/git/refs/tags/{tag}")
    obj = ref["object"]
    commit = obj["sha"]
    if obj["type"] == "tag":
        commit = api(f"/repos/{REPO}/git/tags/{commit}")["object"]["sha"]

    checksum = hashlib.sha256(
        fetch(f"https://github.com/{REPO}/archive/refs/tags/{tag}.tar.gz")
    ).hexdigest()
    print(f"upstream tag={tag} version={version} commit={commit} sha256={checksum}")

    if not args.pr:
        print("dry run: no files changed (use --pr to open the bump PR)")
        return 0

    # No PR yet open for this tag?
    existing = gh(["pr", "list", "--state", "open",
                   "--search", f"in:title \"chore: bump to {tag}\"",
                   "--json", "number"])
    if existing.returncode == 0 and json.loads(existing.stdout):
        print(f"PR for {tag} already open, nothing to do")
        return 0

    edit_pkgbuild("PKGBUILD", tag, version, commit, checksum)
    edit_aur_pkgbuild("aur/PKGBUILD", version, checksum)
    regen_srcinfo("aur")

    branch = f"bump/{tag}"
    gh_repo = os.environ["GH_REPO"]
    push_url = f"https://x-access-token:{os.environ['GH_TOKEN']}@github.com/{gh_repo}.git"

    run(["git", "checkout", "-b", branch])
    run(["git", "config", "user.email", "jabla@users.noreply.github.com"])
    run(["git", "config", "user.name", "hermes-agent-bin CI"])
    run(["git", "add", "PKGBUILD", "aur/PKGBUILD", "aur/.SRCINFO"])
    r = run(["git", "commit", "-m", f"chore: bump to {tag} (v{version})"])
    if r.returncode != 0:
        print("commit failed:", r.stderr)
        return 1
    r = run(["git", "push", "-u", push_url, f"HEAD:{branch}"])
    if r.returncode != 0:
        print("push failed:", r.stderr)
        return 1

    r = gh(["pr", "create", "--base", "main", "--head", branch,
            "--title", f"chore: bump to {tag} (v{version})",
            "--body",
            f"Automated bump to upstream [release {tag}]"
            f"(https://github.com/{REPO}/releases/tag/{tag}).\n\n"
            "Build + smoke run as required checks; auto-merge after green."])
    if r.returncode != 0:
        print("pr create failed:", r.stderr)
        return 1
    print(r.stdout.strip())

    r = gh(["pr", "merge", "--auto", "--squash"])
    if r.returncode != 0:
        print("auto-merge enable failed:", r.stderr)
        return 1
    print("auto-merge enabled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
