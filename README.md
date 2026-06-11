# AI cheat-detection system for chess

A toolkit for spotting engine-assisted cheating in online chess games. It grades
each move of a game against a chess engine and then aggregates those grades
across many games into a **statistical suspicion profile** for a player.

> **What this is not:** it does not "prove" anyone cheats. It produces the same
> kind of statistical evidence that Chess.com and Lichess feed to *human*
> reviewers. Any decision about a real account should always involve a person
> looking at the underlying games. See [Ethics & limits](#ethics--limits).

---

## Why this design

You floated three starting points. Here's where each landed and why:

| Idea | Verdict | Reason |
|------|---------|--------|
| **1. Analyse the moves themselves** | ✅ Built (core) | The single most reliable signal. Yes, strong cheaters throttle their engine to look human — but that throttling *itself* leaves statistical fingerprints once you look across many games. |
| **2. Look at the track record across games** | ✅ Built (profiling layer) | A single brilliant game proves nothing; humans have good days. Patterns *across* games (consistently tiny error, robotic low variance, sudden rating jumps) are what actually distinguish a cheater. This is the heart of real anti-cheat. |
| **3. Inspect the suspect's computer for a running bot** | ❌ Deliberately not built | Scanning someone else's machine for processes is invasive, needs consent and a client install, and is legally/ethically fraught. It's documented below as the "client-side anti-cheat" path so you can decide later — but it's a fundamentally different (and riskier) product than server-side analysis. |

The reason idea #1 isn't hopeless against adaptive cheaters: a player who only
consults an engine in *critical* positions shows a telltale split — near-perfect
play in sharp middlegames but ordinary endgames, or a move-time pattern that
doesn't match the difficulty of the position. The metrics here are bucketed by
game phase precisely so those splits surface.

---

## How it works

```
PGN file ──► analyze.py ──► per-move grades ──► metrics.py ──► per-game summary
                  │                                                   │
              engine.py                                          profile.py
            (Stockfish/UCI)                                  (cross-game scoring)
                                                                     │
                                                                     ▼
                                                          suspicion score + reasons
```

1. **`engine.py`** owns one long-lived UCI engine process (Stockfish by
   default) and answers "what's the best move here and how good is the
   position?" for any board.
2. **`analyze.py`** walks every move of a game. For each move it records: the
   engine's preferred move, whether the player matched it, and how many
   centipawns the move threw away.
3. **`metrics.py`** is pure math (no engine, no I/O — fully unit-tested). It
   converts raw centipawns into **win %** and per-move **accuracy**, and
   aggregates a side's moves into a game summary.
4. **`profile.py`** combines many games for one player into a 0–100 **suspicion
   score** with human-readable reasons.

### The metrics

- **ACPL (average centipawn loss)** — mean centipawns lost per move vs the
  engine's best. Lower = stronger/cleaner. Per-move loss is capped at 1000cp so
  one walk-into-mate doesn't swamp the average.
- **Engine top-move match %** — how often the player chose the engine's #1 move.
  Very high sustained match rates are the classic cheating tell.
- **Accuracy** — a 0–100 score per move derived from how much *win %* (not raw
  centipawns) the move gave up, so errors are weighted by how much they actually
  change the practical result.
- **Per-phase breakdown** — all of the above split into opening / middlegame /
  endgame, to expose selective engine use.
- **Cross-game variance** — humans are streaky; bots are metronomic. Unusually
  low game-to-game variance is itself a flag.

---

## Install

Requires Python 3.10+ and a UCI engine (Stockfish recommended).

```bash
# 1. Engine (macOS; use your package manager elsewhere, or download a binary)
brew install stockfish

# 2. Python deps in a virtualenv (Python is "externally managed" on most setups)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

The pure-math layer (`metrics.py`) and its tests run with **no** dependencies at
all — handy for development before you install anything.

---

## Usage

```bash
# Grade every game in a PGN, per side
.venv/bin/python -m chesscheat.cli analyze data/sample.pgn --depth 16

# Profile one player across all games in a PGN
.venv/bin/python -m chesscheat.cli profile data/sample.pgn --player Morphy --depth 16
```

Common flags: `--engine /path/to/binary` (if not on PATH), `--depth N` (search
depth; higher = slower but more accurate), `--threads N`.

### Example output

```
=== Profile: Morphy ===
  games analysed : 1
  avg ACPL       : 9.4  (stdev 0.0)
  avg top-move % : 88.2
  avg accuracy   : 97.5
  total blunders : 0

  SUSPICION SCORE: 75/100
  reasons:
    - Only 1 game(s) analysed — below the 3-game minimum ...
    - Very low average centipawn loss (9.4).
    - Very high engine top-move match (88.2%).
```

(Yes — Morphy's *Opera Game* scores as "suspicious". That's the right lesson:
on a single brilliant game these metrics light up for anyone, which is exactly
why the tool demands multiple games and a human reviewer.)

---

## Project layout

```
chesscheat/
  engine.py     UCI engine wrapper (Stockfish). Swappable / mockable.
  analyze.py    Single-game, move-by-move analysis -> GameReport
  metrics.py    Pure math: win%, accuracy, per-game aggregation (no deps)
  profile.py    Cross-game suspicion scoring + reasons
  cli.py        Command-line entry point (analyze / profile)
data/
  sample.pgn    A legal sample game (Morphy, Opera Game)
tests/
  test_metrics.py   Dependency-free unit tests for the math layer
requirements.txt
```

Run the tests:

```bash
python3 -m unittest discover -s tests -v
```

---

## Calibration (read before trusting the numbers)

The thresholds in `profile.py` (`THRESHOLDS`) are **conservative starting
points, not science.** ACPL and match % depend heavily on:

- **Engine depth** — deeper search changes "best move", which changes match %.
- **Rating level** — a 2600 GM legitimately has low ACPL; a 1200 player with
  the same ACPL is far more suspicious. Thresholds should be rating-relative.
- **Time control** — bullet games are noisier than classical.

To calibrate properly you need a **labelled dataset**: games from known-clean
players and from confirmed-banned accounts, ideally bucketed by rating and time
control. Then tune the thresholds (or replace the hand-weighted score with a
trained classifier) so false-positive rate stays low. **Minimising false
positives matters more than catching everyone** — a wrong cheating accusation is
very costly.

---

## Roadmap / where to take this next

Ordered roughly by value-for-effort:

1. **Rating-relative thresholds** — accept each player's rating and compare
   their metrics against the expected distribution for that rating.
2. **Move-time analysis** — pull clock times from PGN (`%clk` tags). Humans
   spend longer on hard moves; engine users often play hard moves *instantly*
   and easy moves slowly (waiting to look human). This is a strong independent
   signal and needs no engine.
3. **Online fetchers** — pull a player's recent games directly from the
   Lichess (`/api`) or Chess.com public APIs instead of needing a PGN file.
4. **Labelled-data calibration + ML** — replace the hand-weighted suspicion
   score with a classifier trained on clean-vs-banned games (see Calibration).
5. **"Roll-up" report** — HTML/PDF per-player report with charts (win% graph,
   per-phase bars) for a human reviewer.
6. **Opening-book filtering** — don't penalise/credit book opening moves; only
   grade moves once the players are out of theory.

### The deferred idea #3: client-side anti-cheat

If you ever want to pursue "look inside the person's computer", understand what
it actually requires and costs:

- It only works as a **consenting client install** (like tournament anti-cheat
  software or game anti-cheat), not as something you run against a stranger's
  machine — doing the latter without authorisation is illegal in most places.
- It would watch for a second chess engine process, suspicious window focus
  switches, clipboard activity, virtual machines, etc.
- It's an arms race with high false-positive and privacy risk, and it's a
  completely separate codebase from this server-side analyser.

Recommendation: keep building the server-side statistical approach (idea #1+#2),
which is what every major chess site relies on, and treat client-side as a
last-resort, consent-gated add-on.

---

## Ethics & limits

- This is a **decision-support** tool, not a judge. Output is probabilistic.
- Always have a human review flagged games before acting on an account.
- Strong legitimate players *will* trip the metrics on their best games — that's
  why multiple games and rating context are required.
- Optimise for **few false positives.** A false ban is worse than a missed
  cheater.
