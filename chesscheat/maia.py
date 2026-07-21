"""Maia UCI wrapper.

Maia is not used like Stockfish. Stockfish answers "what is objectively best?";
Maia answers "what would a human around this Elo probably play?".

This module keeps the UCI/process details isolated so the rest of the codebase
can ask a simple question:

    Given this board, what move does Maia predict for this Elo?
"""

from __future__ import annotations

import os
import importlib.util
import shlex
import shutil
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

try:
    import chess
    import chess.engine

    _HAS_CHESS = True
except ImportError:  # pragma: no cover - exercised only without the dependency
    _HAS_CHESS = False


MAIA_COMMANDS = (
    "maia3-uci",
    "maia3-5m",
    "maia3-23m",
    "maia3-79m",
    "maia-uci",
)

MAIA_ELOS = {
    700 : [600,799],
    900 : [800, 999],
    1100 : [1000, 1199],
    1300 : [1200, 1399],
    1500 : [1400, 1599],
    1700 :[1600, 1799],
    1900 : [1800, 1999],
    2100 : [2000, 2199],
    2300 :[2200, 2399],
    2500 :[2400, 2599],
    2700 : [2600, 2799],
    2900 :[2800, 2999],

}


def _is_file(path: str) -> bool:
    return os.path.isfile(path)


def find_engine(explicit: str | None = None) -> str | None:
    """Return a usable Maia executable path/name, or None.

    Search order:
    1. a user-provided command/path;
    2. common Maia 3 UCI entry points on ``$PATH``.
    """
    if explicit:
        first_word = shlex.split(explicit)[0]
        return explicit if shutil.which(first_word) or _is_file(first_word) else None

    python_bin_dirs = [
        Path(sys.executable).parent,
        Path(sys.prefix) / "bin",
    ]
    for name in MAIA_COMMANDS:
        path = shutil.which(name)
        if path:
            return path
        for python_bin_dir in python_bin_dirs:
            venv_path = python_bin_dir / name
            if venv_path.is_file():
                return str(venv_path)

    if importlib.util.find_spec("maia3") is not None:
        return f"{sys.executable} -m maia3.uci"

    return None


def _command_uses_maia3_uci(command: list[str]) -> bool:
    executable = Path(command[0]).name
    return executable == "maia3-uci" or command[1:3] == ["-m", "maia3.uci"]


def build_command(
    engine_path: str,
    model: str = "maia3-5m",
    device: str | None = "cpu",
    use_amp: bool = False,
    use_uci_history: bool = True,
) -> list[str]:
    """Build the command passed to ``python-chess``.

    Preset commands like ``maia3-5m`` already know their model, so they need no
    ``--model`` argument. The generic ``maia3-uci`` command does need one.
    """
    command = shlex.split(engine_path)

    if _command_uses_maia3_uci(command) and "--model" not in command:
        command.extend(["--model", model])

    if _command_uses_maia3_uci(command) and use_uci_history and "--use-uci-history" not in command:
        command.append("--use-uci-history")

    if device and "--device" not in command:
        command.extend(["--device", device])

    if not use_amp and "--no-use-amp" not in command:
        command.append("--no-use-amp")

    return command


@dataclass
class MaiaPrediction:
    """Maia's human-move prediction for one board."""

    best_move: "chess.Move | None"
    best_san: str
    elo: int
    candidate_moves: list["chess.Move"] = field(default_factory=list)
    candidate_sans: list[str] = field(default_factory=list)


class MaiaAnalyzer:
    """Owns one long-lived Maia UCI process.

    Use it as a context manager:

        with MaiaAnalyzer(path, elo=1500) as maia:
            prediction = maia.predict(board)
    """

    def __init__(
        self,
        engine_path: str,
        model: str = "maia3-5m",
        elo: int = 1500,
        self_elo: int | None = None,
        opponent_elo: int | None = None,
        elo_range_evaluated : list[int] = [1400,1599],
        multipv: int = 5,
        nodes: int = 1,
        temperature: float = 0.0,
        top_p: float = 1.0,
        timeout: float = 120.0,
        device: str | None = "cpu",
        use_amp: bool = False,
        use_uci_history: bool = True,
    ):
        if not _HAS_CHESS:
            raise RuntimeError(
                "python-chess is not installed. Run: pip install -r requirements.txt"
            )
            
        

        self.engine_path = engine_path
        self.model = model
        self.elo = elo
        self.self_elo = self_elo
        self.opponent_elo = opponent_elo
        self.elo_range_evaluated = elo_range_evaluated
        self.multipv = multipv
        self.nodes = nodes
        self.temperature = temperature
        self.top_p = top_p
        self.timeout = timeout
        self.device = device
        self.use_amp = use_amp
        self.use_uci_history = use_uci_history
        self.command = build_command(
            engine_path,
            model=model,
            device=device,
            use_amp=use_amp,
            use_uci_history=use_uci_history,
        )
        self._engine: "chess.engine.SimpleEngine | None" = None
        
        for Elo, Elo_range in MAIA_ELOS.items() :
            if Elo_range[0] == elo_range_evaluated[0] and Elo_range[1] == elo_range_evaluated[1] :
                if elo != Elo :
                    self.elo = Elo 
                    
                
                

    def __enter__(self) -> "MaiaAnalyzer":
        self._engine = chess.engine.SimpleEngine.popen_uci(
            self.command,
            timeout=self.timeout,
        )
        self._configure_if_supported("Elo", self.elo)
        self._configure_if_supported("SelfElo", self.self_elo)
        self._configure_if_supported("OppoElo", self.opponent_elo)
        self._configure_if_supported("MultiPV", self.multipv)
        self._configure_if_supported("Temperature", self.temperature)
        self._configure_if_supported("TopP", self.top_p)
        return self

    def __exit__(self, *exc) -> None:
        if self._engine is not None:
            self._engine.quit()
            self._engine = None

    def _configure_if_supported(self, name: str, value) -> None:
        if self._engine is None or value is None:
            return
        try:
            self._engine.configure({name: value})
        except chess.engine.EngineError:
            pass

    def predict(self, board: "chess.Board") -> MaiaPrediction:
        """Return Maia's predicted human move for ``board``."""
        if self._engine is None:
            raise RuntimeError("MaiaAnalyzer must be opened with a context manager.")

        if self.multipv > 1:
            return self._predict_with_candidates(board)

        result = self._engine.play(board, chess.engine.Limit(nodes=self.nodes))
        best_move = result.move
        return MaiaPrediction(
            best_move=best_move,
            best_san=_safe_san(board, best_move),
            elo=self.elo,
            candidate_moves=[best_move] if best_move else [],
            candidate_sans=[_safe_san(board, best_move)] if best_move else [],
        )

    def _predict_with_candidates(self, board: "chess.Board") -> MaiaPrediction:
        infos = self._engine.analyse(
            board,
            chess.engine.Limit(nodes=self.nodes),
            multipv=self.multipv,
        )
        if isinstance(infos, dict):
            infos = [infos]

        candidate_moves = [
            info["pv"][0]
            for info in infos
            if info.get("pv")
        ]
        candidate_sans = [_safe_san(board, move) for move in candidate_moves]
        best_move = candidate_moves[0] if candidate_moves else None

        return MaiaPrediction(
            best_move=best_move,
            best_san=_safe_san(board, best_move),
            elo=self.elo,
            candidate_moves=candidate_moves,
            candidate_sans=candidate_sans,
        )


def _safe_san(board: "chess.Board", move: "chess.Move | None") -> str:
    if move is None:
        return "?"
    try:
        return board.san(move)
    except Exception:
        return move.uci()


@contextmanager
def open_maia_analyzer(engine_path: str | None = None, **kwargs):
    """Resolve Maia, open it once, and yield a ``MaiaAnalyzer``."""
    path = find_engine(engine_path)
    if not path:
        raise RuntimeError(
            "No Maia UCI engine found. Install Maia 3, make sure maia3-uci or "
            "maia3-5m is on PATH, or pass an explicit Maia engine path."
        )
    with MaiaAnalyzer(path, **kwargs) as analyzer:
        yield analyzer


# Backwards-compatible alias while experimenting interactively.
open_analyzer = open_maia_analyzer
