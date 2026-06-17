# AI cheat-detection system for chess

This is my project to detect engine-assisted cheating in online chess. The idea
is to grade each move of a game against a chess engine, then look at how those
grades stack up across many of a player's games to decide whether something
looks off.

It does not "prove" anyone cheats — it produces statistical evidence, the same
kind of thing Chess.com and Lichess generate and then hand to a human reviewer.
I'm treating the output as decision-support, never as a verdict.

## Where I started and why

I had three angles when I began (notes to self so I remember the reasoning):

**Analysing the moves themselves** — this is the core of what I built. It's the
most reliable signal. The obvious objection is that a smart cheater throttles
their engine to look human, but that throttling leaves its own fingerprints once
you stop looking at a single game and look at a whole history.

**Looking at the track record across games** — also built. One brilliant game
means nothing; everyone has good days. What separates a cheater is the pattern
over many games: consistently tiny error, suspiciously low variance, a rating
that suddenly jumps. This is really the heart of the thing.

**Inspecting the suspect's computer for a running bot** — I decided not to build
this. Scanning someone else's machine needs consent and a client install, and
doing it to a stranger is illegal in most places. I've left notes at the bottom
on what it would actually take if I ever revisit it, but it's a completely
different (and riskier) project from server-side analysis.

One thing worth remembering about the move-analysis angle: a player who only
uses an engine in critical positions tends to show a split — near-perfect sharp
middlegames but ordinary endgames, or move times that don't match how hard the
position is. That's why I bucket the metrics by game phase.

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

- **`engine.py`** runs one long-lived Stockfish (UCI) process and answers
  "best move here, and how good is the position?" for any board.
- **`analyze.py`** walks every move of a game and records the engine's best
  move, whether the player matched it, and how many centipawns the move lost.
- **`metrics.py`** is pure math (no engine, no I/O, so it's easy to test). It
  turns centipawns into win % and per-move accuracy and aggregates a side's
  moves into a game summary.
- **`profile.py`** combines a player's games into a 0–100 suspicion score with
  reasons in plain English.

### The metrics I'm using

- **ACPL (average centipawn loss)** — mean centipawns lost per move vs the
  engine's best. Lower is cleaner. I cap per-move loss at 1000cp so one move
  into a forced mate doesn't blow up the average.
- **Engine top-move match %** — how often the player picked the engine's first
  choice. A sustained high match rate is the classic tell.
- **Accuracy** — a 0–100 per-move score based on how much *win %* the move gave
  up (not raw centipawns), so mistakes are weighted by how much they actually
  change the result.
- **Per-phase breakdown** — all of the above split into opening / middlegame /
  endgame to catch selective engine use.
- **Cross-game variance** — humans are streaky, bots are metronomic, so low
  game-to-game variance is itself a flag.

## Install

Needs Python 3.10+ and a UCI engine (I'm using Stockfish).

```bash
# Engine (macOS; swap for your package manager elsewhere)
brew install stockfish

# Python deps in a venv (system Python is "externally managed" on most setups)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

The math layer and its tests run with no dependencies, which is handy before
installing anything.

## Usage

```bash
# Grade every game in a PGN, per side
.venv/bin/python -m chesscheat.cli analyze data/sample.pgn --depth 16

# Profile one player across all games in a PGN
.venv/bin/python -m chesscheat.cli profile data/sample.pgn --player Morphy --depth 16
```

Flags: `--engine /path/to/binary` if it's not on PATH, `--depth N` (deeper =
slower but more accurate), `--threads N`.

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

Morphy's Opera Game scoring as "suspicious" is the point: on a single brilliant
game these metrics light up for anyone, which is exactly why I require multiple
games and a human in the loop.

## Layout

```
chesscheat/
  engine.py     UCI engine wrapper (Stockfish)
  analyze.py    Single-game move-by-move analysis -> GameReport
  metrics.py    Pure math: win%, accuracy, aggregation (no deps)
  profile.py    Cross-game suspicion scoring + reasons
  cli.py        CLI entry point (analyze / profile)
data/
  sample.pgn    Legal sample game (Morphy, Opera Game)
tests/
  test_metrics.py   Dependency-free tests for the math layer
```

Run tests:

```bash
python3 -m unittest discover -s tests -v
```

## Calibration (don't trust the numbers yet)

The thresholds in `profile.py` are conservative guesses, not calibrated values.
ACPL and match % depend a lot on:

- **Engine depth** — deeper search changes the "best move", which changes match %.
- **Rating** — a 2600 GM legitimately has low ACPL; the same number from a 1200
  is far more suspicious, so thresholds should be rating-relative.
- **Time control** — bullet is much noisier than classical.

To do this properly I need a labelled dataset (known-clean vs confirmed-banned
games, bucketed by rating and time control) and then to tune the thresholds, or
replace the hand-weighted score with a trained classifier. The priority is
keeping false positives low — a wrong accusation is worse than a missed cheater.

## What's next

1. Rating-relative thresholds.
2. Move-time analysis from PGN clock tags (`%clk`) — humans think longer on hard
   moves; engine users often blitz the hard ones and stall on easy ones. Strong
   independent signal, needs no engine.
3. Pull games straight from the Lichess and Chess.com public APIs instead of
   needing a PGN file.
4. Labelled-data calibration, then an ML classifier.
5. A per-player HTML report with charts for a human reviewer.
6. Skip opening-book moves so theory isn't graded as brilliance.

### If I ever revisit the "scan the computer" idea

It only works as a consenting client install (like tournament or game anti-cheat
software), watching for a second engine process, suspicious window switching,
clipboard activity, VMs, etc. It's an arms race with real privacy and
false-positive risk and a separate codebase from this. Server-side statistics
(the approach here) is what the big sites actually rely on, so client-side stays
a last resort.

## Things to read

Background I'm using / want to go deeper on, grouped by angle.

### Chess + cheat detection specifically

- **Kenneth Regan's chess research page** — the academic authority on
  statistical cheating detection in chess. Start here.
  https://cse.buffalo.edu/~regan/chess/fidelity/
- **Regan & Haworth, "Intrinsic Chess Ratings" (AAAI 2011)** — models a
  player's move choices against engine evaluations; the basis of his
  cheating-detection z-score method.
  https://cse.buffalo.edu/~regan/papers/pdf/ReHa11.pdf
- **Regan, Macieja & Haworth, "Understanding Distributions of Chess
  Performances"** — how move-quality distributions vary with skill.
  https://cse.buffalo.edu/~regan/papers/pdf/RMH11b.pdf
- **irwin** — Lichess's open-source cheat-detection model. Reading the code is a
  great practical complement to the papers. https://github.com/clarkerubber/irwin
- **Lichess accuracy / win% writeup** — where the win-percent and accuracy
  formulas I used come from. https://lichess.org/page/accuracy

### Modelling human (not engine-best) play

- **McIlroy-Young et al., "Aligning Superhuman AI with Human Behavior: Chess as
  a Model System" (KDD 2020)** — the Maia engine, which predicts the move a
  human of a given rating would actually play. Useful because "did they match a
  human model?" is a different question from "did they match Stockfish?".
  https://arxiv.org/abs/2006.01855 · project: https://maiachess.com
- **McIlroy-Young et al., "Detecting Individual Decision-Making Style:
  Behavioral Stylometry in Chess" (NeurIPS 2021)** — identifying a player from
  their move patterns; relevant to spotting "this isn't how this account
  normally plays." https://arxiv.org/abs/2208.01366
- **CSSLab (Toronto) chess research + data** — the group behind Maia, with
  datasets and follow-up work. https://csslab.cs.toronto.edu/

### Datasets to practise on

- **Lichess open database** — billions of games in PGN, many with `%eval` and
  `%clk` already in them. The single best place to get real data, including for
  building a labelled set later. https://database.lichess.org/
- **Maia / CSSLab data** — preprocessed human-game data tied to the papers
  above. https://github.com/CSSLab/maia-chess
- **FICS games database** — older but large, useful for variety.
  https://www.ficsgames.org/

### Statistics & math background

- **Win-probability / logistic models** — the cp→win% mapping is just a logistic
  curve; understanding logistic regression makes the accuracy metric click.
- **Z-scores & hypothesis testing** — Regan's method is essentially "how many
  standard deviations is this player's performance from what their rating
  predicts?" Worth being solid on z-scores, p-values, and multiple-comparison
  pitfalls (test enough players and someone looks guilty by chance).
- **Precision/recall & ROC/AUC** — for evaluating the detector once I have
  labelled data; the false-positive cost asymmetry matters here.
- **Tools:** the **UCI protocol** (how engines talk) and the **python-chess**
  docs (https://python-chess.readthedocs.io/) — both are what `engine.py` is
  built on.

## A note on ethics

This is decision-support, not a judge. The output is probabilistic, strong
legitimate players will trip the metrics on their best games, and anything real
should have a human review the actual games first. I'm optimising for few false
positives — a false ban is worse than a missed cheater.
