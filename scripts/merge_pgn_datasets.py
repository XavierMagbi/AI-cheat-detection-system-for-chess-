"""Merge PGN datasets while preserving complete game records.

The merger de-duplicates games by the Lichess ``GameURL`` header when present.
If a game has no ``GameURL``, it falls back to a hash of the full PGN record.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


HEADER_RE = re.compile(r'^\[(?P<name>[A-Za-z0-9_]+)\s+"(?P<value>.*)"\]\s*$')


def iter_pgn_games(path: Path):
    """Yield complete PGN game blocks from ``path``."""
    current: list[str] = []

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith("[Event ") and current:
                yield "".join(current).strip()
                current = []
            current.append(line)

    if current:
        game = "".join(current).strip()
        if game:
            yield game


def parse_headers(game: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for line in game.splitlines():
        if not line.startswith("["):
            break
        match = HEADER_RE.match(line)
        if match:
            headers[match.group("name")] = match.group("value")
    return headers


def game_key(game: str) -> str:
    headers = parse_headers(game)
    game_url = headers.get("GameURL")
    if game_url:
        return f"gameurl:{game_url}"
    digest = hashlib.sha256(game.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def merge_pgns(inputs: list[Path], output: Path) -> dict:
    seen: set[str] = set()
    summary = {
        "output": str(output),
        "sources": [],
        "input_games": 0,
        "written_games": 0,
        "duplicate_games": 0,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as out:
        for source in inputs:
            source_stats = {
                "path": str(source),
                "input_games": 0,
                "written_games": 0,
                "duplicate_games": 0,
            }
            for game in iter_pgn_games(source):
                source_stats["input_games"] += 1
                summary["input_games"] += 1

                key = game_key(game)
                if key in seen:
                    source_stats["duplicate_games"] += 1
                    summary["duplicate_games"] += 1
                    continue

                seen.add(key)
                out.write(game)
                out.write("\n\n\n")
                source_stats["written_games"] += 1
                summary["written_games"] += 1

            summary["sources"].append(source_stats)

    summary_path = output.with_suffix(output.suffix + ".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge PGN datasets with de-duplication.")
    parser.add_argument("output", type=Path)
    parser.add_argument("inputs", nargs="+", type=Path)
    args = parser.parse_args()

    summary = merge_pgns(args.inputs, args.output)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
