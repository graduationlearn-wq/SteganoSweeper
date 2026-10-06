from __future__ import annotations

import math
from typing import List, Tuple, Optional

from minesweeper import Minesweeper
from solver import MinesweeperSolver
from behavior_model import HumanBehaviorModel


Move = Tuple[int, int]


class StegoEncoder:
    """
    Entropy-efficient adaptive Minesweeper steganography.

    Instead of restricting the number of usable choices to powers
    of two, this encoder treats the candidate set as a variable-radix
    alphabet.

    Examples:

        2 choices  -> radix 2  -> 1.000 bits of capacity
        4 choices  -> radix 4  -> 2.000 bits
        8 choices  -> radix 8  -> 3.000 bits
        14 choices -> radix 14 -> 3.807 bits
        20 choices -> radix 20 -> 4.322 bits

    The complete message is converted to one large integer.

    Each gameplay decision extracts one digit using:

        digit = value % radix
        value = value // radix

    Therefore the total representable space is:

        radix_1 * radix_2 * ... * radix_n

    and the theoretical capacity is:

        sum(log2(radix_i))

    bits.

    A 1-bit sentinel plus a 32-bit UTF-8 payload-length field are
    included before the payload so that the receiver can recover
    leading zeroes and determine the message length.
    """

    def __init__(
        self,
        game: Minesweeper,
        initial_move: Optional[Move] = None,
        risk_tolerance: float = 0.05,
        allow_risky_moves: bool = False,
        max_choices_per_move: int = 32,
    ):
        self.game = game

        self.solver = MinesweeperSolver(
            game,
            max_component_cells=20,
        )

        self.behavior = HumanBehaviorModel()

        self.last_move = initial_move

        self.risk_tolerance = risk_tolerance

        self.allow_risky_moves = (
            allow_risky_moves
        )

        self.max_choices_per_move = (
            max_choices_per_move
        )

        if self.max_choices_per_move < 2:
            raise ValueError(
                "max_choices_per_move must be at least 2."
            )

        self.move_log: List[dict] = []

    # ==============================================================
    # MESSAGE PACKING
    # ==============================================================

    @staticmethod
    def message_to_integer(
        message: str,
    ) -> Tuple[int, int, int]:
        """
        Convert message to a positive integer.

        Protocol:

            [1-bit sentinel][32-bit byte length][payload]

        Returns:

            encoded_integer
            total_protocol_bits
            payload_bytes
        """

        if not isinstance(message, str):
            raise TypeError(
                "Message must be a string."
            )

        data = message.encode(
            "utf-8"
        )

        payload_length = len(data)

        if payload_length > 0xFFFFFFFF:
            raise ValueError(
                "Message is too large for a 32-bit length header."
            )

        length_bits = format(
            payload_length,
            "032b",
        )

        payload_bits = "".join(
            f"{byte:08b}"
            for byte in data
        )

        # The leading 1 is a sentinel. It ensures that the
        # binary representation is never shortened by Python's
        # integer representation.
        protocol_bits = (
            "1"
            + length_bits
            + payload_bits
        )

        encoded_integer = int(
            protocol_bits,
            2,
        )

        return (
            encoded_integer,
            len(protocol_bits),
            payload_length,
        )

    # ==============================================================
    # SAFE HUMAN-RANKED CHOICES
    # ==============================================================

    def get_safe_choices(self) -> List[Move]:
        """
        Find guaranteed-safe moves and rank them according to
        the human-behavior model.
        """

        self.solver.flag_guaranteed_mines()

        candidates = (
            self.solver.get_candidate_moves()
        )

        if len(candidates) < 2:
            return candidates

        probabilities = {
            cell: 0.0
            for cell in candidates
        }

        ranked = self.behavior.rank_moves(
            self.game,
            probabilities,
            last_move=self.last_move,
            risk_tolerance=0.0,
        )

        return [
            cell
            for cell, _, _
            in ranked
        ]

    # ==============================================================
    # RISK-AWARE HUMAN-RANKED CHOICES
    # ==============================================================

    def get_risk_choices(self) -> List[Move]:
        """
        Obtain low-risk candidate moves and rank them with the
        human-behavior model.
        """

        probabilities = (
            self.solver.get_move_risks()
        )

        if not probabilities:
            return []

        ranked = self.behavior.rank_moves(
            self.game,
            probabilities,
            last_move=self.last_move,
            risk_tolerance=self.risk_tolerance,
        )

        return [
            cell
            for cell, _, _
            in ranked
        ]

    # ==============================================================
    # CURRENT CANDIDATE SET
    # ==============================================================

    def get_encoding_choices(
        self,
    ) -> Tuple[List[Move], str]:
        """
        Return candidate moves and the mode that produced them.
        """

        safe_choices = (
            self.get_safe_choices()
        )

        if len(safe_choices) >= 2:

            return (
                safe_choices[
                    :self.max_choices_per_move
                ],
                "GUARANTEED_SAFE",
            )

        # One safe move is forced gameplay.
        if len(safe_choices) == 1:

            return (
                safe_choices,
                "FORCED_SAFE",
            )

        # Optional risk-aware fallback.
        if self.allow_risky_moves:

            risk_choices = (
                self.get_risk_choices()
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
    # FORCED MOVE
    # ==============================================================

    def make_forced_move(
        self,
        move: Move,
    ):
        """
        Execute a move that carries no information.
        """

        row, col = move

        safe = self.game.reveal(
            row,
            col,
        )

        if not safe:
            raise RuntimeError(
                "The solver produced an unsafe forced move."
            )

        self.last_move = move

        self.move_log.append(
            {
                "step": len(self.move_log) + 1,
                "row": row,
                "col": col,
                "carrier": False,
                "mode": "FORCED_SAFE",
                "radix": 1,
                "digit": None,
                "capacity_bits": 0.0,
                "risk": 0.0,
                "result": "SAFE",
            }
        )

    # ==============================================================
    # ENCODE
    # ==============================================================

    def encode_message(
        self,
        message: str,
    ) -> List[dict]:
        """
        Encode the message using mixed-radix gameplay decisions.
        """

        (
            value,
            protocol_bits,
            payload_bytes,
        ) = self.message_to_integer(
            message
        )

        self.move_log = []

        initial_value = value

        while value > 0:

            if self.game.game_over:

                raise RuntimeError(
                    "Game ended before the complete "
                    "message could be encoded."
                )

            # ------------------------------------------------------
            # Find encoding choices.
            # ------------------------------------------------------

            while True:

                choices, mode = (
                    self.get_encoding_choices()
                )

                if len(choices) >= 2:
                    break

                if (
                    len(choices) == 1
                    and mode == "FORCED_SAFE"
                ):

                    self.make_forced_move(
                        choices[0]
                    )

                    continue

                raise RuntimeError(
                    "Unable to continue encoding.\n"
                    f"Remaining integer value: {value}\n"
                    f"Protocol size: {protocol_bits} bits\n"
                    f"Moves already used: "
                    f"{len(self.move_log)}\n"
                    f"Risk mode: "
                    f"{self.allow_risky_moves}"
                )

            # ------------------------------------------------------
            # Mixed-radix digit.
            # ------------------------------------------------------

            radix = len(choices)

            digit = value % radix

            value //= radix

            capacity_bits = math.log2(
                radix
            )

            selected_move = (
                choices[digit]
            )

            # ------------------------------------------------------
            # Risk.
            # ------------------------------------------------------

            if mode == "GUARANTEED_SAFE":

                risk = 0.0

            else:

                probabilities = (
                    self.solver.get_move_risks()
                )

                risk = probabilities.get(
                    selected_move,
                    1.0,
                )

            # ------------------------------------------------------
            # Execute move.
            # ------------------------------------------------------

            row, col = selected_move

            safe = self.game.reveal(
                row,
                col,
            )

            if not safe:

                self.move_log.append(
                    {
                        "step": len(
                            self.move_log
                        ) + 1,
                        "row": row,
                        "col": col,
                        "carrier": True,
                        "mode": mode,
                        "radix": radix,
                        "digit": digit,
                        "capacity_bits": capacity_bits,
                        "risk": risk,
                        "result": "MINE_HIT",
                    }
                )

                raise RuntimeError(
                    "A probabilistic encoding move "
                    "hit a mine.\n"
                    f"Move: {selected_move}\n"
                    f"Risk estimate: "
                    f"{risk * 100:.2f}%"
                )

            # ------------------------------------------------------
            # Log.
            # ------------------------------------------------------

            self.move_log.append(
                {
                    "step": len(
                        self.move_log
                    ) + 1,
                    "row": row,
                    "col": col,
                    "carrier": True,
                    "mode": mode,
                    "radix": radix,
                    "digit": digit,
                    "capacity_bits": capacity_bits,
                    "risk": risk,
                    "result": "SAFE",
                }
            )

            self.last_move = selected_move

        # Safety check.
        if value != 0:
            raise RuntimeError(
                "Internal mixed-radix encoding error."
            )

        return self.move_log

    # ==============================================================
    # CAPACITY
    # ==============================================================

    def calculate_theoretical_capacity(
        self,
    ) -> float:
        """
        Sum log2(radix) over carrier moves.
        """

        return sum(
            entry["capacity_bits"]
            for entry in self.move_log
            if entry["carrier"]
        )

    # ==============================================================
    # LOG
    # ==============================================================

    def print_move_log(self):

        print(
            "\nMixed-Radix Steganographic Move Log"
        )

        print("-" * 115)

        for entry in self.move_log:

            if entry["carrier"]:

                print(
                    f"Step {entry['step']:>2} | "
                    f"Move=({entry['row']}, "
                    f"{entry['col']}) | "
                    f"{entry['mode']:<16} | "
                    f"Radix={entry['radix']:>2} | "
                    f"Digit={entry['digit']:>2} | "
                    f"Capacity="
                    f"{entry['capacity_bits']:.3f} bits | "
                    f"Risk="
                    f"{entry['risk'] * 100:>6.2f}%"
                )

            else:

                print(
                    f"Step {entry['step']:>2} | "
                    f"Move=({entry['row']}, "
                    f"{entry['col']}) | "
                    f"FORCED_SAFE"
                )

        print("-" * 115)

    # ==============================================================
    # STATISTICS
    # ==============================================================

    def get_statistics(
        self,
        protocol_bits: Optional[int] = None,
    ) -> dict:

        carrier_moves = [
            entry
            for entry in self.move_log
            if entry["carrier"]
        ]

        forced_moves = [
            entry
            for entry in self.move_log
            if not entry["carrier"]
        ]

        total_moves = len(
            self.move_log
        )

        theoretical_capacity = (
            self.calculate_theoretical_capacity()
        )

        average_radix = (
            sum(
                entry["radix"]
                for entry in carrier_moves
            )
            / len(carrier_moves)
            if carrier_moves
            else 0.0
        )

        average_risk = (
            sum(
                entry["risk"]
                for entry in carrier_moves
            )
            / len(carrier_moves)
            if carrier_moves
            else 0.0
        )

        return {
            "total_moves": total_moves,
            "carrier_moves": len(
                carrier_moves
            ),
            "forced_moves": len(
                forced_moves
            ),
            "protocol_bits": (
                protocol_bits
                if protocol_bits is not None
                else 0
            ),
            "theoretical_capacity_bits": (
                theoretical_capacity
            ),
            "capacity_margin_bits": (
                theoretical_capacity
                - protocol_bits
                if protocol_bits is not None
                else 0.0
            ),
            "average_radix": average_radix,
            "average_capacity_per_carrier_move": (
                theoretical_capacity
                / len(carrier_moves)
                if carrier_moves
                else 0.0
            ),
            "bits_per_total_move": (
                protocol_bits / total_moves
                if (
                    protocol_bits is not None
                    and total_moves
                )
                else 0.0
            ),
            "average_estimated_risk": average_risk,
            "risk_based_moves": sum(
                1
                for entry in carrier_moves
                if entry["mode"] == "RISK_BASED"
            ),
        }