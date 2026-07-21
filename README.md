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

### Optional: installing Maia for human-like move analysis

Stockfish is the main engine used by the current codebase. Maia is optional for
the next analysis layer: instead of asking "what is the objectively best move?",
Maia asks "what move would a human around this rating probably play?".

I recommend starting with **Maia 3**, because it exposes a UCI-style engine
interface and has small models that can run on CPU.

```bash
# From inside this project, after creating the venv above
mkdir -p external
git clone https://github.com/CSSLab/maia3.git external/maia3
.venv/bin/pip install -e external/maia3

# Download/cache the smallest model first.
# This avoids the first analysis run waiting on a model download.
.venv/bin/maia3-cache --model maia3-5m

# Check the available Maia model aliases
.venv/bin/maia3-uci --list-models
```

Useful Maia 3 model choices:

- `maia3-5m` — best first try; smaller and more realistic for local CPU use.
- `maia3-23m` — better move prediction, slower.
- `maia3-79m` — strongest Maia 3 model, but much heavier.

Maia 3 downloads model checkpoints from Hugging Face the first time they are
used, then reuses the cached copy. If the laptop is struggling, use `maia3-5m`
before trying larger models.

Maia 1 is another option, but it is older and works differently: the Maia 1
models are LCZero weights, so they need the `lc0` engine as the "body" and Maia
as the "brain". For this project, Maia 3 is the simpler starting point.

## Usage

```bash
# Grade every game in a PGN, per side
.venv/bin/python -m chesscheat.cli analyze data/sample.pgn --depth 16

# Profile one player across all games in a PGN
.venv/bin/python -m chesscheat.cli profile data/sample.pgn --player Morphy --depth 16
```

Flags: `--engine /path/to/binary` if it's not on PATH, `--depth N` (deeper =
slower but more accurate), `--threads N`.

### Local datasets used for benchmarking

There are two different kinds of PGN files in `data/`, and I keep them separate
because they answer different questions.

**Standard rated games** are ordinary Lichess rated games. These are the best
fit for building baseline benchmarks by Elo range, because they represent
normal online play rather than tournament broadcast relays.

I merged the standard rated files currently present in `data/` into:

```text
data/lichess_db_standard_rated_selected.pgn
```

Files included:

- `data/lichess_db_standard_rated_2013-09.pgn`
- `data/lichess_db_standard_rated_2013-10.pgn`
- `data/lichess_db_standard_rated_2013-11.pgn`
- `data/lichess_db_standard_rated_2013-12.pgn`
- `data/lichess_db_standard_rated_2017-02.pgn`

Verification after merging:

```text
source games: 11996350
merged games: 11996350
merged size: 10.0 GB
```

This merged file is large, so benchmarking the whole thing with Stockfish will
be slow. In practice, use `--nb_game` to sample a fixed number of matching games
per Elo range.

**Broadcast games** are tournament/study relay games. They are useful for
experiments, but they are noisier for benchmark calibration because broadcasts
can contain missing Elo tags, malformed moves, interrupted games, illegal SAN,
or corrected relay positions.

The broadcast files currently present in `data/` have been merged into:

```text
data/lichess_db_broadcast_2026-01_05_06.pgn
```

Files included:

- `data/lichess_db_broadcast_2026-01.pgn`
- `data/lichess_db_broadcast_2026-05.pgn`
- `data/lichess_db_broadcast_2026-06.pgn`

Verification after de-duplicating by `GameURL`:

```text
source games: 99805
merged games: 99805
duplicates skipped: 0
merged size: 404 MB
```

I do **not** merge broadcast files into the standard benchmark file. Mixing them
would blur the baseline: standard rated games describe ordinary online play,
while broadcast PGNs describe tournament relay data with different quality and
metadata assumptions.

Typical standard benchmark command:

```bash
.venv/bin/python -m chesscheat.cli general_bench data/lichess_db_standard_rated_selected.pgn --depth 10 --threads 8 --nb_game 150
```

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

## Stockfish vs Maia

Stockfish and Maia answer different questions, so they should not be treated as
interchangeable.

**Stockfish** is an objective-strength engine. It tries to find the best chess
move. In this project it gives the classic cheat-detection signals:

- centipawn loss: how much quality the played move gave up;
- top-move match: whether the player chose Stockfish's first choice;
- accuracy: how much the move changed the expected result.

That makes Stockfish good for measuring **how close the player is to optimal
engine play**.

**Maia** is a human-move model. It is trained to predict moves humans actually
play at different rating levels. It is not mainly trying to be the strongest
engine. It is trying to be human-like.

That makes Maia useful for measuring **how plausible a move is for a player of
that Elo range**.

The important cheat-analysis idea is to combine both signals:

```
Stockfish says: this move is extremely strong
Maia says: humans at this Elo almost never play this move
```

That combination is more interesting than Stockfish alone. A single Stockfish
match can happen naturally, especially in obvious positions or known openings.
But repeated moves that are both:

- very strong according to Stockfish, and
- unlikely according to Maia for that rating range,

are a stronger signal that the play may not be natural for that Elo group.

For Elo-range benchmarking, Maia can help build rating-relative baselines:

- compare a 1500 player against a 1500-ish Maia setting;
- compare a 2200 player against a 2200-ish Maia setting;
- avoid using the same expectation for every rating group.

In other words:

```
Stockfish = objective move quality
Maia      = human-likeness for the Elo range
Both      = better benchmark signal
```

Maia is now treated as an optional second analysis path, not as a blind
replacement for Stockfish, because Maia does not provide the same kind of
centipawn-loss meaning.

## Layout

```
chesscheat/
  engine.py     UCI engine wrapper (Stockfish)
  maia.py       UCI wrapper for Maia human-move prediction
  analyze.py    Single-game move-by-move analysis -> GameReport
  metrics.py    Pure math: win%, accuracy, aggregation (no deps)
  profile.py    Cross-game suspicion scoring + reasons
  cli.py        CLI entry point (analyze / profile)
benchmark_data/
  standard/       Elo-range benchmark summaries from standard rated games
  broadcast/      Elo-range benchmark summaries from broadcast games
results/
  standard_games/ Profile outputs from standard rated games
  broadcast_games/Profile outputs from broadcast games
data/
  lichess_db_standard_rated_selected.pgn      Merged standard rated games for Elo benchmarks
  lichess_db_broadcast_2026-01_05_06.pgn      Merged broadcast games, kept separate from standard
scripts/
  merge_pgn_datasets.py                       Streaming PGN merge utility with duplicate detection
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

## Potential improvements

The project already has the important benchmark hygiene pieces in place: fixed
sample counts through `--nb_game`, separate standard/broadcast benchmark
folders, Elo-range benchmarking, and pre-analysis filtering for Elo range
selection. The next improvements are less about adding raw features and more
about making the evidence easier to audit, visualize, and explain.

### 1. Make filtering auditable

Filtering is currently mostly silent. I want every benchmark/profile run to
produce a small metadata summary alongside the numerical result:

```text
games scanned
games outside Elo range
games skipped for missing/non-numeric Elo
games skipped for invalid PGN / illegal SAN
games skipped for being too short
games analysed
source file
Stockfish depth / threads
Maia model / Elo / MultiPV
```

This would make it clear whether a result is based on a healthy sample or on a
thin/noisy slice of the dataset.

### 2. Moderate the score with confidence

The suspicion score should not be read as a verdict. It should be presented as:

```text
suspicion score
confidence level
main reasons
data-quality warnings
```

For example, a high score from only five games should be visibly weaker than a
similar score from 100 clean games. The final output should say "worth human
review", not "cheater".

### 3. Split the score into sub-scores

The current score is useful, but a single number hides the evidence. A better
report would separate:

```text
Stockfish strength score      low ACPL, high accuracy, high top-move match
Maia plausibility score       how human-like the moves are for the Elo range
Consistency score             unusually low game-to-game variance
Data quality score            sample size and skipped-game quality
```

This makes the output easier to challenge and easier to improve.

### 4. Use stronger Stockfish + Maia combined metrics

Low Maia match alone is not suspicious: a player can simply make bad or unusual
human moves. The stronger signal is the mismatch between objective strength and
human plausibility:

```text
Stockfish likes the move
Maia says humans at this Elo usually do not play it
```

Useful future metrics:

```text
stockfish_top_not_maia_top_k_pct
low_cp_loss_not_maia_top_k_pct
maia_top_k_match_pct
maia_rank_of_played_move
```

These are more meaningful than treating Maia mismatch as suspicious by itself.

### 5. Add reviewer-friendly visualizations

The JSON outputs are useful for machines, but human review needs pictures. The
most useful first charts would be:

- **ACPL distribution by Elo range** — benchmark distribution with the profiled
  player marked.
- **Stockfish match % vs Maia match % scatter plot** — the suspicious quadrant
  is high Stockfish match with low Maia plausibility.
- **Per-game timeline** — ACPL, accuracy, top-move match, and Maia match across
  games to reveal sudden changes or unusually stable performance.
- **Phase breakdown** — opening / middlegame / endgame, because selective
  engine use often appears in sharp middlegames rather than everywhere.
- **Move-level review table** — played move, Stockfish best move, Maia predicted
  move, CP loss, Stockfish match, Maia match/top-k, and a review flag.

### 6. Add opening-book and short-game handling

Opening theory can inflate Stockfish match percentage, and very short games can
make all percentages noisy. Future benchmark/profile runs should explicitly
record:

```text
opening moves skipped or counted separately
minimum analysed moves per side
number of games excluded as too short
```

### 7. Improve reproducibility

Every benchmark should be reproducible from its output files. The saved JSON
should eventually include:

```text
dataset type: standard or broadcast
source PGN
engine versions
Stockfish depth
Maia model and Elo settings
sample target
random seed if random sampling is used
created timestamp
```

That way, results can be compared months later without guessing how they were
generated.

### 8. Longer-term improvements

- Move-time analysis from PGN clock tags (`%clk`): humans usually spend more
  time on hard moves; engine users can show a different timing profile.
- Pull games from Lichess/Chess.com APIs instead of requiring local PGN files.
- Labelled-data calibration with clean and confirmed-engine-use examples.
- A trained classifier only after the hand-built features are trustworthy.
- A small HTML report for human reviewers.

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
