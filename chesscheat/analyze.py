"""Single-game analysis: walk a PGN game move by move, ask the engine to grade
each move, and produce per-side summaries.

This is the data-gathering layer. It does NOT decide "cheater / not cheater" —
it produces the metrics that :mod:`chesscheat.profile` reasons about. Keeping
measurement and judgement separate matters: the judgement thresholds will get
tuned over time, but the measurements should stay stable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

try:
    import chess
    import chess.pgn
except ImportError:  # pragma: no cover
    chess = None

from .engine import Analyzer
from .metrics import MoveEval, accuracy_from_win_drop, cp_to_win_percent, summarize

# Cap per-move centipawn loss. Without this a single move into a forced mate
# scores ~100000cp and swamps the average. 1000cp (~10 pawns) is already
# "completely lost", so anything beyond it carries no extra signal for ACPL.
MAX_CP_LOSS = 1000.0


def _phase(board: "chess.Board", ply: int) -> str:
    """Rough game-phase classification used to bucket metrics.

    Cheating often shows up unevenly: engine help in sharp middlegames but
    human-looking opening theory, for example. Bucketing lets us see that.
    """
    # Count non-pawn, non-king material left on the board.
    pieces = sum(
        1 for sq in chess.SQUARES
        if (p := board.piece_at(sq)) and p.piece_type not in (chess.PAWN, chess.KING)
    )
    if ply <= 20:
        return "opening"
    if pieces <= 6:
        return "endgame"
    return "middlegame"


@dataclass
class GameReport:
    """Everything we learned about one game."""

    white: str
    black: str
    result: str
    moves: list[MoveEval] = field(default_factory=list)
    white_summary: dict = field(default_factory=dict)
    black_summary: dict = field(default_factory=dict)

    def for_player(self, name: str) -> dict | None:
        """Return the summary for ``name`` (case-insensitive), or None."""
        if name.lower() == self.white.lower():
            return self.white_summary
        if name.lower() == self.black.lower():
            return self.black_summary
        return None


def analyze_game(game: "chess.pgn.Game", analyzer: Analyzer) -> GameReport:
    """Grade every move of ``game`` with ``analyzer``."""
    board = game.board()
    headers = game.headers
    report = GameReport(
        white=headers.get("White", "?"),
        black=headers.get("Black", "?"),
        result=headers.get("Result", "*"),
    )

    ply = 0
    for move in game.mainline_moves():
        ply += 1
        is_white = board.turn == chess.WHITE
        phase = _phase(board, ply)

        # Evaluate the position BEFORE the move: gives best move + best score.
        before = analyzer.evaluate(board)
        win_before = cp_to_win_percent(before.score_cp)
        best_san = board.san(before.best_move) if before.best_move else "?"
        played_san = board.san(move)
        is_top = before.best_move == move

        # Play the move, then evaluate from the opponent's POV and negate to get
        # the score from the mover's POV after their move.
        board.push(move)
        after = analyzer.evaluate(board)
        win_after = cp_to_win_percent(-after.score_cp)

        cp_loss = min(MAX_CP_LOSS, max(0.0, before.score_cp - (-after.score_cp)))
        report.moves.append(MoveEval(
            ply=ply,
            san=played_san,
            is_white=is_white,
            phase=phase,
            best_san=best_san,
            is_top_move=is_top,
            cp_loss=cp_loss,
            win_before=win_before,
            win_after=win_after,
            accuracy=accuracy_from_win_drop(win_before, win_after),
        ))

    report.white_summary = summarize(report.moves, white=True)
    report.black_summary = summarize(report.moves, white=False)
    return report


def iter_games(pgn_path: str):
    """Yield every game in a PGN file."""
    if chess is None:
        raise RuntimeError("python-chess is not installed.")
    with open(pgn_path, encoding="utf-8") as fh:
        while (game := chess.pgn.read_game(fh)) is not None:
            yield game
