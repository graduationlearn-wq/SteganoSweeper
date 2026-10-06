from __future__ import annotations

import csv
import os
from typing import List, Tuple, Dict

from minesweeper import Minesweeper
from solver import MinesweeperSolver
from behavior_model import HumanBehaviorModel


Move = Tuple[int, int]


class HumanGameplayCollector:
    """
    Collect real human Minesweeper decisions for ML training.

    Important:
        - No secret message is involved.
        - No steganographic encoding is performed.
        - The player simply plays Minesweeper.
        - Each candidate move is logged with observable features.
        - The chosen move receives selected=1.
        - All other candidate moves receive selected=0.

    This gives us supervised learning data for a future model:

        P(human chooses move | board state)
    """

    def __init__(
        self,
        rows: int = 10,
        cols: int = 10,
        mines: int = 20,
        seed: int = 42,
        risk_tolerance: float = 0.05,
        output_file: str = "human_gameplay.csv",
    ):

        self.rows = rows
        self.cols = cols
        self.mines = mines
        self.seed = seed
        self.risk_tolerance = risk_tolerance
        self.output_file = output_file

        self.game_counter = 0

        self.fieldnames = [
            "game_id",
            "step",
            "candidate_row",
            "candidate_col",
            "mine_risk",
            "information_value",
            "locality",
            "frontier_score",
            "adjacent_revealed",
            "hidden_neighbors",
            "distance_from_last_move",
            "selected",
        ]

        self._create_file_if_needed()

    # ==============================================================
    # FILE SETUP
    # ==============================================================

    def _create_file_if_needed(self):

        if os.path.exists(self.output_file):
            return

        with open(
            self.output_file,
            "w",
            newline="",
            encoding="utf-8",
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=self.fieldnames,
            )

            writer.writeheader()

    # ==============================================================
    # FEATURE EXTRACTION
    # ==============================================================

    @staticmethod
    def extract_features(
        game: Minesweeper,
        move: Move,
        risk: float,
        last_move: Move,
    ) -> Dict[str, float]:

        row, col = move

        neighbors = list(
            game._neighbors(
                row,
                col,
            )
        )

        adjacent_revealed = 0
        hidden_neighbors = 0

        for nr, nc in neighbors:

            cell = game.board[nr][nc]

            if cell.revealed:
                adjacent_revealed += 1

            elif not cell.flagged:
                hidden_neighbors += 1

        information_value = min(
            (
                hidden_neighbors
                + 0.5 * adjacent_revealed
            ) / 12.0,
            1.0,
        )

        frontier_score = (
            1.0
            if adjacent_revealed > 0
            else 0.0
        )

        distance = (
            abs(row - last_move[0])
            + abs(col - last_move[1])
        )

        locality = (
            1.0 / (1.0 + distance)
        )

        return {
            "mine_risk": float(risk),
            "information_value": float(
                information_value
            ),
            "locality": float(
                locality
            ),
            "frontier_score": float(
                frontier_score
            ),
            "adjacent_revealed": int(
                adjacent_revealed
            ),
            "hidden_neighbors": int(
                hidden_neighbors
            ),
            "distance_from_last_move": int(
                distance
            ),
        }

    # ==============================================================
    # CANDIDATE GENERATION
    # ==============================================================

    def get_candidates(
        self,
        game: Minesweeper,
        solver: MinesweeperSolver,
    ) -> Dict[Move, float]:
        """
        Build the candidate set presented to the human.

        Priority:
            1. Guaranteed-safe cells.
            2. Low-risk cells when necessary.
        """

        solver.flag_guaranteed_mines()

        safe = solver.get_candidate_moves()

        # If there are at least two guaranteed-safe candidates,
        # use those.
        if len(safe) >= 2:

            return {
                cell: 0.0
                for cell in safe
            }

        # Otherwise use probability estimates.
        probabilities = (
            solver.get_move_risks()
        )

        if not probabilities:
            return {}

        minimum_risk = min(
            probabilities.values()
        )

        candidates = {
            cell: risk
            for cell, risk
            in probabilities.items()
            if risk <= (
                minimum_risk
                + self.risk_tolerance
            )
        }

        return candidates

    # ==============================================================
    # BOARD DISPLAY
    # ==============================================================

    @staticmethod
    def display_candidate_list(
        candidates: Dict[Move, float],
    ):

        ranked = sorted(
            candidates.items(),
            key=lambda item: (
                item[1],
                item[0],
            ),
        )

        print(
            "\nCandidate moves:"
        )

        print("-" * 55)

        print(
            "Index | Cell       | Estimated risk"
        )

        print("-" * 55)

        for index, (
            move,
            risk,
        ) in enumerate(
            ranked
        ):

            print(
                f"{index:>5} | "
                f"{str(move):<10} | "
                f"{risk * 100:>7.2f}%"
            )

        print("-" * 55)

        return ranked

    # ==============================================================
    # LOG MOVE FEATURES
    # ==============================================================

    def log_decision(
        self,
        game_id: str,
        step: int,
        candidates: Dict[Move, float],
        selected_move: Move,
        last_move: Move,
    ):

        rows = []

        for move, risk in candidates.items():

            features = self.extract_features(
                #game,
                move,
                risk,
                last_move,
            )

            row = {
                "game_id": game_id,
                "step": step,
                "candidate_row": move[0],
                "candidate_col": move[1],
                "mine_risk": features[
                    "mine_risk"
                ],
                "information_value": features[
                    "information_value"
                ],
                "locality": features[
                    "locality"
                ],
                "frontier_score": features[
                    "frontier_score"
                ],
                "adjacent_revealed": features[
                    "adjacent_revealed"
                ],
                "hidden_neighbors": features[
                    "hidden_neighbors"
                ],
                "distance_from_last_move": features[
                    "distance_from_last_move"
                ],
                "selected": int(
                    move == selected_move
                ),
            }

            rows.append(row)

        with open(
            self.output_file,
            "a",
            newline="",
            encoding="utf-8",
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=self.fieldnames,
            )

            writer.writerows(rows)

    # ==============================================================
    # COLLECT ONE GAME
    # ==============================================================

    def collect_game(
        self,
        opening_move: Move = None,
    ) -> bool:

        self.game_counter += 1

        game_id = (
            f"game_{self.game_counter:04d}"
        )

        if opening_move is None:

            opening_move = (
                self.rows // 2,
                self.cols // 2,
            )

        game = Minesweeper(
            rows=self.rows,
            cols=self.cols,
            mines=self.mines,
            seed=self.seed
                + self.game_counter,
        )

        print(
            "\n" + "=" * 70
        )

        print(
            f"COLLECTING {game_id}"
        )

        print(
            "=" * 70
        )

        # ----------------------------------------------------------
        # Opening move
        # ----------------------------------------------------------

        print(
            f"\nOpening move: "
            f"{opening_move}"
        )

        game.reveal(
            opening_move[0],
            opening_move[1],
        )

        last_move = opening_move

        step = 0

        # ----------------------------------------------------------
        # Gameplay loop
        # ----------------------------------------------------------

        while not game.game_over:

            print(
                "\nCurrent board:"
            )

            game.display()

            solver = MinesweeperSolver(
                game,
                max_component_cells=20,
            )

            candidates = (
                self.get_candidates(
                    game,
                    solver,
                )
            )

            if not candidates:

                print(
                    "\nNo candidate choices "
                    "available."
                )

                print(
                    "This state will not be logged."
                )

                break

            ranked = (
                self.display_candidate_list(
                    candidates
                )
            )

            print(
                "\nEnter the INDEX of the move "
                "you would naturally choose."
            )

            print(
                "Enter 'q' to stop this game."
            )

            while True:

                user_input = input(
                    "Your choice: "
                ).strip()

                if user_input.lower() == "q":

                    return False

                try:

                    index = int(
                        user_input
                    )

                    if not (
                        0 <= index < len(
                            ranked
                        )
                    ):

                        print(
                            "Invalid index."
                        )

                        continue

                    break

                except ValueError:

                    print(
                        "Enter a valid number."
                    )

            selected_move = ranked[
                index
            ][0]

            # ------------------------------------------------------
            # Log decision
            # ------------------------------------------------------

            step += 1

            # NOTE:
            # `game` is intentionally used here only for
            # observable board features.
            #
            # This log does not include hidden mine information.
            #
            with open(
                self.output_file,
                "a",
                newline="",
                encoding="utf-8",
            ) as file:

                writer = csv.DictWriter(
                    file,
                    fieldnames=self.fieldnames,
                )

                for move, risk in candidates.items():

                    features = self.extract_features(
                        game,
                        move,
                        risk,
                        last_move,
                    )

                    writer.writerow(
                        {
                            "game_id": game_id,
                            "step": step,
                            "candidate_row": move[0],
                            "candidate_col": move[1],
                            "mine_risk": features[
                                "mine_risk"
                            ],
                            "information_value": features[
                                "information_value"
                            ],
                            "locality": features[
                                "locality"
                            ],
                            "frontier_score": features[
                                "frontier_score"
                            ],
                            "adjacent_revealed": features[
                                "adjacent_revealed"
                            ],
                            "hidden_neighbors": features[
                                "hidden_neighbors"
                            ],
                            "distance_from_last_move": features[
                                "distance_from_last_move"
                            ],
                            "selected": int(
                                move == selected_move
                            ),
                        }
                    )

            # ------------------------------------------------------
            # Make the actual human-selected move.
            # ------------------------------------------------------

            safe = game.reveal(
                selected_move[0],
                selected_move[1],
            )

            last_move = selected_move

            if not safe:

                print(
                    "\nYou hit a mine."
                )

                print(
                    "Game over."
                )

                game.display(
                    reveal_mines=True
                )

                return True

        # ----------------------------------------------------------
        # Result
        # ----------------------------------------------------------

        print(
            "\nFinal board:"
        )

        game.display()

        if game.won:

            print(
                "\nGAME WON"
            )

        else:

            print(
                "\nGAME OVER"
            )

        return True


def main():

    collector = HumanGameplayCollector(
        rows=10,
        cols=10,
        mines=20,
        seed=42,
        risk_tolerance=0.05,
        output_file="human_gameplay.csv",
    )

    print(
        "=" * 70
    )

    print(
        "MINESWEEPER HUMAN DATA COLLECTOR"
    )

    print(
        "=" * 70
    )

    print(
        "\nThis mode is NOT steganography."
    )

    print(
        "Play normally and choose the move "
        "you would naturally make."
    )

    print(
        "\nThe program records candidate features "
        "and your selected move."
    )

    print(
        "\nStart a game? "
        "(y/n)"
    )

    answer = input(
        "> "
    ).strip().lower()

    if answer != "y":

        print(
            "Collection cancelled."
        )

        return

    collector.collect_game()

    print(
        "\nData saved to:"
    )

    print(
        collector.output_file
    )


if __name__ == "__main__":
    main()