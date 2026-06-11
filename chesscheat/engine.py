"""Thin wrapper around a UCI engine (Stockfish by default).

Kept separate so the rest of the code never talks UCI directly, and so we can
swap engines or mock the analyser in tests. If no engine binary is available
the rest of the toolkit still imports fine — you just can't run engine-backed
analysis until you install one.
"""

from __future__ import annotations

import shutil
from contextlib import contextmanager
from dataclasses import dataclass

try:
    import chess
    import chess.engine
    _HAS_CHESS = True
except ImportError:  # pragma: no cover - exercised only without the dependency
    _HAS_CHESS = False


def find_engine(explicit: str | None = None) -> str | None:
    """Return a path to a usable UCI engine binary, or None.

    Order: an explicit path, then $PATH for common engine names.
    """
    if explicit:
        return explicit if shutil.which(explicit) or _is_file(explicit) else None
    for name in ("stockfish", "lc0", "komodo"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _is_file(path: str) -> bool:
    import os
    return os.path.isfile(path)


@dataclass
class PositionEval:
    """Engine's read of one position."""

    best_move: "chess.Move"   # engine's preferred move
    score_cp: float           # eval (side-to-move POV) in centipawns
    is_mate: bool             # True if the score was a forced mate


class Analyzer:
    """Owns a single long-lived engine process.

    Use as a context manager::

        with Analyzer(path, depth=18) as az:
            ev = az.evaluate(board)
    """

    def __init__(self, engine_path: str, depth: int = 16, multipv: int = 1,
                 threads: int = 1, hash_mb: int = 128):
        if not _HAS_CHESS:
            raise RuntimeError(
                "python-chess is not installed. Run: pip install -r requirements.txt"
            )
        self.engine_path = engine_path
        self.depth = depth
        self.multipv = multipv
        self.threads = threads
        self.hash_mb = hash_mb
        self._engine = None

    def __enter__(self) -> "Analyzer":
        self._engine = chess.engine.SimpleEngine.popen_uci(self.engine_path)
        try:
            self._engine.configure({"Threads": self.threads, "Hash": self.hash_mb})
        except chess.engine.EngineError:
            pass  # engine may not expose these options; ignore.
        return self

    def __exit__(self, *exc) -> None:
        if self._engine is not None:
            self._engine.quit()
            self._engine = None

    def evaluate(self, board: "chess.Board") -> PositionEval:
        """Evaluate ``board`` and return the engine's best move + score."""
        info = self._engine.analyse(
            board, chess.engine.Limit(depth=self.depth)
        )
        score = info["score"].pov(board.turn)
        is_mate = score.is_mate()
        # Convert mate scores to a large cp so downstream math stays finite.
        cp = score.score(mate_score=100000)
        best = info.get("pv", [None])[0]
        return PositionEval(best_move=best, score_cp=float(cp), is_mate=is_mate)


@contextmanager
def open_analyzer(engine_path: str | None = None, **kwargs):
    """Convenience: resolve an engine path and yield an Analyzer, or raise."""
    path = find_engine(engine_path)
    if not path:
        raise RuntimeError(
            "No UCI engine found. Install Stockfish (brew install stockfish) "
            "or pass --engine /path/to/engine."
        )
    with Analyzer(path, **kwargs) as az:
        yield az
