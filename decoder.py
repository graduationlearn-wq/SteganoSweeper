from __future__ import annotations

from typing import Dict, List, Tuple, Optional

from minesweeper import Minesweeper
from solver import MinesweeperSolver
from behavior_model import HumanBehaviorModel


Move = Tuple[int, int]


class StegoDecoder:
    """
    Blind mixed-radix Minesweeper decoder.

    The receiver receives only:

        - game configuration
        - seed
        - opening move
        - gameplay coordinates

    It reconstructs the candidate set at every step.

    For each carrier move:

        digit = position of selected move
        radix = number of usable candidates

    The decoder reconstructs the encoded integer using:

        value += digit * multiplier
        multiplier *= radix

    Finally the integer is converted back to:

        [sentinel][32-bit length][payload]
    """

    def __init__(
        self,
        rows: int = 10,
        cols: int = 10,
        mines: int = 20,
        seed: int = 42,
        risk_tolerance: float = 0.05,
        allow_risky_moves: bool = False,
        max_choices_per_move: int = 32,
    ):

        self.rows = rows
        self.cols = cols
        self.mines = mines
        self.seed = seed

        self.risk_tolerance = (
            risk_tolerance
        )

        self.allow_risky_moves = (
            allow_risky_moves
        )

        self.max_choices_per_move = (
            max_choices_per_move
        )

        self.behavior = (
            HumanBehaviorModel()
        )

    # ==============================================================
    # CREATE GAME
    # ==============================================================

    def _create_game(
        self,
        opening_move: Move,
    ) -> Minesweeper:

        game = Minesweeper(
            rows=self.rows,
            cols=self.cols,
            mines=self.mines,
            seed=self.seed,
        )

        row, col = opening_move

        safe = game.reveal(
            row,
            col,
        )

        if not safe:
            raise RuntimeError(
                "Opening move was unsafe."
            )

        return game

    # ==============================================================
    # SAFE CHOICES
    # ==============================================================

    def get_safe_choices(
        self,
        game: Minesweeper,
        solver: MinesweeperSolver,
        last_move: Optional[Move],
    ) -> List[Move]:

        solver.flag_guaranteed_mines()

        candidates = (
            solver.get_candidate_moves()
        )

        if len(candidates) < 2:
            return candidates

        probabilities = {
            cell: 0.0
            for cell in candidates
        }

        ranked = self.behavior.rank_moves(
            game,
            probabilities,
            last_move=last_move,
            risk_tolerance=0.0,
        )

        return [
            cell
            for cell, _, _
            in ranked
        ]

    # ==============================================================
    # RISK CHOICES
    # ==============================================================

    def get_risk_choices(
        self,
        game: Minesweeper,
        solver: MinesweeperSolver,
        last_move: Optional[Move],
    ) -> List[Move]:

        probabilities = (
            solver.get_move_risks()
        )

        if not probabilities:
            return []

        ranked = self.behavior.rank_moves(
            game,
            probabilities,
            last_move=last_move,
            risk_tolerance=self.risk_tolerance,
        )

        return [
            cell
            for cell, _, _
            in ranked
        ]

    # ==============================================================
    # ENCODING CHOICES
    # ==============================================================

    def get_encoding_choices(
        self,
        game: Minesweeper,
        solver: MinesweeperSolver,
        last_move: Optional[Move],
    ) -> Tuple[List[Move], str]:

        safe_choices = (
            self.get_safe_choices(
                game,
                solver,
                last_move,
            )
        )

        if len(safe_choices) >= 2:

            return (
                safe_choices[
                    :self.max_choices_per_move
                ],
                "GUARANTEED_SAFE",
            )

        if len(safe_choices) == 1:

            return (
                safe_choices,
                "FORCED_SAFE",
            )

        if self.allow_risky_moves:

            risk_choices = (
                self.get_risk_choices(
                    game,
                    solver,
                    last_move,
                )
            )

            if len(risk_choices) >= 2:

                return (
                    risk_choices[
                        :self.max_choices_per_move
                    ],
                    "RISK_BASED",
                )

        return (
            [],
            "NO_CHOICE",
        )

    # ==============================================================
    # DECODE
    # ==============================================================

    def decode_replay(
        self,
        opening_move: Move,
        replay: List[Move],
        verbose: bool = True,
    ) -> Dict[str, object]:

        game = self._create_game(
            opening_move
        )

        solver = MinesweeperSolver(
            game,
            max_component_cells=20,
        )

        last_move = opening_move

        # Reconstruct the mixed-radix integer.
        recovered_integer = 0

        multiplier = 1

        decoded_moves = []

        for step_number, move in enumerate(
            replay,
            start=1,
        ):

            if game.game_over:

                raise RuntimeError(
                    f"Game ended before replay "
                    f"step {step_number}."
                )

            choices, mode = (
                self.get_encoding_choices(
                    game,
                    solver,
                    last_move,
                )
            )

            # ------------------------------------------------------
            # Forced move.
            # ------------------------------------------------------

            if mode == "FORCED_SAFE":

                expected = choices[0]

                if move != expected:

                    raise RuntimeError(
                        f"Replay diverged at step "
                        f"{step_number}.\n"
                        f"Expected forced move: "
                        f"{expected}\n"
                        f"Received: {move}"
                    )

                digit = None
                radix = 1
                carrier = False

            # ------------------------------------------------------
            # Carrier move.
            # ------------------------------------------------------

            elif mode in (
                "GUARANTEED_SAFE",
                "RISK_BASED",
            ):

                if len(choices) < 2:

                    raise RuntimeError(
                        "Invalid carrier candidate set."
                    )

                radix = len(choices)

                if move not in choices:

                    raise RuntimeError(
                        f"Replay diverged at step "
                        f"{step_number}.\n"
                        f"Received move: {move}\n"
                        f"Valid choices: {choices}"
                    )

                digit = choices.index(
                    move
                )

                # Mixed-radix reconstruction.
                recovered_integer += (
                    digit * multiplier
                )

                multiplier *= radix

                carrier = True

            else:

                raise RuntimeError(
                    f"No usable encoding choices "
                    f"at replay step {step_number}."
                )

            # ------------------------------------------------------
            # Execute move.
            # ------------------------------------------------------

            row, col = move

            safe = game.reveal(
                row,
                col,
            )

            decoded_moves.append(
                {
                    "step": step_number,
                    "move": move,
                    "mode": mode,
                    "radix": radix,
                    "digit": digit,
                    "carrier": carrier,
                    "result": (
                        "SAFE"
                        if safe
                        else "MINE_HIT"
                    ),
                }
            )

            last_move = move

            if verbose:

                if carrier:

                    print(
                        f"Replay step "
                        f"{step_number:>2}: "
                        f"move={move} | "
                        f"mode={mode} | "
                        f"radix={radix} | "
                        f"digit={digit} | "
                        f"capacity="
                        f"{__import__('math').log2(radix):.3f} bits"
                    )

                else:

                    print(
                        f"Replay step "
                        f"{step_number:>2}: "
                        f"move={move} | "
                        f"FORCED"
                    )

            if not safe:

                raise RuntimeError(
                    f"Replay hit a mine at step "
                    f"{step_number}."
                )

        # ----------------------------------------------------------
        # Decode integer.
        # ----------------------------------------------------------

        if recovered_integer <= 0:

            raise RuntimeError(
                "No valid encoded integer was recovered."
            )

        binary = bin(
            recovered_integer
        )[2:]

        # The first bit must be our sentinel.
        if not binary.startswith("1"):

            raise RuntimeError(
                "Invalid protocol sentinel."
            )

        if len(binary) < 33:

            raise RuntimeError(
                "Insufficient data for protocol header."
            )

        # Remove sentinel.
        protocol_bits = binary[1:]

        # First 32 bits after sentinel = payload byte length.
        length_bits = protocol_bits[:32]

        payload_length = int(
            length_bits,
            2,
        )

        expected_total_bits = (
            32
            + payload_length * 8
        )

        if len(protocol_bits) < expected_total_bits:

            raise RuntimeError(
                "Recovered protocol is incomplete.\n"
                f"Expected at least "
                f"{expected_total_bits + 1} bits "
                f"including sentinel.\n"
                f"Recovered: "
                f"{len(protocol_bits) + 1} bits."
            )

        payload_bits = protocol_bits[
            32:
            32 + payload_length * 8
        ]

        message = self.bits_to_text(
            payload_bits
        )

        return {
            "message": message,
            "recovered_integer": recovered_integer,
            "protocol_bits": (
                "1" + protocol_bits
            ),
            "payload_bits": payload_bits,
            "payload_bytes": payload_length,
            "expected_payload_bits": (
                expected_total_bits
            ),
            "decoded_moves": decoded_moves,
            "total_replay_moves": len(
                replay
            ),
            "carrier_moves": sum(
                1
                for entry in decoded_moves
                if entry["carrier"]
            ),
            "forced_moves": sum(
                1
                for entry in decoded_moves
                if not entry["carrier"]
            ),
            "theoretical_capacity_bits": sum(
                __import__("math").log2(
                    entry["radix"]
                )
                for entry in decoded_moves
                if entry["carrier"]
            ),
        }

    # ==============================================================
    # BITS -> TEXT
    # ==============================================================

    @staticmethod
    def bits_to_text(
        bits: str,
    ) -> str:

        if not bits:
            return ""

        if len(bits) % 8 != 0:

            raise ValueError(
                "Payload bits are not byte aligned."
            )

        data = bytearray()

        for i in range(
            0,
            len(bits),
            8,
        ):

            data.append(
                int(
                    bits[i:i + 8],
                    2,
                )
            )

        return data.decode(
            "utf-8",
            errors="replace",
        )

    # ==============================================================
    # PUBLIC REPLAY
    # ==============================================================

    @staticmethod
    def sanitize_encoder_log(
        move_log: List[dict],
    ) -> List[Move]:

        return [
            (
                entry["row"],
                entry["col"],
            )
            for entry in move_log
        ]