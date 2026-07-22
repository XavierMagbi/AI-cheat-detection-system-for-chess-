"""Cross-game profiling and the heuristic "flagging" layer.

IMPORTANT: nothing here proves cheating. It produces a weighted *suspicion
score* and a list of human-readable reasons, exactly like the public-facing
output of a real anti-cheat would feed to a human reviewer. Decisions about
accounts should always involve a human looking at the underlying games.

The signals we combine:

* **Low ACPL**     — consistently tiny average centipawn loss.
* **High match %** — playing the engine's first choice very often.
* **Low variance** — a real human is streaky; a bot is metronomic. Very low
  game-to-game variance in ACPL is itself suspicious.
* **Phase mismatch** — near-perfect middlegame play paired with weak endgames
  (or vice-versa) can indicate selective engine use.
"""

from __future__ import annotations

import math

import statistics
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .analyze import GameReport


# Thresholds are deliberately conservative and easy to tune. They are starting
# points, not science — see the README "Calibration" section.
THRESHOLDS = {
    "acpl_suspicious": 20.0,     # avg cp loss below this across games is notable
    "acpl_very_low": 12.0,       # and below this is strongly notable
    "match_suspicious": 55.0,    # engine top-move % above this is notable
    "match_very_high": 70.0,
    "acpl_stdev_low": 8.0,       # low game-to-game variance in ACPL
    "min_games": 30,              #
}

MINIMUM_GAMES = 50 
RECOMMENDED_GAMES = 100 
STRONG_GAMES = 200


@dataclass
class RunMetadata:
    """Settings used for one benchmark/profile run."""

    source_file: str = "?"
    maia_model: str = "?"
    maia_elo: int | None = None
    maia_device: str = "?"
    maia_multipv: int | None = None
    stockfish_depth: int | None = None
    stockfish_threads: int | None = None


@dataclass
class EloProfile:
    """Aggregate metrics for one type of player (elo ranking) across many games."""
    elo_range: list[int] = field(default_factory=list)
    games: int = 0
    avg_acpl: float = 0.0
    acpl_stdev: float = 0.0
    avg_match_pct: float = 0.0
    avg_maia_pct : float = 0.0
    avg_accuracy: float = 0.0
    total_blunders: int = 0
    suspicion: dict = field(default_factory=lambda: {
        "general_score": 0.0,
        "stockfish_score": 0.0,
        "maia_score": 0.0,
        "consistency_score": 0.0,
    })  # weighted suspicion sub-scores

    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)
    per_game: list[dict] = field(default_factory=list)
    


def benchmarking(
    elo_range: list[int],
    reports: list[GameReport],
    run_report: RunMetadata | Any | None = None,
    inference_seconds: float = 0.0,
    output_path: str | Path | None = None,
) -> dict | None:
    """Calculate cohort statistics and save them as JSON."""
    low, high = elo_range
    summaries: list[dict] = []


    for report in reports:
        if low <= report.elo_white < high:
            summaries.append(report.white_summary)
        if low <= report.elo_black < high:
            summaries.append(report.black_summary)
            
        

    summaries = [s for s in summaries if s["moves"] > 0]
    if not summaries:
        return None
        #raise RuntimeError(f"no analysable player sides found in ELO range {low}-{high}")

    acpls = [s["acpl"] for s in summaries]
    matches = [s["top_move_pct"] for s in summaries]
    maia_matching = [s["maia_matching_pct"] for s in summaries]
    accuracies = [s["accuracy"] for s in summaries]

    def variance(values: list[float]) -> float:
        return statistics.variance(values) if len(values) > 1 else 0.0

    variance_acpl = variance(acpls)
    variance_accuracy = variance(accuracies)
    variance_match_pct = variance(matches)
    variance_maia_pct = variance(maia_matching)

    def metadata(name: str, default: Any = None) -> Any:
        return getattr(run_report, name, default) if run_report is not None else default

    data = {
        "elo_range": list(elo_range),
        "games_analyzed": len(reports),
        "player_side_samples": len(summaries),
        "source_file": metadata("source_file", "?"),
        "Stockfish_depth": metadata("stockfish_depth"),
        "Stockfish_threads": metadata("stockfish_threads"),
        "Maia_Model": metadata("maia_model", "?"),
        "Maia_Elo": metadata("maia_elo"),
        "Maia_Device": metadata("maia_device", "?"),
        "Maia_MultiPV": metadata("maia_multipv"),
        "inference_seconds": inference_seconds,
        
        "avg_acpl": statistics.mean(acpls),
        "variance_acpl": variance_acpl,
        "std_acpl": math.sqrt(variance_acpl),
        "high_median_acpl": statistics.median_high(acpls),
        "low_median_acpl": statistics.median_low(acpls),
        "avg_accuracy": statistics.mean(accuracies),
        "variance_accuracy": variance_accuracy,
        "std_accuracy": math.sqrt(variance_accuracy),
        "high_median_accuracy": statistics.median_high(accuracies),
        "low_median_accuracy": statistics.median_low(accuracies),
        "avg_match_pct": statistics.mean(matches),
        "variance_match_pct": variance_match_pct,
        "std_match_pct": math.sqrt(variance_match_pct),
        "high_median_match_pct": statistics.median_high(matches),
        "low_median_match_pct": statistics.median_low(matches),
        "avg_maia_pct" : statistics.mean(maia_matching),
        "variance_maia_pct": variance_maia_pct,
        "std_maia_pct": math.sqrt(variance_maia_pct),
        "high_median_maia_pct": statistics.median_high(maia_matching),
        "low_median_maia_pct": statistics.median_low(maia_matching),
        "total_blunders": sum(s["blunders"] for s in summaries),
        "player_side_summaries": summaries,
        
    }

    destination = Path(output_path) if output_path is not None else benchmark_path_for_elo_range(elo_range,reports)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def benchmark_path_for_elo_range(elo_range: list[int], reports: list[GameReport] ) -> Path:
    low, high = elo_range
    if not reports:
        return Path("benchmark_data/standard") / f"benchmark_{low}_{high}.json"
    for report in reports : 
         if  report.type_game== "Standard" : 
             return Path("benchmark_data/standard") / f"benchmark_{low}_{high}.json"
         else : 
             return Path("benchmark_data/broadcast") / f"benchmark_{low}_{high}.json"
        
   
        
        
    


def _legacy_benchmark_path_for_elo_range(elo_range: list[int],reports: list[GameReport]) -> Path:
    if not reports:
        return Path("benchmark_data/standard") / f"benchmark_{elo_range}.json"
    for report in reports :
        if report.type_game =="Standard" :
            return Path("benchmark_data/standard") / f"benchmark_{elo_range}.json"
        else :
            return Path("benchmark_data/broadcast") / f"benchmark_{elo_range}.json"
          
        


def _load_benchmark_data(elo_range: list[int],reports: list[GameReport]) -> dict:
    low, high = elo_range

    dataset_folder = "standard"
    if reports and reports[0].type_game == "Broadcast":
        dataset_folder = "broadcast"

    paths = [
        Path("benchmark_data") / dataset_folder / f"benchmark_{low}_{high}.json",
        _legacy_benchmark_path_for_elo_range(elo_range, reports),
    ]
            

    for path in paths:
        if path.exists():
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)

    searched = ", ".join(str(path) for path in paths)
    low, high = elo_range
    raise RuntimeError(
        f"no benchmark JSON found for ELO range {low}-{high}. "
        f"Looked for: {searched}"
    )


def build_profile(
    elo_range: list[int],
    reports: list[GameReport],
    output_path: str | Path | None = None,
) -> EloProfile:
    low, high = elo_range
    summaries = []
    
    broadcast = bool(reports and reports[0].type_game == "Broadcast")
    move_review: list[dict] = []

    for game_index, report in enumerate(reports, 1):
        if low <= report.elo_white < high:
            summaries.append(report.white_summary)
            move_review.extend(_move_review_rows(game_index, report, white=True))

        if low <= report.elo_black < high:
            summaries.append(report.black_summary)
            move_review.extend(_move_review_rows(game_index, report, white=False))

    summaries = [s for s in summaries if s["moves"] > 0]

    profile = EloProfile(
        elo_range=list(elo_range),
        games=len(summaries),
    )

    if not summaries:
        return profile

    acpls = [s["acpl"] for s in summaries]
    matches = [s["top_move_pct"] for s in summaries]
    maia_matching = [s["maia_matching_pct"] for s in summaries]
    accuracies = [s["accuracy"] for s in summaries]

    profile.avg_acpl = statistics.mean(acpls)
    profile.acpl_stdev = (
        statistics.pstdev(acpls) if len(acpls) > 1 else 0.0
    )
    profile.avg_match_pct = statistics.mean(matches)
    profile.avg_maia_pct = statistics.mean(maia_matching)
    profile.avg_accuracy = statistics.mean(accuracies)
    profile.total_blunders = sum(s["blunders"] for s in summaries)
    profile.per_game = summaries
    profile.confidence = min(profile.games / RECOMMENDED_GAMES, 1.0) * 100

    (
        profile.suspicion["general_score"],
        profile.suspicion["stockfish_score"],
        profile.suspicion["maia_score"],
        profile.suspicion["consistency_score"],
        profile.reasons,
    ) = _score(profile, reports)
    
    
    
    if output_path is None:
        if broadcast:
            output_path = Path("results/broadcast_games") / f"result_{profile.elo_range}.json"
        else:
            output_path = Path("results/standard_games") / f"result_{profile.elo_range}.json"
    
    
    data = {
    "Profile": profile.elo_range,
    "Games_analysed ": profile.games,
    "avg ACPL" : profile.avg_acpl,
    "std_deviaiton" : profile.acpl_stdev,
    " avg top-move % ": profile.avg_match_pct,
    " avg_maia_move_matching %" : profile.avg_maia_pct,
    "avg accuracy" : profile.avg_accuracy,
    "total blunders" : profile.total_blunders,
    "confidence % "    : profile.confidence,
    "per_game": profile.per_game,
    "move_review": move_review,
    "SUSPICION SCORE": { 
        "general score " : profile.suspicion["general_score"]/100,
        "Maia plausibility score " : profile.suspicion["maia_score"]/12,
        "Consistency score" :profile.suspicion["consistency_score"]/15,
        "Stockfish strength score" :profile.suspicion["stockfish_score"]/95,                         
        }
    }
    
    
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(data, indent=2), encoding="utf-8")

    return profile


def _move_review_rows(game_index: int, report: GameReport, white: bool) -> list[dict]:
    """Create move-level rows for reviewer tables."""
    player = report.white if white else report.black
    elo = report.elo_white if white else report.elo_black
    color = "White" if white else "Black"
    rows: list[dict] = []

    for move in report.moves:
        if move.is_white != white:
            continue

        maia_available = move.maia_san != "?"
        suspicious_strength = move.is_top_move and maia_available and not move.is_maia_move
        large_loss = move.cp_loss >= 200
        rows.append({
            "game_index": game_index,
            "player": player,
            "elo": elo,
            "color": color,
            "result": report.result,
            "type_game": report.type_game,
            "ply": move.ply,
            "phase": move.phase,
            "played_move": move.san,
            "stockfish_best_move": move.best_san,
            "maia_predicted_move": move.maia_san,
            "cp_loss": move.cp_loss,
            "accuracy": move.accuracy,
            "stockfish_match": move.is_top_move,
            "maia_match": move.is_maia_move,
            "review_flag": suspicious_strength or large_loss,
        })

    return rows


def _score(p: EloProfile,reports: list[GameReport]) -> tuple[float, float, float, float, list[str]]:
    """Combine signals into a 0..100 suspicion score with reasons."""
    
    low = p.elo_range[0]
    high = p.elo_range[1] 
    
    d = _load_benchmark_data(p.elo_range,reports)

    def benchmark_std(metric: str) -> float:
        std_key = f"std_{metric}"
        variance_key = f"variance_{metric}"
        if std_key in d:
            return d[std_key]
        if variance_key in d:
            return math.sqrt(d[variance_key])
        return 0.0
        
    acpl_suspicious = d["avg_acpl"]     # avg cp loss below this across games is notable
    acpl_very_low = d["avg_acpl"] - benchmark_std("acpl")        # and below this is strongly notable
    match_suspicious = d["avg_match_pct"]    # engine top-move % above this is notable
    match_very_high = d["avg_match_pct"] + benchmark_std("match_pct")
    match_too_high = d["avg_match_pct"] + 2*benchmark_std("match_pct")
    matching_maia_suspicious =  d["avg_maia_pct"]
    matching_maia_very_low = d["avg_maia_pct"] - benchmark_std("maia_pct")
    matching_maia_too_low = d["avg_maia_pct"] - 2 * benchmark_std("maia_pct")
    acpl_stdev_low = benchmark_std("acpl")       # low game-to-game variance in ACPL
    min_games = d["player_side_samples"]/2              #

    

    gen_score = 0.0 #/100
    stockfish_score = 0.0 # /95 
    maia_score = 0.0 # /12 
    consistency_score = 0.0 #/15
    
    reasons: list[str] = []

    if p.games < min_games:
        reasons.append(
            f"Only {p.games} game(s) analysed ,below the {min_games:.0f}-game "
            "minimum for a reliable profile. Treat results as indicative only."
        )

    # Low average centipawn loss.
    if p.avg_acpl <= acpl_very_low:
        gen_score += 35
        stockfish_score+=35
        reasons.append(f"Very low average centipawn loss ({p.avg_acpl:.1f}).")
    elif p.avg_acpl <= acpl_suspicious:
        gen_score += 15
        stockfish_score+=15
        reasons.append(f"Low average centipawn loss ({p.avg_acpl:.1f}).")

    # High engine top-move agreement & Low maia top-move agreement.
    
    
    if p.avg_match_pct >= match_too_high and p.avg_maia_pct <= matching_maia_too_low :
        gen_score += 50
        stockfish_score+=45
        maia_score+=5
        reasons.append(f"Very high engine top-move match ({p.avg_match_pct:.1f}%) and very low human-like moves.")
    
    elif p.avg_match_pct >= match_too_high and p.avg_maia_pct > matching_maia_too_low :
        gen_score += 45
        stockfish_score+=45
        reasons.append(f"Very high engine top-move match ({p.avg_match_pct:.1f}%).")
    
    elif p.avg_match_pct >= match_very_high and p.avg_maia_pct <= matching_maia_very_low :
        gen_score += 40
        maia_score+=5
        stockfish_score+=35
        reasons.append(f"Very high engine top-move match ({p.avg_match_pct:.1f}%) and very low human-like moves.")
        
    elif p.avg_match_pct >= match_very_high and p.avg_maia_pct > matching_maia_very_low :
        gen_score += 35
        stockfish_score+=35
        reasons.append(f"Very high engine top-move match ({p.avg_match_pct:.1f}%).")
        
    elif p.avg_match_pct >= match_suspicious and  p.avg_maia_pct <= matching_maia_suspicious :
        gen_score += 20
        maia_score+=2
        stockfish_score+=18 
        reasons.append(f"High engine top-move match  ({p.avg_match_pct:.1f}%) and very low human-like matching move ({p.avg_maia_pct:.1f}%).")
        
    elif p.avg_match_pct >= match_suspicious  :
        gen_score += 18
        stockfish_score+=18
        reasons.append(f"High engine top-move match ({p.avg_match_pct:.1f}%).")


    # Low game-to-game variance (only meaningful with several games).
    if p.games >= min_games and p.acpl_stdev <= acpl_stdev_low:
        gen_score += 15
        consistency_score+= 15 
        reasons.append(
            f"Unusually consistent results across games "
            f"(ACPL stdev {p.acpl_stdev:.1f}) — little human streakiness."
        )

    if not reasons or all(r.startswith("Only") for r in reasons):
        reasons.append("No strong statistical anomalies detected.")

    return min(100.0, gen_score), min(95.0, stockfish_score), min(12.0, maia_score), min(15.0, consistency_score), reasons
