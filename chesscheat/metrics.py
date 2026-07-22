"""Pure-math helpers for converting engine evaluations into human-readable
quality metrics. No engine or I/O here so these are trivially unit-testable.

The two key ideas:

* **Win percentage** : centipawns are not linear in "how won is this position".
  +300cp matters far more at 0 than at +1500. We map cp -> expected score in
  [0, 100] with the logistic Lichess uses, so errors are weighted by how much
  they actually change the practical outcome.

* **Accuracy** : a per-move score in [0, 100] derived from how much win% the
  move threw away. A move that loses no win% scores ~100; a blunder scores low.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# --- evaluation conversions -------------------------------------------------

def cp_to_win_percent(cp: float) -> float:
    """Convert a centipawn eval (from the side-to-move's POV) to win % [0, 100].

    Uses the Lichess logistic. A cp of 0 -> 50%. Large advantages saturate.
    """
    # Clamp to avoid overflow on mate-ish scores passed in as huge cp.
    cp = max(-2000.0, min(2000.0, cp))
    return 50.0 + 50.0 * (2.0 / (1.0 + math.exp(-0.00368208 * cp)) - 1.0)


def accuracy_from_win_drop(win_before: float, win_after: float) -> float:
    """Per-move accuracy [0, 100] from the win% before/after the move.

    ``win_before`` and ``win_after`` are both expressed from the moving side's
    perspective. The drop is how much practical winning chance the move gave up.
    """
    drop = max(0.0, win_before - win_after)
    acc = 103.1668 * math.exp(-0.04354 * drop) - 3.1669
    return max(0.0, min(100.0, acc))


def matching_engine_play(best_move : str , player_move : str) -> bool :
    
    if best_move == player_move : 
        return True 
        
    return False 



# --- per-move record --------------------------------------------------------

@dataclass
class MoveEval:
    """One analysed half-move."""

    ply: int                 # 1-based half-move number
    san: str                 # the move actually played, e.g. "Nf3"
    is_white: bool           # True if White made this move
    phase: str               # "opening" | "middlegame" | "endgame"
    best_san: str            # engine's preferred move in this position
    is_top_move: bool        # did the player play the engine's #1 move?
    cp_loss: float           # centipawns lost vs best (>= 0)
    win_before: float        # win% (mover POV) before the move, best line
    win_after: float         # win% (mover POV) after the move played
    accuracy: float          # per-move accuracy [0, 100]
    is_maia_move: bool = False  # did the player play Maia's best move?
    maia_san: str = "?"      # Maia's predicted move in SAN, if Maia was enabled


# --- aggregation ------------------------------------------------------------

def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def summarize(moves: list[MoveEval], white: bool) -> dict:
    """Aggregate one side's moves into a per-game summary dict."""
    side = [m for m in moves if m.is_white == white]
    if not side:
        return {
            "moves": 0, "acpl": 0.0, "accuracy": 0.0,
            "top_move_pct": 0.0, "maia_matching_pct": 0.0, "blunders": 0,
            "acpl_by_phase": {}, "top_move_pct_by_phase": {},
        }

    cp_losses = [m.cp_loss for m in side]
    accs = [m.accuracy for m in side]
    tops = sum(1 for m in side if m.is_top_move)
    maias = sum(1 for m in side if m.is_maia_move)
    blunders = sum(1 for m in side if m.cp_loss >= 200)

    by_phase_acpl: dict[str, float] = {}
    by_phase_top: dict[str, float] = {}
    for phase in ("opening", "middlegame", "endgame"):
        pm = [m for m in side if m.phase == phase]
        if pm:
            by_phase_acpl[phase] = _mean([m.cp_loss for m in pm])
            by_phase_top[phase] = 100.0 * sum(1 for m in pm if m.is_top_move) / len(pm)

    return {
        "moves": len(side),
        "acpl": _mean(cp_losses),
        "accuracy": _mean(accs),
        "top_move_pct": 100.0 * tops / len(side),
        "maia_matching_pct": 100.0 * maias / len(side),
        "blunders": blunders,
        "acpl_by_phase": by_phase_acpl,
        "top_move_pct_by_phase": by_phase_top,
    }
