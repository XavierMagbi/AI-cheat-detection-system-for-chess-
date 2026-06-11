"""Unit tests for the pure-math metrics layer.

These have no third-party dependencies, so they run even before you
`pip install -r requirements.txt`. Run with:  python -m pytest  (or unittest).
"""

import math
import unittest

from chesscheat.metrics import (
    MoveEval,
    accuracy_from_win_drop,
    cp_to_win_percent,
    summarize,
)


class TestWinPercent(unittest.TestCase):
    def test_even_position_is_fifty(self):
        self.assertAlmostEqual(cp_to_win_percent(0), 50.0, places=6)

    def test_monotonic(self):
        self.assertLess(cp_to_win_percent(-300), cp_to_win_percent(0))
        self.assertLess(cp_to_win_percent(0), cp_to_win_percent(300))

    def test_bounded(self):
        self.assertGreaterEqual(cp_to_win_percent(-99999), 0.0)
        self.assertLessEqual(cp_to_win_percent(99999), 100.0)


class TestAccuracy(unittest.TestCase):
    def test_no_drop_is_near_perfect(self):
        self.assertGreater(accuracy_from_win_drop(60.0, 60.0), 99.0)

    def test_big_drop_is_low(self):
        self.assertLess(accuracy_from_win_drop(80.0, 20.0), 20.0)

    def test_negative_drop_clamped(self):
        # Move that improves win% shouldn't exceed 100.
        self.assertLessEqual(accuracy_from_win_drop(40.0, 80.0), 100.0)


class TestSummarize(unittest.TestCase):
    def _move(self, ply, white, cp_loss, top, phase="middlegame"):
        return MoveEval(
            ply=ply, san="Nf3", is_white=white, phase=phase,
            best_san="Nf3", is_top_move=top, cp_loss=cp_loss,
            win_before=50.0, win_after=50.0,
            accuracy=accuracy_from_win_drop(50.0, 50.0 - cp_loss / 10),
        )

    def test_empty(self):
        s = summarize([], white=True)
        self.assertEqual(s["moves"], 0)

    def test_splits_by_side_and_counts_blunders(self):
        moves = [
            self._move(1, True, 10, True),
            self._move(2, False, 250, False),   # black blunder
            self._move(3, True, 5, True),
            self._move(4, False, 300, False),   # black blunder
        ]
        white = summarize(moves, white=True)
        black = summarize(moves, white=False)
        self.assertEqual(white["moves"], 2)
        self.assertEqual(white["blunders"], 0)
        self.assertEqual(white["top_move_pct"], 100.0)
        self.assertEqual(black["moves"], 2)
        self.assertEqual(black["blunders"], 2)

    def test_acpl_is_mean(self):
        moves = [self._move(1, True, 10, True), self._move(3, True, 30, False)]
        self.assertAlmostEqual(summarize(moves, white=True)["acpl"], 20.0)


if __name__ == "__main__":
    unittest.main()
