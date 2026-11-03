"""Encode a short message into Minesweeper moves and blind-decode the replay."""
from __future__ import annotations

import argparse

from minesweeper import Minesweeper
from encoder import StegoEncoder
from decoder import StegoDecoder
from behavior_model import HumanBehaviorModel


def run_once(message: str, rows: int, cols: int, mines: int, seed: int,
             opening: tuple[int, int], risk_tolerance: float,
             allow_risky_moves: bool, max_choices: int):
    game = Minesweeper(rows=rows, cols=cols, mines=mines, seed=seed)
    if not game.reveal(*opening):
        raise RuntimeError("Opening move was unsafe; try another seed or opening cell.")

    encoder = StegoEncoder(
        game=game,
        initial_move=opening,
        risk_tolerance=risk_tolerance,
        allow_risky_moves=allow_risky_moves,
        max_choices_per_move=max_choices,
    )
    if encoder.behavior.model_type != "conditional_logit":
        raise RuntimeError(
            "The trained model was not loaded. Run `python train_behavior_model.py` first."
        )

    move_log = encoder.encode_message(message)
    replay = [(entry["row"], entry["col"]) for entry in move_log]

    decoder = StegoDecoder(
        rows=rows,
        cols=cols,
        mines=mines,
        seed=seed,
        risk_tolerance=risk_tolerance,
        allow_risky_moves=allow_risky_moves,
        max_choices_per_move=max_choices,
    )
    if decoder.behavior.model_type != "conditional_logit":
        raise RuntimeError("Decoder did not load the same trained behavior model.")

    result = decoder.decode_replay(opening, replay, verbose=False)
    if result["message"] != message:
        raise RuntimeError(f"Decoded text mismatch: {result['message']!r}")

    stats = encoder.get_statistics(protocol_bits=StegoEncoder.message_to_integer(message)[1])
    return move_log, stats, result


def main():
    parser = argparse.ArgumentParser(description="SteganoSweeper learned-model encode/decode demo")
    parser.add_argument("--message", default="HELLO", help="Text to hide (keep it short for the demo)")
    parser.add_argument("--rows", type=int, default=16)
    parser.add_argument("--cols", type=int, default=16)
    parser.add_argument("--mines", type=int, default=40)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--opening-row", type=int, default=7)
    parser.add_argument("--opening-col", type=int, default=7)
    parser.add_argument("--risk-tolerance", type=float, default=0.05)
    parser.add_argument("--allow-risky", action="store_true", help="Permit low-risk fallback moves when no guaranteed-safe choices remain")
    parser.add_argument("--max-choices", type=int, default=32)
    parser.add_argument("--try-seeds", type=int, default=1, help="Try this many consecutive seeds if capacity is insufficient")
    args = parser.parse_args()

    model = HumanBehaviorModel()
    if model.model_type != "conditional_logit":
        raise SystemExit("Trained model not found. Run `python train_behavior_model.py` first.")

    print("SteganoSweeper — learned behavior model")
    print(f"Model: conditional logit | training decisions: {model.learned_model['training_decisions']} | games: {model.learned_model['training_games']}")
    print(f"Message: {args.message!r}")
    print("Starting encode/decode test...\n")

    last_error = None
    for seed in range(args.seed, args.seed + max(1, args.try_seeds)):
        try:
            moves, stats, decoded = run_once(
                args.message, args.rows, args.cols, args.mines, seed,
                (args.opening_row, args.opening_col), args.risk_tolerance,
                args.allow_risky, args.max_choices,
            )
            print(f"Board: {args.rows}x{args.cols}, mines={args.mines}, seed={seed}, opening={(args.opening_row, args.opening_col)}")
            print(f"Encoded moves: {stats['total_moves']} (carrier={stats['carrier_moves']}, forced={stats['forced_moves']})")
            print(f"Protocol bits: {stats['protocol_bits']} | Theoretical capacity: {stats['theoretical_capacity_bits']:.2f} bits")
            print(f"Average estimated risk: {stats['average_estimated_risk'] * 100:.2f}%")
            print(f"Blind decode result: {decoded['message']!r}")
            print("MESSAGE RECOVERY: SUCCESS" if decoded["message"] == args.message else "MESSAGE RECOVERY: FAILED")
            print("\nPublic replay coordinates:")
            print(replay_string := " ".join(f"({e['row']},{e['col']})" for e in moves))
            return
        except Exception as exc:
            last_error = exc
            print(f"Seed {seed} did not fit the payload: {exc}")

    print("\nNo tested seed carried the full message with the selected safety setting.")
    print("Try a shorter message (e.g. HI), a larger board, or --allow-risky with careful disclosure.")
    if last_error:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
