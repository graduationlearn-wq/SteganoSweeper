from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

CellPos = Tuple[int, int]


class HumanBehaviorModel:
    """Human move-choice model with a learned conditional-logit option.

    If choice_model.json exists beside this file, candidate scores are produced
    by the fitted conditional-logit model. Otherwise the original hand-weighted
    heuristic remains available as a safe fallback.

    The public methods and return structures are kept compatible with the
    repository's encoder.py, decoder.py and main.py.
    """

    FEATURE_NAMES = ["safety", "information", "locality", "frontier"]

    def __init__(
        self,
        risk_weight: float = 0.45,
        information_weight: float = 0.30,
        locality_weight: float = 0.15,
        frontier_weight: float = 0.10,
        temperature: float = 1.0,
        model_path: Optional[str] = None,
    ):
        if temperature <= 0:
            raise ValueError("Temperature must be greater than zero.")
        self.temperature = float(temperature)

        total = risk_weight + information_weight + locality_weight + frontier_weight
        if total <= 0:
            raise ValueError("Behavior weights must sum to > 0.")
        self.weights = {
            "safety": risk_weight / total,
            "information": information_weight / total,
            "locality": locality_weight / total,
            "frontier": frontier_weight / total,
        }

        self.learned_model = None
        self.model_type = "heuristic"
        self.model_load_error = None

        target = Path(model_path) if model_path else Path(__file__).resolve().with_name("choice_model.json")
        if target.exists():
            try:
                payload = json.loads(target.read_text(encoding="utf-8"))
                names = payload.get("feature_names")
                means = payload.get("means")
                scales = payload.get("scales")
                coefficients = payload.get("coefficients")
                if names != self.FEATURE_NAMES:
                    raise ValueError("The saved model feature order does not match this runtime.")
                if not (len(means) == len(scales) == len(coefficients) == len(self.FEATURE_NAMES)):
                    raise ValueError("The saved model has an invalid parameter count.")
                if any(not math.isfinite(float(v)) for v in means + scales + coefficients):
                    raise ValueError("The saved model contains non-finite parameters.")
                if any(float(v) <= 0 for v in scales):
                    raise ValueError("The saved model contains an invalid feature scale.")
                self.learned_model = {
                    "means": [float(v) for v in means],
                    "scales": [float(v) for v in scales],
                    "coefficients": [float(v) for v in coefficients],
                    "training_decisions": int(payload.get("training_decisions", 0)),
                    "training_games": int(payload.get("training_games", 0)),
                    "validation": payload.get("validation", {}),
                }
                self.model_type = "conditional_logit"
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                self.model_load_error = str(exc)

    # ------------------------------------------------------------------
    # Runtime features. These transforms mirror train_behavior_model.py.
    # ------------------------------------------------------------------
    def extract_features(
        self,
        game,
        move: CellPos,
        risk: float,
        last_move: Optional[CellPos] = None,
    ) -> Dict[str, float]:
        return {
            "safety": max(0.0, min(1.0, 1.0 - float(risk))),
            "information": self.information_value(game, move),
            "locality": self.locality_score(game, move, last_move),
            "frontier": self.frontier_score(game, move),
        }

    def information_value(self, game, move: CellPos) -> float:
        row, col = move
        neighbors = list(game._neighbors(row, col))
        if not neighbors:
            return 0.0
        adjacent_numbered = 0
        hidden_neighbors = 0
        for nr, nc in neighbors:
            cell = game.board[nr][nc]
            if cell.revealed and getattr(cell, "adjacent_mines", 0) > 0:
                adjacent_numbered += 1
            if not cell.revealed and not cell.flagged:
                hidden_neighbors += 1
        # Same interpretable information proxy used by the v3 gameplay logger.
        return 0.5 * (adjacent_numbered / 8.0) + 0.5 * (hidden_neighbors / 8.0)

    def frontier_score(self, game, move: CellPos) -> float:
        row, col = move
        neighbors = list(game._neighbors(row, col))
        if not neighbors:
            return 0.0
        adjacent_numbered = sum(
            1
            for nr, nc in neighbors
            if game.board[nr][nc].revealed
            and getattr(game.board[nr][nc], "adjacent_mines", 0) > 0
        )
        return adjacent_numbered / max(1, len(neighbors))

    def locality_score(
        self,
        game,
        move: CellPos,
        last_move: Optional[CellPos],
    ) -> float:
        if last_move is None:
            return 1.0
        row, col = move
        last_row, last_col = last_move
        distance = math.sqrt((row - last_row) ** 2 + (col - last_col) ** 2)
        return 1.0 / (1.0 + distance)

    # ------------------------------------------------------------------
    # Scoring and probabilities
    # ------------------------------------------------------------------
    def score_move(
        self,
        game,
        move: CellPos,
        risk: float,
        last_move: Optional[CellPos] = None,
    ) -> float:
        features = self.extract_features(game, move, risk, last_move)

        if self.learned_model is not None:
            means = self.learned_model["means"]
            scales = self.learned_model["scales"]
            coefficients = self.learned_model["coefficients"]
            return sum(
                coefficients[i] * ((features[name] - means[i]) / scales[i])
                for i, name in enumerate(self.FEATURE_NAMES)
            )

        return sum(self.weights[name] * features[name] for name in self.FEATURE_NAMES)

    def _softmax(self, values: List[float]) -> List[float]:
        if not values:
            return []
        scaled = [value / self.temperature for value in values]
        maximum = max(scaled)
        exponentials = [math.exp(value - maximum) for value in scaled]
        total = sum(exponentials)
        if total <= 0 or not math.isfinite(total):
            return [1.0 / len(values) for _ in values]
        return [value / total for value in exponentials]

    def probability_distribution(
        self,
        game,
        probabilities: Dict[CellPos, float],
        last_move: Optional[CellPos] = None,
    ) -> List[Tuple[CellPos, float, float, float]]:
        if not probabilities:
            return []
        scored = []
        for cell, risk in probabilities.items():
            score = self.score_move(game, cell, risk, last_move)
            scored.append((cell, risk, score))
        softmax_probs = self._softmax([item[2] for item in scored])
        result = [
            (cell, risk, score, probability)
            for (cell, risk, score), probability in zip(scored, softmax_probs)
        ]
        result.sort(key=lambda item: (-item[3], item[1], item[0]))
        return result

    def rank_moves(
        self,
        game,
        probabilities: Dict[CellPos, float],
        last_move: Optional[CellPos] = None,
        risk_tolerance: float = 0.05,
    ) -> List[Tuple[CellPos, float, float]]:
        if not probabilities:
            return []
        minimum_risk = min(probabilities.values())
        eligible = [
            cell for cell, risk in probabilities.items()
            if risk <= minimum_risk + risk_tolerance
        ]
        if len(eligible) < 2:
            eligible = [
                cell for cell, _ in sorted(
                    probabilities.items(), key=lambda item: (item[1], item[0])
                )[:2]
            ]
        restricted = {cell: probabilities[cell] for cell in eligible}
        distribution = self.probability_distribution(game, restricted, last_move)
        return [(cell, risk, score) for cell, risk, score, _ in distribution]

    def behavioral_entropy(self, distribution) -> float:
        entropy = 0.0
        for _, _, _, probability in distribution:
            if probability > 0:
                entropy -= probability * math.log2(probability)
        return entropy

    def behavioral_surprise(self, probability: float) -> float:
        if probability <= 0:
            return float("inf")
        return -math.log2(probability)

    def get_stego_choices(
        self,
        game,
        probabilities: Dict[CellPos, float],
        last_move: Optional[CellPos] = None,
        risk_tolerance: float = 0.05,
        number_of_choices: int = 8,
    ) -> List[CellPos]:
        if not probabilities:
            return []
        minimum_risk = min(probabilities.values())
        eligible = {
            cell: risk for cell, risk in probabilities.items()
            if risk <= minimum_risk + risk_tolerance
        }
        distribution = self.probability_distribution(game, eligible, last_move)
        return [item[0] for item in distribution[:number_of_choices]]

    def analyze_moves(
        self,
        game,
        probabilities: Dict[CellPos, float],
        last_move: Optional[CellPos] = None,
        risk_tolerance: float = 0.05,
    ) -> Dict[str, object]:
        if not probabilities:
            return {
                "distribution": [],
                "entropy": 0.0,
                "candidate_count": 0,
                "theoretical_uniform_capacity": 0.0,
                "behavioral_efficiency": 0.0,
            }
        minimum_risk = min(probabilities.values())
        eligible = {
            cell: risk for cell, risk in probabilities.items()
            if risk <= minimum_risk + risk_tolerance
        }
        distribution = self.probability_distribution(game, eligible, last_move)
        entropy = self.behavioral_entropy(distribution)
        candidate_count = len(distribution)
        uniform_capacity = math.log2(candidate_count) if candidate_count > 1 else 0.0
        return {
            "distribution": distribution,
            "entropy": entropy,
            "candidate_count": candidate_count,
            "theoretical_uniform_capacity": uniform_capacity,
            "behavioral_efficiency": entropy / uniform_capacity if uniform_capacity > 0 else 0.0,
        }
