#!/usr/bin/env python3
"""Print the "Upstream changes" lines of a release's notes.

The range starts at the upstream tag of the last release of this repository
that packaged a different upstream tag, not at upstream's previous release:
when a version was skipped, its changes belong to this release too. Skipped
upstream releases are listed by name.

Usage: upstream-range.py <repo> <release tag> <upstream repo> <upstream tag>
Reads through `gh api` (GH_TOKEN). Never fails: on any error it prints the
generic link to upstream's releases, so a release is never blocked by it.
"""
import base64
import json
import re
import subprocess
import sys

SEMVER_RE = re.compile(r"v(\d+)\.(\d+)\.(\d+)")


def gh_api(path: str):
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def packaged_tag(repo: str, ref: str) -> str | None:
    """_pkgver_tag of PKGBUILD at one of this repository's tags."""
    data = gh_api(f"repos/{repo}/contents/PKGBUILD?ref={ref}")
    found = re.search(r"(?m)^_pkgver_tag=(\S+)$", base64.b64decode(data["content"]).decode())
    return found.group(1) if found else None


def version(tag: str) -> tuple[int, ...] | None:
    found = SEMVER_RE.fullmatch(tag)
    return tuple(map(int, found.groups())) if found else None


def lines(repo: str, release: str, upstream: str, current: str) -> list[str]:
    ours = [r["tag_name"] for r in gh_api(f"repos/{repo}/releases?per_page=100") if not r["draft"]]
    if release in ours:              # a re-run: only the releases before it count
        ours = ours[ours.index(release) + 1:]
    base = None
    for tag in ours:
        packaged = packaged_tag(repo, tag)
        if packaged and packaged != current:
            base = packaged
            break
    published = [r["tag_name"] for r in gh_api(f"repos/{upstream}/releases?per_page=100")
                 if not r["draft"] and not r["prerelease"]]
    if base is None:                 # first release: upstream's previous one
        later = published[published.index(current) + 1:] if current in published else []
        base = later[0] if later else None
    if base is None:
        raise LookupError(f"no earlier upstream tag for {current}")
    out = [f"- [Upstream changes {base} -> {current}]"
           f"(https://github.com/{upstream}/compare/{base}...{current})"]
    low, high = version(base), version(current)
    if low and high:
        skipped = sorted((t for t in published if version(t) and low < version(t) < high), key=version)
        if skipped:
            links = ", ".join(f"[{t}](https://github.com/{upstream}/releases/tag/{t})" for t in skipped)
            noun, own = ("release", "its") if len(skipped) == 1 else ("releases", "their")
            out.append(f"- Also covers the upstream {noun} {links}, not packaged on {own} own")
    return out


def main() -> int:
    repo, release, upstream, current = sys.argv[1:5]
    try:
        print("\n".join(lines(repo, release, upstream, current)))
    except Exception as exc:         # notes are best effort, the release is not
        print(f"::warning::upstream range lookup failed: {exc}", file=sys.stderr)
        print(f"- [Upstream changes](https://github.com/{upstream}/releases)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
