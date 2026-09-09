#!/usr/bin/env python3
"""Stage the repository's Markdown into a tree MkDocs can build from.

Why this exists at all
----------------------
The documentation in this repo is written to be read *on GitHub*: README.md
and the four project docs live at the repository root, the deployment guides
live beside the scripts they describe, and the per-project testing
walkthroughs live under docs/. That layout is deliberate - a deploy script's
README should sit next to the script - and it is the layout every relative
link in those files already assumes.

MkDocs wants a single `docs_dir`. The obvious fix, moving everything into
docs/, would break every one of those relative links for anyone reading the
repo on GitHub, which is still the primary way people read it.

So instead this script copies the Markdown into a staging tree **preserving
each file's repository-relative path**. That one property is what makes the
whole thing work: MkDocs rewrites relative `.md` links to their built URLs
automatically, so a link like `[SETUP.md](SETUP.md)` in README.md, or
`[../CLOUDSHELL.md](../CLOUDSHELL.md)` in a deploy README, resolves correctly
in the built site *and* on GitHub, with no rewriting and no plugin.

The one addition is `index.md`, a copy of README.md, because MkDocs needs a
homepage at the docs root.

Usage
-----
    python scripts/build_docs.py            # stage only
    python scripts/build_docs.py --serve    # stage, then `mkdocs serve`
    python scripts/build_docs.py --build    # stage, then `mkdocs build --strict`

The staging directory is disposable and gitignored; it is rebuilt from
scratch every run so a deleted source file cannot linger in the site.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STAGE_DIR = REPO_ROOT / ".mkdocs-build" / "docs"

# Root-level documents, copied to the staging root under the same names.
# README.md is deliberately absent: it is staged as index.md instead (below).
# Staging it under both names makes MkDocs exclude one as a conflict. Nothing
# in the docs links to a root README.md, so nothing breaks by omitting it.
ROOT_DOCS = [
    "SETUP.md",
    "TESTING.md",
    "BIDWRIGHT.md",
    "CLAIMCLARITY.md",
    "GLACIERWATCH.md",
    "TRINETRA.md",
]

# Directories copied wholesale, preserving their paths. Screenshots come along
# so image links keep working; the SSML files do not, since they are inputs to
# a speech synthesiser rather than anything to read on a docs site.
COPY_DIRS = ["docs", "deploy"]

COPY_SUFFIXES = {".md", ".png", ".jpg", ".jpeg", ".svg", ".gif"}


def stage() -> int:
    if STAGE_DIR.exists():
        shutil.rmtree(STAGE_DIR)
    STAGE_DIR.mkdir(parents=True)

    copied = 0

    for name in ROOT_DOCS:
        src = REPO_ROOT / name
        if not src.exists():
            print(f"  WARNING: {name} is listed in ROOT_DOCS but does not exist", file=sys.stderr)
            continue
        shutil.copy2(src, STAGE_DIR / name)
        copied += 1

    # MkDocs needs a homepage at the docs root.
    readme = REPO_ROOT / "README.md"
    if readme.exists():
        shutil.copy2(readme, STAGE_DIR / "index.md")

    for dirname in COPY_DIRS:
        src_dir = REPO_ROOT / dirname
        if not src_dir.is_dir():
            print(f"  WARNING: {dirname}/ does not exist", file=sys.stderr)
            continue
        for src in sorted(src_dir.rglob("*")):
            if not src.is_file() or src.suffix.lower() not in COPY_SUFFIXES:
                continue
            dest = STAGE_DIR / src.relative_to(REPO_ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            copied += 1

    print(f"Staged {copied} files into {STAGE_DIR.relative_to(REPO_ROOT)}")
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--serve", action="store_true", help="stage, then run `mkdocs serve`")
    parser.add_argument("--build", action="store_true", help="stage, then run `mkdocs build --strict`")
    args = parser.parse_args()

    if stage() == 0:
        print("Nothing was staged - refusing to continue.", file=sys.stderr)
        return 1

    # Invoked as `sys.executable -m mkdocs` rather than a bare "mkdocs" so this
    # works when the script is run through a virtualenv's interpreter without
    # that virtualenv's bin/ being on PATH - which is exactly how you would run
    # it as `.venv/bin/python scripts/build_docs.py`.
    if args.serve:
        return subprocess.call([sys.executable, "-m", "mkdocs", "serve"], cwd=REPO_ROOT)
    if args.build:
        # --strict turns broken internal links and other warnings into errors,
        # so a docs build fails loudly rather than publishing a broken site.
        return subprocess.call([sys.executable, "-m", "mkdocs", "build", "--strict"], cwd=REPO_ROOT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
