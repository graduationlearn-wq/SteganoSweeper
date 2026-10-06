# Minesweeper Gameplay Steganography

A research-oriented Minesweeper system that explores **steganography through gameplay decision sequences** rather than directly modifying the hidden mine layout.

The project combines a clickable Minesweeper environment, gameplay data collection, logical solving, probability estimation, human-behavior modeling, and adaptive steganographic move selection.

---

## Research Idea

Traditional Minesweeper-based steganography can use the hidden mine configuration as a carrier.

This project investigates a different carrier:

> **The sequence of gameplay decisions made during a Minesweeper session.**

The central research question is:

> **How much information can be embedded into Minesweeper gameplay while keeping the resulting sequence safe, playable, and behaviorally similar to natural human gameplay?**

The long-term goal is to select among multiple plausible moves so that the selected move carries information while still looking like a normal player's decision.

---

## Current Architecture

```text
                ┌──────────────────────┐
                │ Clickable Minesweeper │
                └──────────┬───────────┘
                           │
                           ▼
                ┌──────────────────────┐
                │ Gameplay Data Logger │
                └──────────┬───────────┘
                           │
                           ▼
                  human_gameplay.csv
                           │
                           ▼
                ┌──────────────────────┐
                │ Human Behavior Model │
                └──────────┬───────────┘
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
      Solver / Risk Model         Steganographic
                                      Encoder
             │                           │
             └─────────────┬─────────────┘
                           ▼
                   Gameplay Sequence
                           │
                           ▼
                    Blind Decoder
```

---

## Project Components

### `clickable_minesweeper.py`

A graphical Minesweeper implementation built with Tkinter.

Features include:

- Left-click to reveal cells
- Right-click to flag/unflag cells
- Double-click/chording on revealed numbers
- Mine counter
- Timer
- Restart button
- First-click-safe board generation
- Win/loss detection
- Automatic gameplay logging

The interface is designed to let a human play naturally without entering candidate indices manually.

---

### `minesweeper.py`

Core Minesweeper game logic.

Responsibilities include:

- Board generation
- Mine placement
- Neighbor calculation
- Number generation
- Reveal/flood-fill behavior
- Flag handling
- Game state
- Win/loss logic

---

### `solver.py`

Visible-state Minesweeper solver.

The solver uses information available from the revealed board rather than directly inspecting hidden mines for decision making.

It can derive:

- Guaranteed safe cells
- Guaranteed mines
- Constraint relationships
- Candidate cells
- Estimated mine probabilities

Basic Minesweeper constraints can be represented as:

\[
\sum_{j \in U_i} x_j = k_i
\]

where:

- \(U_i\) = unknown neighboring cells around a revealed number
- \(x_j \in \{0,1\}\) indicates whether a cell contains a mine
- \(k_i\) = number of remaining mines implied by the clue

---

### `encoder.py`

Adaptive gameplay steganography.

The encoder represents the secret as a numerical value and embeds information through the choice of gameplay moves.

Instead of forcing a fixed number of bits per move, the project uses a variable radix:

\[
b_t = \log_2(R_t)
\]

where \(R_t\) is the number of usable candidate choices at step \(t\).

The theoretical capacity over a sequence of moves is:

\[
C = \sum_{t=1}^{T} \log_2(R_t)
\]

This is the basis of the mixed-radix encoding approach.

---

### `decoder.py`

Blind replay decoder.

The intended receiver is given the gameplay sequence rather than the secret message.

For each move:

\[
d_t = \text{index of selected move among candidate choices}
\]

The move sequence can then be interpreted as digits in a mixed-radix representation.

The decoder reconstructs the embedded integer and extracts:

- Sentinel
- Payload length
- Message bytes

The research goal is that the receiver can recover the message from the replay without being explicitly given the secret bit sequence.

---

### `behavior_model.py`

Human gameplay behavior modeling.

The current framework extracts features such as:

- Safety / estimated mine risk
- Information value
- Locality
- Frontier relationship
- Distance from previous action

A probability distribution over candidate moves can be represented using softmax:

\[
P(i \mid s)
=
\frac{e^{z_i}}
{\sum_j e^{z_j}}
\]

where:

- \(s\) = current game state
- \(i\) = candidate move
- \(z_i\) = score/logit for candidate \(i\)

The current heuristic system is intended as a baseline. The longer-term goal is to train the model from actual human gameplay data.

---

## Human Gameplay Dataset

The clickable interface automatically records gameplay into:

```text
human_gameplay.csv
```

The dataset is intended to represent the information available to a human player at decision time.

Examples of recorded information include:

- Session ID
- Game ID
- Game seed
- Board dimensions
- Mine count
- Step number
- Timestamp
- Time between actions
- Action type
- Cell coordinates
- Whether the action was the first move
- Revealed cells before and after the action
- Flags before and after the action
- Remaining mine count
- Adjacent revealed cells
- Hidden neighboring cells
- Frontier score
- Distance from previous action
- Visible board before the action
- Visible board after the action
- Action outcome
- Game status

Hidden mine positions should not be included in the human-behavior dataset used to model player decisions.

---

## Human Mistakes Are Part of the Dataset

A key design decision is that mistakes are not discarded.

Examples include:

```text
Safe move
Mine hit
Incorrect flag
Unflag
Early loss
Late-game loss
Game win
```

This is important because the objective is to learn **actual human behavior**, not ideal solver behavior.

A human player may:

- make an incorrect inference
- choose a risky cell
- misclick
- flag incorrectly
- change their mind
- lose early
- make a final mistake near the end of a game

These behaviors can provide useful signals for modeling behavioral realism.

---

## First-Click Rule

The current Minesweeper environment protects the first clicked cell and its neighboring cells when placing mines.

This prevents an immediate first-click loss and produces a more conventional Minesweeper experience.

The first click is therefore treated as board initialization rather than as a meaningful risky human decision.

---

## Research Methodology

The planned research pipeline consists of the following stages.

### Stage 1 — Human Gameplay Collection

Collect natural human gameplay through the clickable interface.

The player simply plays Minesweeper normally.

No manual candidate indexing is required.

---

### Stage 2 — Candidate Generation

For each decision state, generate plausible candidate moves using the solver and risk model.

Candidate choices can be grouped into:

```text
Guaranteed Safe
Low Risk
Risk-Based
```

depending on the available information.

---

### Stage 3 — Feature Extraction

For every candidate move, compute features such as:

\[
\text{risk}(c)
\]

\[
\text{information}(c)
\]

\[
\text{locality}(c)
\]

\[
\text{frontier}(c)
\]

along with temporal and contextual features.

---

### Stage 4 — Human Behavior Model

Train a model to estimate:

\[
P(c \mid s)
\]

meaning:

> the probability that a human would select candidate \(c\) in game state \(s\).

Possible baseline models include:

- Logistic Regression
- Random Forest
- Gradient Boosting
- Other calibrated classifiers

The learned probabilities can later replace or augment the handcrafted heuristic model.

---

## Behavioral Entropy

If the human model assigns probabilities \(p_i\) to candidate moves, behavioral entropy is:

\[
H(P) =
-\sum_i p_i \log_2 p_i
\]

For \(N\) equally likely candidate choices, the maximum entropy is:

\[
H_{\max} = \log_2 N
\]

A normalized behavioral efficiency can be defined as:

\[
\eta =
\frac{H(P)}{\log_2 N}
\]

A value close to 1 indicates behavior close to a uniform distribution over available choices.

---

## Mixed-Radix Steganography

Suppose there are \(R_t\) usable choices at move \(t\).

Rather than forcing every move to encode a fixed number of bits, the system treats the candidate index as a digit:

\[
d_t \in \{0,1,\ldots,R_t-1\}
\]

The gameplay sequence therefore behaves like a mixed-radix number.

The selected move is determined by:

\[
d_t = V \bmod R_t
\]

followed by:

\[
V \leftarrow \left\lfloor \frac{V}{R_t} \right\rfloor
\]

where \(V\) is the remaining message value.

The information capacity of move \(t\) is:

\[
C_t = \log_2 R_t
\]

and total theoretical capacity is:

\[
C =
\sum_t \log_2 R_t
\]

---

## Example

Suppose three consecutive decisions have:

```text
R₁ = 8
R₂ = 5
R₃ = 10
```

Then:

\[
C =
\log_2(8)
+
\log_2(5)
+
\log_2(10)
\]

\[
C \approx
3 + 2.322 + 3.322
= 8.644 \text{ bits}
\]

This is more efficient than restricting every move to a power-of-two number of choices.

---

## Capacity vs. Effective Payload

The theoretical capacity is not necessarily equal to useful payload capacity.

Practical overhead can include:

- Sentinel
- Payload length
- Synchronization information
- Error-handling information
- Forced moves
- Risk restrictions
- Candidate limitations

Therefore, experiments should report both:

\[
C_{\text{theoretical}}
\]

and

\[
C_{\text{effective}}
\]

---

## Risk Modeling

For a candidate cell \(c\), the estimated mine probability is:

\[
P(M_c = 1 \mid S)
\]

where \(S\) represents the visible board state.

The system can classify candidate choices using thresholds such as:

```text
0%       → Guaranteed Safe
Low %    → Low Risk
Higher % → Risk-Based
100%     → Guaranteed Mine
```

A risk-aware encoder can prioritize candidates that provide sufficient encoding capacity without making gameplay obviously unsafe.

---

## Behavioral Similarity

A major research objective is not simply:

> Can the secret message be decoded?

It is also:

> Does the resulting gameplay look like natural human gameplay?

If \(P_H\) is the human behavior distribution and \(P_S\) is the steganographic behavior distribution, one possible comparison is Jensen-Shannon divergence.

First define:

\[
M = \frac{1}{2}(P_H + P_S)
\]

Then:

\[
JS(P_H,P_S)
=
\frac{1}{2}D_{KL}(P_H\|M)
+
\frac{1}{2}D_{KL}(P_S\|M)
\]

where:

\[
D_{KL}(P\|Q)
=
\sum_i P_i\log\frac{P_i}{Q_i}
\]

Lower divergence indicates greater behavioral similarity.

---

## Main Evaluation Metrics

The final experimental system should measure:

### 1. Embedding Capacity

\[
\text{bits/move}
=
\frac{\text{payload bits}}
{\text{carrier moves}}
\]

---

### 2. Decoding Accuracy

\[
\text{Accuracy}
=
\frac{\text{correctly recovered bits}}
{\text{total embedded bits}}
\]

The strongest outcome is exact message recovery.

---

### 3. Mine-Hit Rate

\[
\text{Mine Hit Rate}
=
\frac{\text{mine-hit actions}}
{\text{reveal actions}}
\]

Lower is generally preferable for a playable carrier.

---

### 4. Win Rate

\[
\text{Win Rate}
=
\frac{\text{games won}}
{\text{games played}}
\]

---

### 5. Behavioral Similarity

Compare human and steganographic gameplay distributions using metrics such as:

- Jensen-Shannon divergence
- KL divergence
- Cross-entropy
- Timing distribution similarity
- Move locality similarity

---

### 6. Steganalysis Detection Rate

Train a classifier to distinguish:

```text
Human gameplay
vs.
Steganographic gameplay
```

A good stealth-oriented system should make this classification difficult.

A useful evaluation is:

\[
\text{Detection Accuracy}
\approx 50\%
\]

for a balanced binary classification task, although the exact interpretation depends on the experimental design and classifier.

---

## Baselines

The research should compare several systems:

```text
Random Player
      ↓
Rule / Solver Player
      ↓
Heuristic Human Model
      ↓
Learned Human Model
      ↓
Steganographic Encoder
```

This helps determine whether improvements are actually coming from the behavior model and not simply from solving Minesweeper better.

---

## Ablation Studies

Useful ablations include:

### Without Human Model

Use solver/risk ranking only.

### Heuristic vs. Learned Behavior

Compare handcrafted scoring with ML-based probabilities.

### Without Risk Constraint

Allow more candidate moves and measure the effect on mine risk.

### Fixed-Radix vs. Mixed-Radix

Compare fixed bits-per-move encoding with:

\[
\log_2(R_t)
\]

adaptive capacity.

### Without Behavioral Optimization

Measure how detectable the gameplay becomes.

---

## Current Status

The project currently includes:

- Clickable Minesweeper interface
- First-click-safe board generation
- Human gameplay logging
- CSV dataset generation
- Visible-state solver
- Logical constraint reasoning
- Exact probability estimation for manageable states
- Human-behavior feature framework
- Heuristic behavior scoring
- Adaptive mixed-radix steganographic encoding
- Blind replay decoding

The current development focus is:

> **Collecting real human gameplay and training a behavior model from observed player decisions.**

---

## Next Development Steps

```text
1. Stabilize gameplay logger
        ↓
2. Collect human gameplay sessions
        ↓
3. Convert raw logs into candidate-choice examples
        ↓
4. Train behavior model
        ↓
5. Calibrate predicted probabilities
        ↓
6. Integrate learned behavior model
        ↓
7. Generate steganographic gameplay
        ↓
8. Decode from replay
        ↓
9. Compare human vs. steganographic behavior
        ↓
10. Perform steganalysis experiments
```

---

## Repository Structure

```text
Minesweeper/
│
├── clickable_minesweeper.py
├── minesweeper.py
├── solver.py
├── encoder.py
├── decoder.py
├── behavior_model.py
├── experiments.py
├── data_collector.py
│
├── human_gameplay.csv        # ignored by Git
│
├── .gitignore
└── README.md
```

---

## Running the Game

Make sure Python 3 is installed.

Run:

```bash
python clickable_minesweeper.py
```

The graphical interface should open.

### Controls

```text
Left Click   → Reveal
Right Click  → Flag / Unflag
Double Click → Chord a revealed number
Reset        → Start a new game
```

Gameplay data is automatically written to:

```text
human_gameplay.csv
```

---

## Research Caveat

This project should be presented as an **experimental research framework**, not as a claim that Minesweeper gameplay steganography itself is unprecedented.

The research contribution is being developed around the combination of:

- gameplay-sequence steganography
- adaptive candidate-space capacity
- risk-aware move selection
- learned human behavior
- behavioral similarity
- steganalysis

The novelty and positioning should ultimately be validated through a systematic literature review.

---

## Author

**Arnav Kumar**
**Raunak Shukla**

B.Tech AI & ML

This repository is intended for academic research and experimentation.