#!/usr/bin/env python3
"""The AUR source package hermes-agent, generated from this repository.

usage: scripts/source-package.py              write aur-source/ from PKGBUILD
       scripts/source-package.py --check      fail when aur-source/ is stale
       scripts/source-package.py --into DIR   copy the source package into
                                              DIR, a clone of the AUR
                                              repository (staged, no commit)

PKGBUILD is a full source build: CI builds it and publishes the result for
the -bin wrapper in aur/. The AUR source package is the same PKGBUILD under
its own name, description and conflicts, with the same local files byte for
byte. aur-source/ holds its PKGBUILD, .SRCINFO and REUSE.toml. The maintainer
lines of aur-source/PKGBUILD and the rest of aur-source/REUSE.toml are kept;
everything else follows PKGBUILD.

Writing and --check need makepkg (not as root). --into needs only git: it
puts aur-source/ and the local files its REUSE.toml lists into DIR, removes
the files that DIR's previous REUSE.toml listed and the new one does not,
and leaves everything else in DIR alone (its LICENSE, .gitignore, notes).
It refuses when the last commit in DIR was not made from this repository
(OWN_EMAIL): a co-maintainer's change is read before it is overwritten.
--allow-foreign overrides that once it has been read.
"""
import argparse
import difflib
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

BINNAME = "hermes-agent-bin"
NAME = "hermes-agent"
PKGDESC = "Locally-run AI agent with tool use, web browsing, and automation"
REPO = "https://github.com/jabla/hermes-agent-bin"
ABOUT = ("Builds Hermes Agent from the upstream release tag into /opt/hermes-agent. "
         "Upstream pins a large, partly native Python dependency set; uv's "
         "relocatable venv keeps the packaged environment usable after makepkg "
         "moves it under /opt.")
# The source package is built on the user's machine, not in CI.
EDITS = [
    (r"--source ci\b", "--source aur"),         # the install stamp's provenance
    (r" \(and aur/PKGBUILD\)", ""),             # the source package has no aur/
]
# The author of every commit made from this repository in the AUR repository:
# aur-sync's CI identity and the maintainer's own pushes.
OWN_EMAIL = "jabla@users.noreply.github.com"

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "aur-source"
GENERATED = ("PKGBUILD", ".SRCINFO", "REUSE.toml")


def die(msg):
    sys.exit(f"source-package: {msg}")


def sub(text, pattern, repl, count=1):
    """Replace pattern by the literal repl exactly count times."""
    new, n = re.subn(pattern, lambda _m: repl, text, flags=re.M)
    if n != count:
        die(f"{n} matches for {pattern!r} in PKGBUILD, expected {count}")
    return new


def wrap(text, width):
    lines, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}" if line else word
    return lines + [line] if line else lines


def local_files(pkgbuild):
    """The local entries of source=() in their order (no URL, no rename)."""
    block = re.search(r"^source=\(\n((?:[ \t]+.*\n)*)\)$", pkgbuild, re.M)
    if not block:
        die("PKGBUILD has no multi-line source=( ... ) array")
    entries = re.findall(r"""^[ \t]+(['"])(.+)\1$""", block.group(1), re.M)
    return [e for _q, e in entries if "::" not in e and "/" not in e]


def reuse_paths(text):
    m = re.search(r"^path = \[\n((?:    .*\n)*)\]$", text, re.M)
    if not m:
        die("REUSE.toml has no path = [ ... ] list")
    return re.findall(r'^    "(.+)",$', m.group(1), re.M)


def printsrcinfo(pkgbuild):
    with tempfile.TemporaryDirectory() as tmp:
        pathlib.Path(tmp, "PKGBUILD").write_text(pkgbuild, encoding="utf-8")
        r = subprocess.run(["makepkg", "--printsrcinfo"], cwd=tmp,
                           capture_output=True, text=True)
    if r.returncode != 0:
        die(f"makepkg --printsrcinfo failed:\n{r.stderr}")
    return r.stdout


def generate():
    """aur-source/ as PKGBUILD gives it: {file name: text}."""
    try:
        old = (OUT / "PKGBUILD").read_text(encoding="utf-8")
        reuse = (OUT / "REUSE.toml").read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        die(f"{exc.filename} is missing: aur-source/ starts as a copy of the "
            f"AUR repository {NAME}")
    text = (ROOT / "PKGBUILD").read_text(encoding="utf-8")
    shared = local_files(text)

    # The AUR package's own maintainer lines stay; never invent any.
    people = re.findall(r"^# (?:Maintainer|Co-maintainer|Contributor):.*$", old, re.M)
    about = (f"{ABOUT} The local files ({', '.join(shared)}) are the same files "
             f"as in {BINNAME}, whose CI builds this PKGBUILD under that name "
             f"({REPO}).")
    header = "".join(f"{line}\n" for line in people)
    header += "".join(f"# {line}\n" for line in wrap(about, 77))

    text = sub(text, r"\A(?:#.*\n)+(?=pkgname=)", header)
    text = sub(text, rf"^pkgname={re.escape(BINNAME)}$", f"pkgname={NAME}")
    text = sub(text, r'^pkgdesc=".*"$', f'pkgdesc="{PKGDESC}"')
    text = sub(text, r"^provides=\(.*\)\n", "")
    text = sub(text, rf"^conflicts=\('{re.escape(NAME)}'\)$", f"conflicts=('{BINNAME}')")
    for pattern, repl in EDITS:
        text = sub(text, pattern, repl)
    if BINNAME in re.sub(r"^(#|conflicts=).*$", "", text, flags=re.M):
        die(f"{BINNAME} is still named outside comments and conflicts")

    srcinfo = printsrcinfo(text)
    listed = [s for s in re.findall(r"^\tsource = (.+)$", srcinfo, re.M) if "://" not in s]
    if listed != shared:
        die(f".SRCINFO lists the local files {listed}, source=() {shared}")
    paths = "".join(f'    "{f}",\n' for f in ["PKGBUILD", ".SRCINFO", "LICENSE",
                                                 "REUSE.toml", *shared])
    reuse = sub(reuse, r"^path = \[\n(?:    .*\n)*\]$", f"path = [\n{paths}]")
    return {"PKGBUILD": text, ".SRCINFO": srcinfo, "REUSE.toml": reuse}


def write():
    for name, text in generate().items():
        (OUT / name).write_text(text, encoding="utf-8")
    print(f"source-package: aur-source/ is PKGBUILD as {NAME}")


def check():
    stale = False
    for name, text in generate().items():
        current = (OUT / name).read_text(encoding="utf-8")
        if current != text:
            stale = True
            sys.stdout.writelines(difflib.unified_diff(
                current.splitlines(keepends=True), text.splitlines(keepends=True),
                f"aur-source/{name}", f"aur-source/{name} (from PKGBUILD)"))
    if stale:
        die("aur-source/ does not match PKGBUILD: run scripts/source-package.py "
            "and commit aur-source/")
    print("source-package: aur-source/ matches PKGBUILD")


def git(dst, *args, **kw):
    return subprocess.run(["git", "-C", str(dst), *args], text=True, **kw)


def into(dst, allow_foreign):
    dst = pathlib.Path(dst)
    if git(dst, "rev-parse", "--git-dir", capture_output=True).returncode:
        die(f"{dst} is not a git repository")
    last = git(dst, "log", "-1", "--format=%ae%x00%h %an <%ae>: %s", capture_output=True)
    if last.returncode == 0:            # a new, empty AUR repository has no log
        email, commit = last.stdout.rstrip("\n").split("\0", 1)
        if email != OWN_EMAIL and not allow_foreign:
            die(f"the last commit in {dst} was not made from this repository:\n"
                f"  {commit}\nRead it and port what applies to PKGBUILD, then "
                f"rerun with --allow-foreign.")

    new = reuse_paths((OUT / "REUSE.toml").read_text(encoding="utf-8"))
    previous = dst / "REUSE.toml"
    old = reuse_paths(previous.read_text(encoding="utf-8")) if previous.exists() else []
    gone = [f for f in old if f not in new]
    if gone:
        git(dst, "rm", "-q", "-f", "--ignore-unmatch", "--", *gone, check=True)
        for f in gone:
            (dst / f).unlink(missing_ok=True)
    copied = []
    for f in new:
        if f == "LICENSE" and (dst / f).exists():
            continue                    # the AUR repository's own license file
        shutil.copyfile(OUT / f if f in GENERATED else ROOT / f, dst / f)
        copied.append(f)
    git(dst, "add", "--", *copied, check=True)
    print(f"source-package: {dst} holds aur-source/ and its local files (staged)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true",
                      help="fail when aur-source/ is not what PKGBUILD gives")
    mode.add_argument("--into", metavar="DIR",
                      help="copy the source package into DIR, a clone of the AUR repository")
    ap.add_argument("--allow-foreign", action="store_true",
                    help="with --into: overwrite although the last commit in DIR is someone else's")
    args = ap.parse_args()
    if args.allow_foreign and not args.into:
        ap.error("--allow-foreign needs --into")
    if args.into:
        into(args.into, args.allow_foreign)
    elif args.check:
        check()
    else:
        write()


if __name__ == "__main__":
    main()
