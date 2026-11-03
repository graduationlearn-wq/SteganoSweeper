"""Train a conditional-logit human move-choice model from SteganoSweeper logs.

Expected input: human_decisions.csv produced by clickable_minesweeper_v3.py.
The selected move is modelled as a choice among the candidates in each row.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp

FEATURE_NAMES = ["safety", "information", "locality", "frontier"]


def as_float(value: Any, default: float = float("nan")) -> float:
    try:
        if value in (None, "", "null"):
            return default
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def candidate_vector(candidate: dict, fallback_risk: float) -> list[float]:
    risk = as_float(candidate.get("risk_estimate"), fallback_risk)
    information = as_float(candidate.get("information_proxy"), 0.5)
    distance = as_float(candidate.get("distance_from_last_action"), 0.0)
    frontier = as_float(candidate.get("frontier_score"), 0.0)

    risk = min(1.0, max(0.0, risk))
    information = min(1.0, max(0.0, information))
    frontier = min(1.0, max(0.0, frontier))
    locality = 1.0 / (1.0 + max(0.0, distance))
    return [1.0 - risk, information, locality, frontier]


def load_groups(path: Path):
    groups = []
    skipped = 0
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        required = {"session_id", "game_id", "selected_row", "selected_col", "candidates_json"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV is missing required columns: {sorted(missing)}")

        for row in reader:
            try:
                candidates = json.loads(row["candidates_json"])
                selected = (int(row["selected_row"]), int(row["selected_col"]))
                fallback_risk = as_float(row.get("selected_risk_estimate"), 0.25)
                if not isinstance(candidates, list) or len(candidates) < 2:
                    skipped += 1
                    continue

                seen = set()
                clean = []
                selected_index = None
                for c in candidates:
                    pos = (int(c["row"]), int(c["col"]))
                    if pos in seen:
                        continue
                    seen.add(pos)
                    if pos == selected:
                        selected_index = len(clean)
                    clean.append(candidate_vector(c, fallback_risk))

                if selected_index is None or len(clean) < 2:
                    skipped += 1
                    continue

                X = np.asarray(clean, dtype=float)
                groups.append({
                    "key": (row["session_id"], row["game_id"]),
                    "X": X,
                    "chosen": selected_index,
                })
            except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                skipped += 1
    if not groups:
        raise ValueError("No valid decision groups were found in the CSV.")
    return groups, skipped


def standardize(groups):
    all_x = np.vstack([g["X"] for g in groups])
    means = all_x.mean(axis=0)
    scales = all_x.std(axis=0)
    scales[scales < 1e-8] = 1.0
    transformed = [
        {**g, "Z": (g["X"] - means) / scales}
        for g in groups
    ]
    return transformed, means, scales


def fit_conditional_logit(groups, regularization=2.0):
    """Maximise conditional choice likelihood with L2 regularisation."""
    k = len(FEATURE_NAMES)

    def objective(beta):
        loss = 0.5 * regularization * float(beta @ beta)
        grad = regularization * beta.copy()
        for g in groups:
            z = g["Z"]
            scores = z @ beta
            probabilities = np.exp(scores - logsumexp(scores))
            loss += float(logsumexp(scores) - scores[g["chosen"]])
            grad += z.T @ probabilities - z[g["chosen"]]
        return loss, grad

    result = minimize(
        objective,
        np.zeros(k, dtype=float),
        method="L-BFGS-B",
        jac=True,
        options={"maxiter": 500, "ftol": 1e-10},
    )
    if not result.success and not np.isfinite(result.fun):
        raise RuntimeError(f"Model optimisation failed: {result.message}")
    return result.x, result


def evaluate(groups, beta):
    top1, top3, top5, nll, uniform_nll = [], [], [], [], []
    for g in groups:
        scores = g["Z"] @ beta
        order = np.argsort(-scores)
        chosen = g["chosen"]
        nll.append(float(logsumexp(scores) - scores[chosen]))
        uniform_nll.append(math.log(len(scores)))
        top1.append(int(order[0] == chosen))
        top3.append(int(chosen in order[:min(3, len(order))]))
        top5.append(int(chosen in order[:min(5, len(order))]))
    return {
        "decisions": len(groups),
        "top1_accuracy": float(np.mean(top1)),
        "top3_accuracy": float(np.mean(top3)),
        "top5_accuracy": float(np.mean(top5)),
        "mean_choice_nll": float(np.mean(nll)),
        "uniform_baseline_nll": float(np.mean(uniform_nll)),
    }


def main():
    parser = argparse.ArgumentParser(description="Train SteganoSweeper human-choice model")
    parser.add_argument("--input", default="human_decisions.csv")
    parser.add_argument("--output", default="choice_model.json")
    parser.add_argument("--regularization", type=float, default=2.0)
    parser.add_argument("--test-fraction", type=float, default=0.2)
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Cannot find {input_path}. Run from the project folder or pass --input.")
    if args.regularization < 0:
        raise ValueError("regularization must be non-negative")

    groups, skipped = load_groups(input_path)
    game_keys = sorted({g["key"] for g in groups})
    rng = random.Random(42)
    rng.shuffle(game_keys)
    n_test = max(1, min(len(game_keys) - 1, round(len(game_keys) * args.test_fraction)))
    test_keys = set(game_keys[:n_test])
    train_raw = [g for g in groups if g["key"] not in test_keys]
    test_raw = [g for g in groups if g["key"] in test_keys]

    # Evaluate a genuinely held-out game split.
    train_eval, eval_means, eval_scales = standardize(train_raw)
    test_eval = [{**g, "Z": (g["X"] - eval_means) / eval_scales} for g in test_raw]
    beta_eval, opt_eval = fit_conditional_logit(train_eval, args.regularization)
    metrics = evaluate(test_eval, beta_eval)

    # Refit the deployment model on all available pilot decisions.
    full_groups, means, scales = standardize(groups)
    beta, opt_full = fit_conditional_logit(full_groups, args.regularization)

    output = {
        "model_type": "conditional_logit",
        "version": 1,
        "feature_names": FEATURE_NAMES,
        "means": means.tolist(),
        "scales": scales.tolist(),
        "coefficients": beta.tolist(),
        "regularization": args.regularization,
        "training_decisions": len(groups),
        "training_games": len(game_keys),
        "skipped_rows": skipped,
        "validation": metrics,
        "note": "Pilot model from one player's gameplay; exploratory, not a population-level human model.",
    }
    output_path = Path(args.output)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    print("=" * 64)
    print("STEGANOSWEEPER HUMAN-CHOICE MODEL TRAINING")
    print("=" * 64)
    print(f"Valid decisions : {len(groups)}")
    print(f"Distinct games  : {len(game_keys)}")
    print(f"Skipped rows    : {skipped}")
    print(f"Train / test    : {len(train_raw)} / {len(test_raw)} decisions")
    print(f"Model type      : Conditional Logistic Choice Model")
    print(f"Optimisation    : {opt_full.message}")
    print("\nHeld-out game evaluation:")
    print(f"  Top-1 accuracy       : {metrics['top1_accuracy']:.3f}")
    print(f"  Top-3 accuracy       : {metrics['top3_accuracy']:.3f}")
    print(f"  Top-5 accuracy       : {metrics['top5_accuracy']:.3f}")
    print(f"  Mean choice NLL      : {metrics['mean_choice_nll']:.3f}")
    print(f"  Uniform baseline NLL : {metrics['uniform_baseline_nll']:.3f}")
    print("\nLearned coefficients (standardised features):")
    for name, value in zip(FEATURE_NAMES, beta):
        print(f"  {name:12s}: {value:+.4f}")
    print(f"\nSaved model: {output_path.resolve()}")
    print("The saved model is trained on all valid decisions after held-out evaluation.")


if __name__ == "__main__":
    main()
