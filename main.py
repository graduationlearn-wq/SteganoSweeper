import math

from minesweeper import Minesweeper
from solver import MinesweeperSolver
from behavior_model import HumanBehaviorModel


def main():

    # ==============================================================
    # CONFIGURATION
    # ==============================================================

    rows = 16
    cols = 16
    mines = 40
    seed = 42

    opening_move = (7, 7)

    risk_tolerance = 0.05

    # ==============================================================
    # CREATE GAME
    # ==============================================================

    game = Minesweeper(
        rows=rows,
        cols=cols,
        mines=mines,
        seed=seed,
    )

    print("=" * 90)
    print(
        "MINESWEEPER BEHAVIORAL PROBABILITY ANALYSIS"
    )
    print("=" * 90)

    print("\nConfiguration")
    print("-" * 60)

    print(
        f"Board size       : "
        f"{rows} x {cols}"
    )

    print(
        f"Mines            : "
        f"{mines}"
    )

    print(
        f"Seed             : "
        f"{seed}"
    )

    print(
        f"Risk tolerance   : "
        f"{risk_tolerance * 100:.1f}%"
    )

    # ==============================================================
    # OPENING MOVE
    # ==============================================================

    print(
        f"\nOpening move: "
        f"{opening_move}"
    )

    game.reveal(
        opening_move[0],
        opening_move[1],
    )

    print(
        "\nBoard after opening move:"
    )

    game.display()

    # ==============================================================
    # SOLVER
    # ==============================================================

    solver = MinesweeperSolver(
        game,
        max_component_cells=20,
    )

    print(
        "\nSolver state:"
    )

    solver.print_reasoning_state()

    # Flag proven mines before probability analysis.
    flagged = (
        solver.flag_guaranteed_mines()
    )

    print(
        f"\nFlagged "
        f"{len(flagged)} guaranteed mines."
    )

    # ==============================================================
    # PROBABILITIES
    # ==============================================================

    probabilities = (
        solver.get_move_risks()
    )

    # ==============================================================
    # HUMAN MODEL
    # ==============================================================

    behavior = HumanBehaviorModel(
        risk_weight=0.45,
        information_weight=0.30,
        locality_weight=0.15,
        frontier_weight=0.10,
        temperature=1.0,
    )

    analysis = behavior.analyze_moves(
        game,
        probabilities,
        last_move=opening_move,
        risk_tolerance=risk_tolerance,
    )

    distribution = (
        analysis["distribution"]
    )

    # ==============================================================
    # BEHAVIORAL DISTRIBUTION
    # ==============================================================

    print(
        "\nHuman-behavior probability distribution:"
    )

    print("-" * 100)

    print(
        "Rank | Cell       | Risk       | "
        "Score      | Human Prob. | Surprise"
    )

    print("-" * 100)

    for rank, (
        cell,
        risk,
        score,
        probability,
    ) in enumerate(
        distribution[:20],
        start=1,
    ):

        surprise = (
            behavior.behavioral_surprise(
                probability
            )
        )

        print(
            f"{rank:>4} | "
            f"{str(cell):<10} | "
            f"{risk * 100:>7.2f}% | "
            f"{score:>8.4f} | "
            f"{probability * 100:>9.2f}% | "
            f"{surprise:>7.3f} bits"
        )

    # ==============================================================
    # ENTROPY
    # ==============================================================

    entropy = (
        analysis["entropy"]
    )

    uniform_capacity = (
        analysis[
            "theoretical_uniform_capacity"
        ]
    )

    efficiency = (
        analysis[
            "behavioral_efficiency"
        ]
    )

    candidate_count = (
        analysis[
            "candidate_count"
        ]
    )

    print(
        "\nBehavioral capacity analysis:"
    )

    print("-" * 60)

    print(
        f"Usable candidates       : "
        f"{candidate_count}"
    )

    print(
        f"Uniform capacity        : "
        f"{uniform_capacity:.4f} bits"
    )

    print(
        f"Behavioral entropy      : "
        f"{entropy:.4f} bits"
    )

    print(
        f"Behavioral efficiency   : "
        f"{efficiency * 100:.2f}%"
    )

    print(
        "\nInterpretation:"
    )

    print(
        "Uniform capacity assumes every candidate "
        "is equally likely."
    )

    print(
        "Behavioral entropy measures how much "
        "uncertainty exists under our human model."
    )

    # ==============================================================
    # STEGO CANDIDATES
    # ==============================================================

    choices = (
        behavior.get_stego_choices(
            game,
            probabilities,
            last_move=opening_move,
            risk_tolerance=risk_tolerance,
            number_of_choices=8,
        )
    )

    print(
        "\nTop human-compatible steganographic choices:"
    )

    print("-" * 60)

    for index, cell in enumerate(
        choices
    ):

        risk = probabilities[
            cell
        ]

        matching = next(
            (
                item
                for item in distribution
                if item[0] == cell
            ),
            None,
        )

        if matching:

            probability = (
                matching[3]
            )

            print(
                f"Choice {index:>2}: "
                f"{cell} | "
                f"risk={risk * 100:.2f}% | "
                f"human_prob="
                f"{probability * 100:.2f}%"
            )

    # ==============================================================
    # RESEARCH INTERPRETATION
    # ==============================================================

    print(
        "\n" + "=" * 90
    )

    print(
        "NEXT RESEARCH STEP"
    )

    print(
        "=" * 90
    )

    print(
        """
The next encoder will use this probability distribution
instead of treating every move as equally human.

The long-term pipeline is:

    Human gameplay
          ↓
    Feature extraction
          ↓
    Learned move-probability model
          ↓
    Risk-constrained candidate set
          ↓
    Entropy / arithmetic coding
          ↓
    Minesweeper gameplay
          ↓
    Blind replay decoder
          ↓
    Steganalysis
"""
    )


if __name__ == "__main__":
    main()