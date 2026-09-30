"""Build fingerprints.

- data fingerprint: processed Parquet + status.json + manual CSVs.
- build fingerprint: data + everything that shapes the site (site/, ingest/, registry/, lockfiles).

The deployed site publishes its build fingerprint at /fingerprint.txt. CI compares against
that (the *last successful deploy*), so a failed deploy is retried on the next run.

Usage:
  python -m ingest.fingerprint                 # print build fingerprint
  python -m ingest.fingerprint --data          # print data fingerprint
  python -m ingest.fingerprint --clear-stale-cache
      clear site/src/.observablehq/cache if the data fingerprint changed since the cache was filled
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_GLOBS = ["data/parquet/**/*.parquet", "data/status.json", "data/manual/**/*.csv"]
CODE_GLOBS = [
    "ingest/**/*.py",
    "registry/**/*",
    "site/src/**/*",
    "site/observablehq.config.js",
    "site/package.json",
    "site/package-lock.json",
    "pyproject.toml",
    "uv.lock",
]
EXCLUDE_PARTS = {".observablehq", "node_modules", "dist", "__pycache__"}
CACHE_DIR = ROOT / "site" / "src" / ".observablehq" / "cache"
CACHE_STAMP = CACHE_DIR / ".data-fingerprint"


def _files(globs: Iterable[str], root: Path) -> list[Path]:
    out = set()
    for g in globs:
        for p in root.glob(g):
            if p.is_file() and not EXCLUDE_PARTS & set(p.relative_to(root).parts):
                out.add(p)
    return sorted(out)


def fingerprint(globs: Iterable[str], root: Path = ROOT) -> str:
    h = hashlib.sha256()
    for p in _files(globs, root):
        h.update(p.relative_to(root).as_posix().encode())
        h.update(b"\0")
        h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


def data_fingerprint(root: Path = ROOT) -> str:
    return fingerprint(DATA_GLOBS, root)


def build_fingerprint(root: Path = ROOT) -> str:
    return fingerprint([*DATA_GLOBS, *CODE_GLOBS], root)


def clear_stale_cache(cache_dir: Path = CACHE_DIR, root: Path = ROOT) -> bool:
    """Observable reuses loader output without noticing input Parquet changes. Returns True if cleared."""
    stamp = cache_dir / ".data-fingerprint"
    current = data_fingerprint(root)
    if stamp.exists() and stamp.read_text().strip() == current:
        return False
    cache_dir.mkdir(parents=True, exist_ok=True)
    for child in cache_dir.iterdir():
        if child.name == "_npm":  # third-party modules, not derived from our data
            continue
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    stamp.write_text(current + "\n")
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--data", action="store_true")
    g.add_argument("--clear-stale-cache", action="store_true")
    args = ap.parse_args()
    if args.clear_stale_cache:
        print("loader cache cleared" if clear_stale_cache() else "loader cache up to date")
    elif args.data:
        print(data_fingerprint())
    else:
        print(build_fingerprint())


if __name__ == "__main__":
    main()
