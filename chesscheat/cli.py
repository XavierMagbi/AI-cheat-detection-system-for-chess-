"""Command-line entry point.

Usage:
    python -m chesscheat.cli analyze games.pgn [--engine PATH] [--depth N]
    python -m chesscheat.cli profile games.pgn --player "Name" [...]
"""

from __future__ import annotations

import argparse
import sys
import time
from contextlib import nullcontext

from .analyze import analyze_game, iter_games
from .engine import open_analyzer
from .maia import open_maia_analyzer
from .profile import RunMetadata, build_profile, benchmarking, benchmark_path_for_elo_range





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
    p.add_argument("--nb_game", type=int, default=500, help="number of game selected in the dataset")


def _add_maia_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--use-maia", action="store_true", help="also run Maia human-move prediction")
    p.add_argument("--maia-engine", help="path/command for Maia UCI engine")
    p.add_argument("--maia-model", default="maia3-5m", help="Maia 3 model alias")
    p.add_argument("--maia-elo", type=int, help="Maia Elo; default is midpoint of --elo_range when available")
    p.add_argument("--maia-multipv", type=int, default=1, help="number of Maia candidate moves")
    p.add_argument("--maia-nodes", type=int, default=1, help="Maia UCI nodes limit")
    p.add_argument("--maia-temperature", type=float, default=0.0, help="Maia sampling temperature; 0 means deterministic")
    p.add_argument("--maia-top-p", type=float, default=1.0, help="Maia nucleus sampling threshold")
    p.add_argument("--maia-timeout", type=float, default=120.0, help="seconds to wait for Maia to start")
    p.add_argument("--maia-device", default="cpu", help="Maia inference device, e.g. cpu, mps, or cuda")
    p.add_argument("--maia-use-amp", action="store_true", help="allow Maia automatic mixed precision")


def _run_metadata_from_args(args, elo_range: list[int] | None = None) -> RunMetadata:
    maia_elo = args.maia_elo
    if maia_elo is None and elo_range is not None:
        low, high = elo_range
        maia_elo = (low + high) // 2

    return RunMetadata(
        source_file=args.pgn,
        maia_model=args.maia_model,
        maia_elo=maia_elo,
        maia_device=args.maia_device,
        maia_multipv=args.maia_multipv,
        stockfish_depth=args.depth,
        stockfish_threads=args.threads,
    )


def _open_maia_from_args(args, elo_range: list[int] | None = None):
    if not getattr(args, "use_maia", False):
        return nullcontext(None)

    maia_elo = args.maia_elo
    if maia_elo is None and elo_range is not None:
        low, high = elo_range
        maia_elo = (low + high) // 2

    kwargs = {
        "model": args.maia_model,
        "multipv": args.maia_multipv,
        "nodes": args.maia_nodes,
        "temperature": args.maia_temperature,
        "top_p": args.maia_top_p,
        "timeout": args.maia_timeout,
        "device": args.maia_device,
        "use_amp": args.maia_use_amp,
    }
    if maia_elo is not None:
        kwargs["elo"] = maia_elo
    if elo_range is not None:
        kwargs["elo_range_evaluated"] = elo_range

    return open_maia_analyzer(engine_path=args.maia_engine, **kwargs)
    


def cmd_analyze(args) -> int:
    """Analyse every game in a PGN and print per-side summaries."""
    with open_analyzer(args.engine, depth=args.depth, threads=args.threads) as az:
        with _open_maia_from_args(args) as maia:
            for i, game in enumerate(iter_games(args.pgn), 1):
                report = analyze_game(game, az, maia)
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
                            f"maia-match={s['maia_matching_pct']:.1f}% "
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
        with _open_maia_from_args(args, args.elo_range) as maia:
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
                
                reports.append(analyze_game(game, az, maia))
                
                if len(reports) >= args.nb_game:
                    break
                
            inference_seconds = time.perf_counter() - start_time
            run_metadata = _run_metadata_from_args(args, args.elo_range)
            result = benchmarking(
                args.elo_range,
                reports,
                run_metadata,
                inference_seconds=inference_seconds,
            )
            if result is None:
                print(f"\n=== ELO Benchmark: {low}–{high} ===")
                print("  skipped: no analysable player sides found")
                return 0
            output_path = benchmark_path_for_elo_range(args.elo_range,reports)
            
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
            maia_context = _open_maia_from_args(args, elo_range)
            with maia_context as maia:
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
                    
                    reports.append(analyze_game(game, az, maia))
                    if len(reports) >= args.nb_game:
                        break

            inference_seconds = time.perf_counter() - start_time
            run_metadata = _run_metadata_from_args(args, elo_range)
            result = benchmarking(
                elo_range,
                reports,
                run_metadata,
                inference_seconds=inference_seconds,
            )

            if result is None:
                print(f"\n=== ELO Benchmark: {low}–{high} ===")
                print("  skipped: no analysable player sides found")
                continue
            output_path = benchmark_path_for_elo_range(elo_range,reports)

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
    
    start_time = time.perf_counter()
    
    with open_analyzer(
        args.engine,
        depth=args.depth,
        threads=args.threads,
    ) as az:
        with _open_maia_from_args(args, args.elo_range) as maia:
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

                reports.append(analyze_game(game, az, maia))

                if len(reports) >= args.nb_game:
                    break

    prof = build_profile(args.elo_range, reports)
    
    inference_seconds = time.perf_counter() - start_time

    print(f"\n=== ELO Profile: {low}–{high} ===")
    print(f"  samples analysed: {prof.games}")
    print(f"\n=== Profile: {prof.elo_range} ===")
    print(f"  games analysed : {prof.games}")
    print(f"  avg ACPL       : {prof.avg_acpl:.1f}  (stdev {prof.acpl_stdev:.1f})")
    print(f"  avg top-move % : {prof.avg_match_pct:.1f}")
    print(f"  avg accuracy   : {prof.avg_accuracy:.1f}")
    print(f"  total blunders : {prof.total_blunders}")
    print(f"\n  SUSPICION SCORE: {prof.suspicion['general_score']:.0f}/100")
    print(f"Inference Time : {inference_seconds}")
    print("  reasons:")
    
    
    
    for r in prof.reasons:
        print(f"    - {r}")
    print("\n  NOTE: this is a statistical indicator, not proof. Always have a "
          "human review the actual games before acting on an account.")
    
    return 0

def cmd_profile_all(args) -> int:
    for elo_range in ELO_RANGES :
        low, high = elo_range
        reports = []
        start_time = time.perf_counter()
        
        with open_analyzer(
        args.engine,
        depth=args.depth,
        threads=args.threads,
        ) as az:
            with _open_maia_from_args(args, elo_range) as maia:
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
                    
                    reports.append(analyze_game(game, az, maia))
                    
                    if len(reports) >= args.nb_game:
                        break
                    
        prof = build_profile(elo_range, reports)
            
        inference_seconds = time.perf_counter() - start_time
        
        print(f"\n=== ELO Profile: {low}–{high} ===")
        print(f"  games analysed : {prof.games}")
        print(f"  inference time : {inference_seconds}")
        print(f"  confidence     : {prof.confidence:.1f}%")
        print(f"  avg ACPL       : {prof.avg_acpl:.1f}  (stdev {prof.acpl_stdev:.1f})")
        print(f"  avg top-move % : {prof.avg_match_pct:.1f}")
        print(f"  avg accuracy   : {prof.avg_accuracy:.1f}")
        print(f"  total blunders : {prof.total_blunders}")
        print(f"\n  SUSPICION SCORE: {prof.suspicion['general_score']:.0f}/100")
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
    _add_maia_args(a)
    a.set_defaults(func=cmd_analyze)

    pr = sub.add_parser("profile", help="profile one elo range across many games")
    pr.add_argument("pgn", help="path to a .pgn file")
    pr.add_argument("--player", required=False, help="player name as in the PGN")
    pr.add_argument("--elo_range",type = int , nargs = 2 ,metavar=("MIN_ELO", "MAX_ELO"), default=[1400, 3000],help="ELO range that we want to evaluate for")
    _add_engine_args(pr)
    _add_maia_args(pr)
    pr.set_defaults(func=cmd_profile)
    
    
    gen_pr = pr = sub.add_parser("general_profile", help="profile all elo ranges across many games")
    gen_pr.add_argument("pgn", help="path to a .pgn file")
    _add_engine_args(gen_pr)
    _add_maia_args(gen_pr)
    gen_pr.set_defaults(func=cmd_profile_all)
    
    
    bch_mark= sub.add_parser("benchmarking", help="benchmark one ELO range of players ")
    bch_mark.add_argument("pgn", help="path to a .pgn file")
    bch_mark.add_argument("--elo_range",type = int , nargs = 2 ,metavar=("MIN_ELO", "MAX_ELO"), default=[2000, 2299],help="ELO range that we want to evaluate for")
    _add_engine_args(bch_mark)
    _add_maia_args(bch_mark)
    bch_mark.set_defaults(func=cmd_single_benchmark)
    
    
    gen_bench = sub.add_parser("general_bench", help="benchmark across all ELO ranges of players ")
    gen_bench.add_argument("pgn", help="path to a .pgn file")
    _add_engine_args(gen_bench)
    _add_maia_args(gen_bench)
    gen_bench.set_defaults(func=cmd_general_benchmark)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
