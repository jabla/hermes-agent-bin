#!/usr/bin/env python3
"""Bump hermes-agent-bin to the latest upstream release.

Two modes:
  * default (dry run): report what a bump would change, write nothing.
  * --pr: create branch + commit (PKGBUILD, aur/PKGBUILD, aur/.SRCINFO and
    the AUR source package in aur-source/), push it and open an auto-merge
    PR. Never commits to main directly.

A bump also lists the optional-dependency extras that changed upstream,
against the --extra lists PKGBUILD installs, and moves the pnpm the build
downloads to upstream's pin (pm/lock.json).

Exits 0 without changes when PKGBUILD already tracks the latest upstream tag.
Requires: gh (GH_TOKEN + GH_REPO env), makepkg available for .SRCINFO regen,
vercmp (pacman) for the version order. UPSTREAM_API_TOKEN, when set,
authenticates the GitHub API reads.
Must not run as root: makepkg refuses to run as root, so the container job
runs this script through runuser as an unprivileged user.
"""
import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tomllib
import urllib.request

REPO = "NousResearch/hermes-agent"
SHA_RE = re.compile(r"^sha256sums=\('([0-9a-f]{64})'", re.M)
# The extras build() installs: every `--extra a,b,c` in PKGBUILD.
EXTRA_ARG_RE = re.compile(r"--extra[ =]([\w.,-]+)")
# An extra that pulls in others: "hermes-agent[a,b]".
SELF_REF_RE = re.compile(r"hermes-agent\s*\[([^\]]*)\]")

# pnpm as PKGBUILD downloads it (source_x86_64=()): the linux-x64 artifacts of
# upstream's pin in pm/lock.json, the @pnpm/exe executable, then the launcher
# package.
PNPM_URLS = ("https://registry.npmjs.org/@pnpm/exe.linux-x64/-/exe.linux-x64-{v}.tgz",
             "https://registry.npmjs.org/pnpm/-/pnpm-{v}.tgz")
PNPM_VAR_RE = re.compile(r"(?m)^_pnpmver=(\S+)")
PNPM_SUMS_RE = re.compile(r"(?ms)^sha256sums_x86_64=\(.*?\)")


def tarball_file(tarball: bytes, name: str) -> bytes:
    """A file of upstream's archive, by its path below the top directory."""
    with tarfile.open(fileobj=io.BytesIO(tarball)) as tar:
        for member in tar:
            if member.isfile() and member.name.partition("/")[2] == name:
                return tar.extractfile(member).read()
    raise KeyError(f"the upstream archive has no {name}")


def pnpm_pin(tarball: bytes) -> tuple[str, list[str]]:
    """Upstream's pnpm pin (pm/lock.json): its version and the sha256 digests
    of the two linux-x64 artifacts, in source_x86_64=() order."""
    pin = json.loads(tarball_file(tarball, "pm/lock.json"))["packages"]["pnpm"]
    version = pin["version"]
    sums = {a["url"]: a["sha256"] for a in pin["artifacts"]["linux-x64"]}
    urls = [url.format(v=version) for url in PNPM_URLS]
    if sorted(sums) != sorted(urls):
        sys.exit(f"pm/lock.json pins pnpm {version} as {sorted(sums)}, "
                 f"PKGBUILD downloads {urls}")
    return version, [sums[url] for url in urls]


def edit_pnpm(path: str, version: str, sums: list[str]):
    """Write upstream's pnpm pin into PKGBUILD (_pnpmver, sha256sums_x86_64)."""
    pkg = open(path).read()
    pkg, n = PNPM_VAR_RE.subn(f"_pnpmver={version}", pkg)
    block = "sha256sums_x86_64=(" + "\n                   ".join(f"'{s}'" for s in sums) + ")"
    pkg, m = PNPM_SUMS_RE.subn(lambda _m: block, pkg)
    if n != 1 or m != 1:
        sys.exit(f"cannot write the pnpm pin into {path} "
                 f"({n} _pnpmver= lines, {m} sha256sums_x86_64= arrays)")
    open(path, "w").write(pkg)


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


def upstream_extras(tag: str) -> dict[str, list[str]]:
    """{extra: requirement strings} of upstream's pyproject.toml at tag."""
    text = fetch(f"https://raw.githubusercontent.com/{REPO}/{tag}/pyproject.toml").decode()
    return tomllib.loads(text)["project"].get("optional-dependencies", {})


def requirement_names(reqs: list[str]) -> set[str]:
    """Package names only: version bumps are uv.lock's business, while a new
    package can need a system library (python-olm needs cmake)."""
    return {re.split(r"[\s<>=!~;\[(@]", req.strip(), maxsplit=1)[0].lower().replace("_", "-")
            for req in reqs if not SELF_REF_RE.match(req.strip())}


def installed_extras(extras: dict[str, list[str]], selected: set[str]) -> set[str]:
    """selected plus every extra they pull in through hermes-agent[...]."""
    seen, todo = set(), list(selected)
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        for req in extras.get(name, []):
            ref = SELF_REF_RE.match(req.strip())
            if ref:
                todo += [n.strip() for n in ref.group(1).split(",") if n.strip()]
    return seen


def extras_report(pkgbuild: str, cur_tag: str, tag: str) -> list[str]:
    """What changed in upstream's extras between cur_tag and tag that the
    package has to follow: PKGBUILD installs a fixed --extra list and smoke
    imports a fixed set, so a new or changed extra goes unnoticed otherwise.
    Best effort: a failed lookup warns and never blocks the bump."""
    try:
        old, new = upstream_extras(cur_tag), upstream_extras(tag)
    except Exception as exc:
        print(f"::warning::extras check skipped: {exc}")
        return []
    selected = {name for m in EXTRA_ARG_RE.finditer(pkgbuild)
                for name in m.group(1).split(",") if name}
    installed = installed_extras(new, selected)
    lines = []
    for name in sorted(selected - new.keys()):
        lines.append(f"`{name}` is in PKGBUILD's --extra list but gone upstream: "
                     "the build fails until it is removed")
    for name in sorted(new.keys() - old.keys()):
        state = "installed" if name in installed else "not installed"
        lines.append(f"new extra `{name}` ({state}): "
                     f"{', '.join(sorted(requirement_names(new[name]))) or 'no packages of its own'}")
    for name in sorted(old.keys() - new.keys() - selected):
        lines.append(f"extra `{name}` removed upstream")
    for name in sorted(installed & old.keys() & new.keys()):
        before, after = requirement_names(old[name]), requirement_names(new[name])
        if before != after:
            change = [f"+{n}" for n in sorted(after - before)] + [f"-{n}" for n in sorted(before - after)]
            lines.append(f"installed extra `{name}` changed packages: {' '.join(change)}")
    for line in lines:
        print(f"extras: {line}")
    if not lines:
        print(f"extras: nothing to follow between {cur_tag} and {tag}")
    return lines


def gh(args: list[str]) -> subprocess.CompletedProcess:
    return run(["gh", *args])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pr", action="store_true",
                    help="push bump branch and open auto-merge PR")
    args = ap.parse_args()

    require_non_root()

    rel = api(f"/repos/{REPO}/releases/latest")
    tag = rel["tag_name"]
    # Up to v0.21.5 upstream tagged by date and named releases "Hermes Agent
    # v0.21.3 (v2026.9.14)"; since v0.21.6 the tag is the version itself and
    # the name reads "Hermes Agent v0.21.6". Take the first vX.Y.Z in the name
    # that is not the date tag, whatever order upstream uses.
    date_tag = re.fullmatch(r"v(\d{4}\.\d+\.\d+(?:\.\d+)?)", tag)
    candidates = [v for v in re.findall(r"\bv(\d+\.\d+\.\d+)\b", rel.get("name") or "")
                  if not (date_tag and date_tag.group(1).startswith(v))]
    if not candidates:
        print(f"cannot parse version from release name: {rel.get('name')!r}")
        return 2
    version = candidates[0]
    if not date_tag and tag != f"v{version}":
        print(f"release name {rel.get('name')!r} does not match its tag {tag}")
        return 2

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

    tarball = fetch(f"https://github.com/{REPO}/archive/refs/tags/{tag}.tar.gz")
    checksum = hashlib.sha256(tarball).hexdigest()
    print(f"upstream tag={tag} version={version} pkgrel={pkgrel} commit={commit} "
          f"sha256={checksum}")
    pnpm_version, pnpm_sums = pnpm_pin(tarball)
    cur_pnpm = PNPM_VAR_RE.search(pkg).group(1)
    pnpm_move = f"pnpm pin {cur_pnpm} -> {pnpm_version}" if pnpm_version != cur_pnpm else ""
    print(f"upstream pins pnpm {pnpm_version}" + (f": {pnpm_move}" if pnpm_move else ", as PKGBUILD"))
    extras = extras_report(pkg, cur_tag, tag)

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
    edit_pnpm("PKGBUILD", pnpm_version, pnpm_sums)
    edit_aur_pkgbuild("aur/PKGBUILD", version, pkgrel)
    regen_srcinfo("aur")
    # The AUR source package follows PKGBUILD (scripts/source-package.py).
    r = run([sys.executable, "-I", "scripts/source-package.py"])
    if r.returncode != 0:
        print("source-package.py failed:", r.stdout, r.stderr)
        return 1

    branch = f"bump/{tag}"
    gh_repo = os.environ["GH_REPO"]
    push_url = f"https://x-access-token:{os.environ['GH_TOKEN']}@github.com/{gh_repo}.git"

    # -B (not -b): a previous run may have left the branch behind after
    # failing further down, and re-runs must not die on "branch exists".
    run(["git", "checkout", "-B", branch])
    run(["git", "config", "user.email", "jabla@users.noreply.github.com"])
    run(["git", "config", "user.name", "hermes-agent-bin CI"])
    run(["git", "add", "PKGBUILD", "aur/PKGBUILD", "aur/.SRCINFO", "aur-source"])
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
            "Build, smoke and wrapper run as required checks; auto-merge after green.")
    if pnpm_move:
        body += f"\n\nFollows upstream's {pnpm_move} (pm/lock.json)."
    if extras:
        body += ("\n\n**Extras changed upstream** (follow them in the `--extra` lists of "
                 "PKGBUILD and the extras that smoke imports):\n"
                 + "\n".join(f"- {line}" for line in extras))
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
