from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple


CellPos = Tuple[int, int]


class HumanBehaviorModel:
    """
    Human gameplay behavior model.

    Version 1:
        Rule-based feature scoring + softmax probability model.

    Version 2 (future):
        The same feature interface can be backed by an ML model
        trained from real human gameplay.

    Current features:
        - safety
        - information value
        - locality
        - frontier preference

    Outputs:
        - human-likeness score
        - normalized probability
        - behavioral entropy
        - behavioral surprise
    """

    FEATURE_NAMES = [
        "safety",
        "information",
        "locality",
        "frontier",
    ]

    def __init__(
        self,
        risk_weight: float = 0.45,
        information_weight: float = 0.30,
        locality_weight: float = 0.15,
        frontier_weight: float = 0.10,
        temperature: float = 1.0,
    ):
        """
        temperature controls how concentrated the probability
        distribution is.

        Lower temperature:
            prefers high-scoring moves more strongly.

        Higher temperature:
            produces a flatter/more exploratory distribution.
        """

        if temperature <= 0:
            raise ValueError(
                "Temperature must be greater than zero."
            )

        self.temperature = temperature

        total = (
            risk_weight
            + information_weight
            + locality_weight
            + frontier_weight
        )

        if total <= 0:
            raise ValueError(
                "Behavior weights must sum to > 0."
            )

        self.weights = {
            "safety": (
                risk_weight / total
            ),
            "information": (
                information_weight / total
            ),
            "locality": (
                locality_weight / total
            ),
            "frontier": (
                frontier_weight / total
            ),
        }

        # Reserved for the future learned model.
        self.learned_model = None
        self.model_type = "heuristic"

    # ==============================================================
    # FEATURE EXTRACTION
    # ==============================================================

    def extract_features(
        self,
        game,
        move: CellPos,
        risk: float,
        last_move: Optional[CellPos] = None,
    ) -> Dict[str, float]:
        """
        Extract normalized behavioral features for a move.
        """

        return {
            "safety": max(
                0.0,
                min(
                    1.0,
                    1.0 - risk,
                ),
            ),
            "information": (
                self.information_value(
                    game,
                    move,
                )
            ),
            "locality": (
                self.locality_score(
                    game,
                    move,
                    last_move,
                )
            ),
            "frontier": (
                self.frontier_score(
                    game,
                    move,
                )
            ),
        }

    # ==============================================================
    # INFORMATION VALUE
    # ==============================================================

    def information_value(
        self,
        game,
        move: CellPos,
    ) -> float:

        row, col = move

        hidden_neighbors = 0
        revealed_neighbors = 0

        for nr, nc in game._neighbors(
            row,
            col,
        ):

            cell = game.board[
                nr
            ][
                nc
            ]

            if (
                not cell.revealed
                and not cell.flagged
            ):
                hidden_neighbors += 1

            if cell.revealed:
                revealed_neighbors += 1

        raw = (
            hidden_neighbors
            + 0.5 * revealed_neighbors
        )

        return min(
            raw / 12.0,
            1.0,
        )

    # ==============================================================
    # FRONTIER
    # ==============================================================

    def frontier_score(
        self,
        game,
        move: CellPos,
    ) -> float:

        row, col = move

        for nr, nc in game._neighbors(
            row,
            col,
        ):

            if game.board[
                nr
            ][
                nc
            ].revealed:

                return 1.0

        return 0.0

    # ==============================================================
    # LOCALITY
    # ==============================================================

    def locality_score(
        self,
        game,
        move: CellPos,
        last_move: Optional[CellPos],
    ) -> float:

        if last_move is None:
            return 0.5

        row, col = move

        last_row, last_col = (
            last_move
        )

        distance = (
            abs(row - last_row)
            + abs(col - last_col)
        )

        return 1.0 / (
            1.0 + distance
        )

    # ==============================================================
    # SCORE
    # ==============================================================

    def score_move(
        self,
        game,
        move: CellPos,
        risk: float,
        last_move: Optional[CellPos] = None,
    ) -> float:

        features = self.extract_features(
            game,
            move,
            risk,
            last_move,
        )

        score = sum(
            self.weights[name]
            * features[name]
            for name in self.FEATURE_NAMES
        )

        return score

    # ==============================================================
    # SOFTMAX
    # ==============================================================

    def _softmax(
        self,
        values: List[float],
    ) -> List[float]:
        """
        Numerically stable softmax.
        """

        if not values:
            return []

        scaled = [
            value / self.temperature
            for value in values
        ]

        maximum = max(
            scaled
        )

        exponentials = [
            math.exp(
                value - maximum
            )
            for value in scaled
        ]

        total = sum(
            exponentials
        )

        if total <= 0:
            return [
                1.0 / len(values)
                for _ in values
            ]

        return [
            value / total
            for value in exponentials
        ]

    # ==============================================================
    # PROBABILITY DISTRIBUTION
    # ==============================================================

    def probability_distribution(
        self,
        game,
        probabilities: Dict[
            CellPos,
            float,
        ],
        last_move: Optional[CellPos] = None,
    ) -> List[
        Tuple[
            CellPos,
            float,
            float,
            float,
        ]
    ]:
        """
        Return:

            (
                cell,
                mine_risk,
                human_score,
                human_probability
            )

        sorted by descending behavioral probability.
        """

        if not probabilities:
            return []

        scored = []

        for cell, risk in probabilities.items():

            score = self.score_move(
                game,
                cell,
                risk,
                last_move,
            )

            scored.append(
                (
                    cell,
                    risk,
                    score,
                )
            )

        scores = [
            item[2]
            for item in scored
        ]

        softmax_probs = (
            self._softmax(
                scores
            )
        )

        result = []

        for item, probability in zip(
            scored,
            softmax_probs,
        ):

            cell, risk, score = item

            result.append(
                (
                    cell,
                    risk,
                    score,
                    probability,
                )
            )

        result.sort(
            key=lambda item: (
                -item[3],
                item[1],
                item[0],
            )
        )

        return result

    # ==============================================================
    # BACKWARD-COMPATIBLE RANKING
    # ==============================================================

    def rank_moves(
        self,
        game,
        probabilities: Dict[
            CellPos,
            float,
        ],
        last_move: Optional[CellPos] = None,
        risk_tolerance: float = 0.05,
    ) -> List[
        Tuple[
            CellPos,
            float,
            float,
        ]
    ]:
        """
        Existing interface preserved for encoder.py.

        Returns:

            (cell, mine_risk, human_score)
        """

        if not probabilities:
            return []

        minimum_risk = min(
            probabilities.values()
        )

        eligible = [
            cell
            for cell, risk in probabilities.items()
            if risk <= (
                minimum_risk
                + risk_tolerance
            )
        ]

        if len(eligible) < 2:

            eligible = [
                cell
                for cell, _ in sorted(
                    probabilities.items(),
                    key=lambda item: (
                        item[1],
                        item[0],
                    ),
                )[:2]
            ]

        restricted = {
            cell: probabilities[cell]
            for cell in eligible
        }

        distribution = (
            self.probability_distribution(
                game,
                restricted,
                last_move,
            )
        )

        return [
            (
                cell,
                risk,
                score,
            )
            for (
                cell,
                risk,
                score,
                _,
            ) in distribution
        ]

    # ==============================================================
    # BEHAVIORAL ENTROPY
    # ==============================================================

    def behavioral_entropy(
        self,
        distribution: List[
            Tuple[
                CellPos,
                float,
                float,
                float,
            ]
        ],
    ) -> float:
        """
        Shannon entropy in bits.

            H = -sum(p log2 p)
        """

        entropy = 0.0

        for (
            _,
            _,
            _,
            probability,
        ) in distribution:

            if probability > 0:

                entropy -= (
                    probability
                    * math.log2(
                        probability
                    )
                )

        return entropy

    # ==============================================================
    # BEHAVIORAL SURPRISE
    # ==============================================================

    def behavioral_surprise(
        self,
        probability: float,
    ) -> float:
        """
        Information content of choosing a move:

            Surprise = -log2(p)
        """

        if probability <= 0:
            return float("inf")

        return -math.log2(
            probability
        )

    # ==============================================================
    # STEGO CANDIDATES
    # ==============================================================

    def get_stego_choices(
        self,
        game,
        probabilities: Dict[
            CellPos,
            float,
        ],
        last_move: Optional[CellPos] = None,
        risk_tolerance: float = 0.05,
        number_of_choices: int = 8,
    ) -> List[CellPos]:

        if not probabilities:
            return []

        minimum_risk = min(
            probabilities.values()
        )

        eligible = {
            cell: risk
            for cell, risk in probabilities.items()
            if risk <= (
                minimum_risk
                + risk_tolerance
            )
        }

        distribution = (
            self.probability_distribution(
                game,
                eligible,
                last_move,
            )
        )

        return [
            cell
            for (
                cell,
                _,
                _,
                _,
            ) in distribution[
                :number_of_choices
            ]
        ]

    # ==============================================================
    # FULL ANALYSIS
    # ==============================================================

    def analyze_moves(
        self,
        game,
        probabilities: Dict[
            CellPos,
            float,
        ],
        last_move: Optional[CellPos] = None,
        risk_tolerance: float = 0.05,
    ) -> Dict[str, object]:

        minimum_risk = (
            min(
                probabilities.values()
            )
            if probabilities
            else None
        )

        if minimum_risk is None:
            return {
                "distribution": [],
                "entropy": 0.0,
                "candidate_count": 0,
                "theoretical_uniform_capacity": 0.0,
            }

        eligible = {
            cell: risk
            for cell, risk in probabilities.items()
            if risk <= (
                minimum_risk
                + risk_tolerance
            )
        }

        distribution = (
            self.probability_distribution(
                game,
                eligible,
                last_move,
            )
        )

        entropy = (
            self.behavioral_entropy(
                distribution
            )
        )

        candidate_count = len(
            distribution
        )

        uniform_capacity = (
            math.log2(
                candidate_count
            )
            if candidate_count > 1
            else 0.0
        )

        return {
            "distribution": distribution,
            "entropy": entropy,
            "candidate_count": candidate_count,
            "theoretical_uniform_capacity": (
                uniform_capacity
            ),
            "behavioral_efficiency": (
                entropy / uniform_capacity
                if uniform_capacity > 0
                else 0.0
            ),
        }