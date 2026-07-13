"""Command-line entry point.

Usage:
    python -m chesscheat.cli analyze games.pgn [--engine PATH] [--depth N]
    python -m chesscheat.cli profile games.pgn --player "Name" [...]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .analyze import analyze_game, iter_games
from .engine import open_analyzer
from .profile import build_profile, benchmarking, benchmark_path_for_elo_range





ELO_RANGES = [
    [600,799],
    [800, 999],
    [1000, 1199],
    [1200, 1399],
    [1400, 1599],
    [1600, 1799],
    [1800, 1999],
    [2000, 2199],
    [2200, 2399],
    [2400, 2599],
    [2600, 2799],
    [2800, 2999],
]



def _add_engine_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--engine", help="path to a UCI engine (default: search PATH)")
    p.add_argument("--depth", type=int, default=10, help="engine search depth")
    p.add_argument("--threads", type=int, default=8, help="engine threads")
    p.add_argument("--nb_game", type=int, default=80, help="number of game selected in the dataset")
    


def cmd_analyze(args) -> int:
    """Analyse every game in a PGN and print per-side summaries."""
    with open_analyzer(args.engine, depth=args.depth, threads=args.threads) as az:
        for i, game in enumerate(iter_games(args.pgn), 1):
            report = analyze_game(game, az)
            print(f"\n=== Game {i}: {report.white} vs {report.black} "
                    f"({report.result}) ===")
            for side, s in (("White", report.white_summary),("Black", report.black_summary)):
                print(f"  {side:5} {report.white  if side=='White' else report.black}")
                if side=='White' : 
                    print (f" ELO : {report.elo_white} ")
                else : 
                    print (f" ELO : {report.elo_black} ")
                print(f"moves={s['moves']}  ACPL={s['acpl']:.1f} "
                        f"accuracy={s['accuracy']:.1f} "
                        f"top-move={s['top_move_pct']:.1f}% "
                        f"blunders={s['blunders']}")
            if i >= args.nb_game:
                break
        
    return 0

def cmd_single_benchmark(args)->int:
    low, high = args.elo_range
    reports = []
    start_time = time.perf_counter()

    with open_analyzer(
        args.engine,
        depth=args.depth,
        threads=args.threads,
    ) as az:
        for game in iter_games(args.pgn):
            headers = game.headers

            try:
                white_elo = int(headers.get("WhiteElo", 0))
                black_elo = int(headers.get("BlackElo", 0))
            except (TypeError, ValueError):
                continue

            white_matches = low <= white_elo < high
            black_matches = low <= black_elo < high

            # Crucially, skip before invoking Stockfish
            if not white_matches and not black_matches:
                continue

            reports.append(analyze_game(game, az))
            
            

            if len(reports) >= args.nb_game:
                break

    inference_seconds = time.perf_counter() - start_time
    output_path = benchmark_path_for_elo_range(args.elo_range,reports)
    result = benchmarking(
        args.elo_range,
        reports,
        inference_seconds=inference_seconds,
        output_path=output_path,
    )
    if result is None:
        print(f"\n=== ELO Benchmark: {low}–{high} ===")
        print("  skipped: no analysable player sides found")
        return 0

    print(f"\n=== ELO Benchmark: {low}–{high} ===")
    print(f"  games analysed      : {result['games_analyzed']}")
    print(f"  player-side samples : {result['player_side_samples']}")
    print(f"  inference time      : {result['inference_seconds']:.2f}s")
    print(f"  saved to            : {output_path}")
    
    
    return 0


def cmd_general_benchmark(args)->int:
    
    total_time = 0
    
    for elo_range in ELO_RANGES :
        low, high = elo_range
        reports = []
        start_time = time.perf_counter()
        
        with open_analyzer(
            args.engine,
            depth=args.depth,
            threads=args.threads,
        ) as az:
            for game in iter_games(args.pgn):
                headers = game.headers
                
                try:
                    white_elo = int(headers.get("WhiteElo", 0))
                    black_elo = int(headers.get("BlackElo", 0))
                    
                except (TypeError, ValueError):
                    continue
                
                white_matches = low <= white_elo < high
                black_matches = low <= black_elo < high
                
                 
                    
                
                # Crucially, skip before invoking Stockfish
                if not white_matches and not black_matches:
                    continue
                
                reports.append(analyze_game(game, az))
                if len(reports) >= args.nb_game:
                    break

            inference_seconds = time.perf_counter() - start_time
            output_path = benchmark_path_for_elo_range(elo_range,reports)
           
            result = benchmarking(
                elo_range,
                reports,
                inference_seconds=inference_seconds,
                output_path=output_path,
            )

            if result is None:
                print(f"\n=== ELO Benchmark: {low}–{high} ===")
                print("  skipped: no analysable player sides found")
                continue

            total_time+=inference_seconds
                
            print(f"\n=== ELO Benchmark: {low}–{high} ===")
            print(f"  games analysed      : {result['games_analyzed']}")
            print(f"  player-side samples : {result['player_side_samples']}")
            print(f"  inference time      : {result['inference_seconds']:.2f}s")
            print(f"  saved to            : {output_path}")
            
    total_time = total_time/60
            
    print(f" Total inference time = {total_time} min")
        
    
    return 0



def cmd_profile(args) -> int:
    low, high = args.elo_range
    reports = []

    with open_analyzer(
        args.engine,
        depth=args.depth,
        threads=args.threads,
    ) as az:
        for game in iter_games(args.pgn):
            headers = game.headers

            try:
                white_elo = int(headers.get("WhiteElo", 0))
                black_elo = int(headers.get("BlackElo", 0))
            except (TypeError, ValueError):
                continue

            white_matches = low <= white_elo < high
            black_matches = low <= black_elo < high

            # Crucially, skip before invoking Stockfish
            if not white_matches and not black_matches:
                continue

            reports.append(analyze_game(game, az))

            if len(reports) >= args.nb_game:
                break

    prof = build_profile(args.elo_range, reports)

    print(f"\n=== ELO Profile: {low}–{high} ===")
    print(f"  samples analysed: {prof.games}")
    print(f"\n=== Profile: {prof.elo_range} ===")
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
    pr.add_argument("--player", required=False, help="player name as in the PGN")
    pr.add_argument("--elo_range",type = int , nargs = 2 ,metavar=("MIN_ELO", "MAX_ELO"), default=[1400, 3000],help="ELO range that we want to evaluate for")
    _add_engine_args(pr)
    pr.set_defaults(func=cmd_profile)
    
    
    bch_mark= sub.add_parser("benchmarking", help="benchmark one ELO range of players ")
    bch_mark.add_argument("pgn", help="path to a .pgn file")
    bch_mark.add_argument("--elo_range",type = int , nargs = 2 ,metavar=("MIN_ELO", "MAX_ELO"), default=[2000, 2299],help="ELO range that we want to evaluate for")
    _add_engine_args(bch_mark)
    bch_mark.set_defaults(func=cmd_single_benchmark)
    
    
    gen_bench = sub.add_parser("general_bench", help="benchmark across all ELO ranges of players ")
    gen_bench.add_argument("pgn", help="path to a .pgn file")
    _add_engine_args(gen_bench)
    gen_bench.set_defaults(func=cmd_general_benchmark)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
