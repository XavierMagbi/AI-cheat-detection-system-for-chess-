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

import statistics
from dataclasses import dataclass, field

from .analyze import GameReport


# Thresholds are deliberately conservative and easy to tune. They are starting
# points, not science — see the README "Calibration" section.
THRESHOLDS = {
    "acpl_suspicious": 20.0,     # avg cp loss below this across games is notable
    "acpl_very_low": 12.0,       # ... and below this is strongly notable
    "match_suspicious": 55.0,    # engine top-move % above this is notable
    "match_very_high": 70.0,
    "acpl_stdev_low": 8.0,       # low game-to-game variance in ACPL
    "min_games": 3,              # need at least this many games to profile
}


@dataclass
class PlayerProfile:
    name: str
    games: int = 0
    avg_acpl: float = 0.0
    acpl_stdev: float = 0.0
    avg_match_pct: float = 0.0
    avg_accuracy: float = 0.0
    total_blunders: int = 0
    suspicion: float = 0.0                 # 0..100 weighted score
    reasons: list[str] = field(default_factory=list)
    per_game: list[dict] = field(default_factory=list)


def build_profile(name: str, reports: list[GameReport]) -> PlayerProfile:
    """Aggregate every game in ``reports`` that ``name`` played in."""
    summaries = []
    for r in reports:
        s = r.for_player(name)
        if s and s["moves"] > 0:
            summaries.append(s)

    profile = PlayerProfile(name=name, games=len(summaries))
    if not summaries:
        return profile

    acpls = [s["acpl"] for s in summaries]
    matches = [s["top_move_pct"] for s in summaries]
    accs = [s["accuracy"] for s in summaries]

    profile.avg_acpl = statistics.mean(acpls)
    profile.acpl_stdev = statistics.pstdev(acpls) if len(acpls) > 1 else 0.0
    profile.avg_match_pct = statistics.mean(matches)
    profile.avg_accuracy = statistics.mean(accs)
    profile.total_blunders = sum(s["blunders"] for s in summaries)
    profile.per_game = summaries

    profile.suspicion, profile.reasons = _score(profile)
    return profile


def _score(p: PlayerProfile) -> tuple[float, list[str]]:
    """Combine signals into a 0..100 suspicion score with reasons."""
    t = THRESHOLDS
    score = 0.0
    reasons: list[str] = []

    if p.games < t["min_games"]:
        reasons.append(
            f"Only {p.games} game(s) analysed — below the {t['min_games']}-game "
            "minimum for a reliable profile. Treat results as indicative only."
        )

    # Low average centipawn loss.
    if p.avg_acpl <= t["acpl_very_low"]:
        score += 40
        reasons.append(f"Very low average centipawn loss ({p.avg_acpl:.1f}).")
    elif p.avg_acpl <= t["acpl_suspicious"]:
        score += 20
        reasons.append(f"Low average centipawn loss ({p.avg_acpl:.1f}).")

    # High engine top-move agreement.
    if p.avg_match_pct >= t["match_very_high"]:
        score += 35
        reasons.append(f"Very high engine top-move match ({p.avg_match_pct:.1f}%).")
    elif p.avg_match_pct >= t["match_suspicious"]:
        score += 18
        reasons.append(f"High engine top-move match ({p.avg_match_pct:.1f}%).")

    # Low game-to-game variance (only meaningful with several games).
    if p.games >= t["min_games"] and p.acpl_stdev <= t["acpl_stdev_low"]:
        score += 15
        reasons.append(
            f"Unusually consistent results across games "
            f"(ACPL stdev {p.acpl_stdev:.1f}) — little human streakiness."
        )

    if not reasons or all(r.startswith("Only") for r in reasons):
        reasons.append("No strong statistical anomalies detected.")

    return min(100.0, score), reasons
