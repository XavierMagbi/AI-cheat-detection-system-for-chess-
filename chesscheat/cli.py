"""Command-line entry point.

Usage:
    python -m chesscheat.cli analyze games.pgn [--engine PATH] [--depth N]
    python -m chesscheat.cli profile games.pgn --player "Name" [...]
"""

from __future__ import annotations

import argparse
import sys

from .analyze import analyze_game, iter_games
from .engine import open_analyzer
from .profile import build_profile


def _add_engine_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--engine", help="path to a UCI engine (default: search PATH)")
    p.add_argument("--depth", type=int, default=16, help="engine search depth")
    p.add_argument("--threads", type=int, default=1, help="engine threads")


def cmd_analyze(args) -> int:
    """Analyse every game in a PGN and print per-side summaries."""
    with open_analyzer(args.engine, depth=args.depth, threads=args.threads) as az:
        for i, game in enumerate(iter_games(args.pgn), 1):
            report = analyze_game(game, az)
            print(f"\n=== Game {i}: {report.white} vs {report.black} "
                  f"({report.result}) ===")
            for side, s in (("White", report.white_summary),
                            ("Black", report.black_summary)):
                print(f"  {side:5} {report.white if side=='White' else report.black}")
                print(f"        moves={s['moves']}  ACPL={s['acpl']:.1f}  "
                      f"accuracy={s['accuracy']:.1f}  "
                      f"top-move={s['top_move_pct']:.1f}%  "
                      f"blunders={s['blunders']}")
    return 0


def cmd_profile(args) -> int:
    """Profile a single player across every game in the PGN."""
    with open_analyzer(args.engine, depth=args.depth, threads=args.threads) as az:
        reports = [analyze_game(g, az) for g in iter_games(args.pgn)]

    prof = build_profile(args.player, reports)
    print(f"\n=== Profile: {prof.name} ===")
    print(f"  games analysed : {prof.games}")
    print(f"  avg ACPL       : {prof.avg_acpl:.1f}  (stdev {prof.acpl_stdev:.1f})")
    print(f"  avg top-move % : {prof.avg_match_pct:.1f}")
    print(f"  avg accuracy   : {prof.avg_accuracy:.1f}")
    print(f"  total blunders : {prof.total_blunders}")
    print(f"\n  SUSPICION SCORE: {prof.suspicion:.0f}/100")
    print("  reasons:")
    for r in prof.reasons:
        print(f"    - {r}")
    print("\n  NOTE: this is a statistical indicator, not proof. Always have a "
          "human review the actual games before acting on an account.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="chesscheat",
        description="Chess online cheat-detection toolkit (engine + statistics).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    a = sub.add_parser("analyze", help="grade every game in a PGN")
    a.add_argument("pgn", help="path to a .pgn file")
    _add_engine_args(a)
    a.set_defaults(func=cmd_analyze)

    pr = sub.add_parser("profile", help="profile one player across many games")
    pr.add_argument("pgn", help="path to a .pgn file")
    pr.add_argument("--player", required=True, help="player name as in the PGN")
    _add_engine_args(pr)
    pr.set_defaults(func=cmd_profile)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
