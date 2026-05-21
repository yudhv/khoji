#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from urllib.request import urlopen


DEFAULT_URL = (
    "https://github.com/shabados/database/releases/download/4.8.7/database.sqlite"
)
DEFAULT_OUTPUT = Path("data/shabados/database.sqlite")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download the stable Shabad OS SQLite database for local imports."
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(args.url) as response, args.output.open("wb") as output:
        total = int(response.headers.get("content-length", "0"))
        copied = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
            copied += len(chunk)
            if total:
                percent = copied / total * 100
                print(f"\rDownloaded {copied / 1024 / 1024:.1f} MiB ({percent:.1f}%)", end="")
        print()

    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

