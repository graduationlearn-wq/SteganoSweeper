from __future__ import annotations

import html
import json
import math
import time
from typing import Any, Dict, List, Tuple

import streamlit as st

try:
    from minesweeper import Minesweeper
    from solver import MinesweeperSolver
    from encoder import StegoEncoder
    from decoder import StegoDecoder
    from behavior_model import HumanBehaviorModel
except ImportError as exc:  # Show a useful message instead of a cryptic module error.
    st.set_page_config(page_title="SteganoSweeper", page_icon="💣", layout="wide")
    st.error(
        "The original SteganoSweeper modules could not be imported. "
        "Keep streamlit_app.py in the same folder as minesweeper.py, solver.py, "
        "encoder.py, decoder.py, behavior_model.py and choice_model.json."
    )
    st.exception(exc)
    st.stop()


ROWS = 16
COLS = 16
MINES = 40
OPENING_MOVE = (7, 7)  # Same opening used by the verified command-line demonstration.
MAX_PAYLOAD_BYTES = 5

st.set_page_config(
    page_title="SteganoSweeper | Interactive Studio",
    page_icon="💣",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# -----------------------------------------------------------------------------
# Core encode / blind-decode pipeline
# -----------------------------------------------------------------------------
def _snapshot(game: Minesweeper, step: int, last_move: Tuple[int, int] | None) -> Dict[str, Any]:
    """Capture only the visible board; hidden mine locations are not displayed."""
    cells = []
    for row in range(game.rows):
        line = []
        for col in range(game.cols):
            cell = game.board[row][col]
            line.append(
                {
                    "revealed": bool(cell.revealed),
                    "flagged": bool(cell.flagged),
                    "adjacent_mines": int(cell.adjacent_mines),
                }
            )
        cells.append(line)
    return {"step": step, "last_move": last_move, "cells": cells}


def build_replay_trace(
    seed: int,
    move_log: List[Dict[str, Any]],
    decoded_moves: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Replay the public coordinates and expose the decoder's per-step reasoning."""
    game = Minesweeper(rows=ROWS, cols=COLS, mines=MINES, seed=seed)
    if not game.reveal(*OPENING_MOVE):
        raise RuntimeError("The replay opening move was not safe.")

    decoder = StegoDecoder(
        rows=ROWS,
        cols=COLS,
        mines=MINES,
        seed=seed,
        risk_tolerance=0.05,
        allow_risky_moves=False,
        max_choices_per_move=32,
    )
    if decoder.behavior.model_type != "conditional_logit":
        raise RuntimeError("The blind decoder did not load choice_model.json.")

    solver = MinesweeperSolver(game, max_component_cells=20)
    last_move = OPENING_MOVE
    snapshots = [_snapshot(game, 0, OPENING_MOVE)]
    trace: List[Dict[str, Any]] = []
    recovered_integer = 0
    multiplier = 1

    for index, entry in enumerate(move_log):
        move = (int(entry["row"]), int(entry["col"]))
        choices, mode = decoder.get_encoding_choices(game, solver, last_move)

        if mode == "FORCED_SAFE":
            if not choices or move != choices[0]:
                raise RuntimeError(f"Forced move mismatch at replay step {index + 1}.")
            digit = None
            radix = 1
            rank = 1
            contribution = 0
            carrier = False
        elif mode in ("GUARANTEED_SAFE", "RISK_BASED"):
            if move not in choices:
                raise RuntimeError(f"Move {move} is not in the reconstructed candidate set at step {index + 1}.")
            digit = choices.index(move)
            radix = len(choices)
            rank = digit + 1
            contribution = digit * multiplier
            recovered_integer += contribution
            multiplier *= radix
            carrier = True
        else:
            raise RuntimeError(f"No candidate choices were available at replay step {index + 1}.")

        # Cross-check the displayed trace against the decoder's own result.
        decoded = decoded_moves[index]
        if decoded.get("move") != move or decoded.get("mode") != mode or decoded.get("digit") != digit:
            raise RuntimeError(f"Decoder trace consistency check failed at step {index + 1}.")

        safe = game.reveal(*move)
        if not safe:
            raise RuntimeError(f"The computer replay hit a mine at step {index + 1}.")

        trace.append(
            {
                "Step": index + 1,
                "Move (row, col)": f"({move[0] + 1}, {move[1] + 1})",
                "Mode": mode,
                "Candidate count / radix": radix,
                "Selected rank": rank if carrier else "Forced",
                "Digit (0-based)": digit if carrier else "—",
                "Capacity (bits)": round(math.log2(radix), 3) if carrier else 0.0,
                "Integer contribution": contribution,
                "Estimated risk": f"{float(entry.get('risk', 0.0)) * 100:.2f}%",
                "Candidate order (row, col)": ", ".join(
                    f"({r + 1},{c + 1})" for r, c in choices
                ),
            }
        )
        last_move = move
        snapshots.append(_snapshot(game, index + 1, move))

    return snapshots, trace


def encode_and_decode(message: str, first_seed: int, seed_attempts: int) -> Dict[str, Any]:
    model = HumanBehaviorModel()
    if model.model_type != "conditional_logit":
        reason = getattr(model, "model_load_error", None)
        suffix = f" Model load detail: {reason}" if reason else ""
        raise RuntimeError(
            "The trained conditional-logit model was not loaded. "
            "Place choice_model.json beside behavior_model.py and run "
            "python train_behavior_model.py if needed." + suffix
        )

    protocol_bits = StegoEncoder.message_to_integer(message)[1]
    failures = []

    for seed in range(first_seed, first_seed + max(1, seed_attempts)):
        try:
            game = Minesweeper(rows=ROWS, cols=COLS, mines=MINES, seed=seed)
            if not game.reveal(*OPENING_MOVE):
                raise RuntimeError("Opening move was unsafe.")

            encoder = StegoEncoder(
                game=game,
                initial_move=OPENING_MOVE,
                risk_tolerance=0.05,
                allow_risky_moves=False,
                max_choices_per_move=32,
            )
            if encoder.behavior.model_type != "conditional_logit":
                raise RuntimeError("The encoder did not load the trained model.")

            move_log = encoder.encode_message(message)
            replay = [(int(item["row"]), int(item["col"])) for item in move_log]

            # The decoder receives only public configuration and coordinates.
            blind_decoder = StegoDecoder(
                rows=ROWS,
                cols=COLS,
                mines=MINES,
                seed=seed,
                risk_tolerance=0.05,
                allow_risky_moves=False,
                max_choices_per_move=32,
            )
            if blind_decoder.behavior.model_type != "conditional_logit":
                raise RuntimeError("The blind decoder did not load the trained model.")

            decoded = blind_decoder.decode_replay(OPENING_MOVE, replay, verbose=False)
            if decoded["message"] != message:
                raise RuntimeError(
                    f"Decoded text mismatch: {decoded['message']!r}"
                )

            stats = encoder.get_statistics(protocol_bits=protocol_bits)
            snapshots, trace = build_replay_trace(seed, move_log, decoded["decoded_moves"])

            public_replay = {
                "format": "SteganoSweeper public replay v1",
                "board": {"rows": ROWS, "cols": COLS, "mines": MINES},
                "seed": seed,
                "opening_move_zero_based": list(OPENING_MOVE),
                "moves_zero_based": [list(move) for move in replay],
                "note": "Contains public replay coordinates only; it does not contain the secret message or mixed-radix digits.",
            }

            return {
                "message": message,
                "seed": seed,
                "move_log": move_log,
                "stats": stats,
                "decoded": decoded,
                "snapshots": snapshots,
                "trace": trace,
                "public_replay": public_replay,
                "model": {
                    "type": model.model_type,
                    "training_decisions": model.learned_model.get("training_decisions", 0),
                    "training_games": model.learned_model.get("training_games", 0),
                },
            }
        except Exception as exc:
            failures.append(f"Seed {seed}: {exc}")

    raise RuntimeError(
        "No tested seed had enough eligible choices to encode this message. "
        "Try a shorter message or increase the seed search.\n\n" + "\n".join(failures[-5:])
    )


# -----------------------------------------------------------------------------
# Visual presentation
# -----------------------------------------------------------------------------
def render_board(snapshot: Dict[str, Any]) -> str:
    cells = snapshot["cells"]
    rows = len(cells)
    cols = len(cells[0]) if rows else 0
    last_move = snapshot.get("last_move")

    css = f"""
    <style>
      .ss-board-scroll {{ width:100%; overflow-x:auto; padding:8px 2px 14px 2px; }}
      .ss-board {{ display:grid; grid-template-columns:repeat({cols}, 30px); gap:3px;
                  width:max-content; margin:0 auto; padding:10px; border-radius:14px;
                  background:#182234; border:1px solid #34445d; }}
      .ss-cell {{ width:30px; height:30px; display:flex; align-items:center; justify-content:center;
                  border-radius:6px; box-sizing:border-box; font:700 14px/1 Arial,sans-serif;
                  user-select:none; }}
      .ss-hidden {{ color:#cbd5e1; background:linear-gradient(145deg,#52647c,#36465c);
                    border:1px solid #687b94; box-shadow:inset 0 -2px 0 rgba(0,0,0,.18); }}
      .ss-open {{ color:#1e293b; background:#e7edf5; border:1px solid #cbd5e1; }}
      .ss-flag {{ color:#fff; background:#9a3412; border:1px solid #fb923c; }}
      .ss-last {{ outline:3px solid #facc15; outline-offset:1px; z-index:1; }}
      .ss-n1 {{ color:#2563eb; }} .ss-n2 {{ color:#15803d; }} .ss-n3 {{ color:#dc2626; }}
      .ss-n4 {{ color:#4338ca; }} .ss-n5 {{ color:#92400e; }} .ss-n6 {{ color:#0e7490; }}
      .ss-empty {{ color:#94a3b8; }}
      @media(max-width:700px) {{ .ss-board {{ grid-template-columns:repeat({cols}, 26px); gap:2px; }}
        .ss-cell {{ width:26px; height:26px; font-size:12px; }} }}
    </style>
    """

    parts = [css, '<div class="ss-board-scroll"><div class="ss-board">']
    for r in range(rows):
        for c in range(cols):
            cell = cells[r][c]
            is_last = last_move == (r, c)
            classes = ["ss-cell"]
            if cell["flagged"] and not cell["revealed"]:
                label = "⚑"
                classes.append("ss-flag")
            elif not cell["revealed"]:
                label = ""
                classes.append("ss-hidden")
            else:
                value = cell["adjacent_mines"]
                label = str(value) if value else ""
                classes.append("ss-open")
                classes.append(f"ss-n{value}" if value else "ss-empty")
            if is_last:
                classes.append("ss-last")
            parts.append(f'<div class="{" ".join(classes)}">{html.escape(label) if label else "&nbsp;"}</div>')
    parts.append("</div></div>")
    return "\n".join(parts)


def show_result(result: Dict[str, Any]) -> None:
    stats = result["stats"]
    decoded = result["decoded"]

    st.divider()
    st.subheader("1 · Encoded gameplay")
    st.caption(
        f"Computer player · seed {result['seed']} · {ROWS} × {COLS} board · {MINES} mines · "
        f"opening cell ({OPENING_MOVE[0] + 1}, {OPENING_MOVE[1] + 1})"
    )

    top_cols = st.columns(4)
    top_cols[0].metric("Moves", stats["total_moves"])
    top_cols[1].metric("Carrier moves", stats["carrier_moves"])
    top_cols[2].metric("Protocol size", f"{stats['protocol_bits']} bits")
    top_cols[3].metric("Theoretical capacity", f"{stats['theoretical_capacity_bits']:.2f} bits")
    st.caption(
        f"Forced moves: {stats['forced_moves']} · "
        f"Capacity margin: {stats['capacity_margin_bits']:.2f} bits · "
        f"Average estimated risk: {stats['average_estimated_risk'] * 100:.2f}%"
    )

    speed = st.slider(
        "Animation delay per move (seconds)",
        min_value=0.05,
        max_value=0.70,
        value=0.16,
        step=0.05,
        key="animation_speed",
    )

    if st.button("▶ Play computer game", type="primary", use_container_width=False):
        board_slot = st.empty()
        status_slot = st.empty()
        progress_slot = st.progress(0)
        total_frames = len(result["snapshots"])
        for frame_index, snapshot in enumerate(result["snapshots"]):
            board_slot.markdown(render_board(snapshot), unsafe_allow_html=True)
            if frame_index == 0:
                status_slot.caption("Opening move: board generated with a protected first reveal.")
            else:
                move = result["move_log"][frame_index - 1]
                status_slot.caption(
                    f"Move {frame_index}/{total_frames - 1} · "
                    f"Cell ({int(move['row']) + 1}, {int(move['col']) + 1}) · "
                    f"{move['mode']} · "
                    f"{'Carries message information' if move['carrier'] else 'Forced safe move'}"
                )
            progress_slot.progress((frame_index + 1) / total_frames)
            if frame_index < total_frames - 1:
                time.sleep(speed)
        st.session_state["animation_completed"] = True

    if st.session_state.get("animation_completed", False):
        frame_index = st.slider(
            "Replay timeline",
            min_value=0,
            max_value=len(result["snapshots"]) - 1,
            value=len(result["snapshots"]) - 1,
            key="replay_frame",
            help="Move backward or forward to inspect the board after each computer move.",
        )
        st.markdown(render_board(result["snapshots"][frame_index]), unsafe_allow_html=True)
        if frame_index == 0:
            st.caption("Initial board after the protected opening reveal.")
        else:
            st.caption(f"Showing the board after computer move {frame_index}.")
    else:
        st.markdown(render_board(result["snapshots"][0]), unsafe_allow_html=True)
        st.info("Select **Play computer game** to watch the computer reveal the encoded move sequence.")

    with st.expander("Public replay coordinates", expanded=False):
        coordinates = [f"({m['row']}, {m['col']})" for m in result["move_log"]]
        st.code(" ".join(coordinates), language="text")
        st.caption("Coordinates in this raw replay list are zero-based (row 0 to 15, column 0 to 15). The decoder table displays one-based coordinates.")
        st.download_button(
            "Download public replay JSON",
            data=json.dumps(result["public_replay"], indent=2),
            file_name="steganosweeper_public_replay.json",
            mime="application/json",
        )
        st.caption("The downloaded replay contains the seed and public cell coordinates, not the secret text or the mixed-radix digits.")

    st.divider()
    st.subheader("2 · Blind decoder")
    st.write(
        "The decoder is given the board configuration, seed, opening cell and public move coordinates. "
        "It rebuilds the candidate set at every step, finds each selected move's position, and reconstructs the mixed-radix integer."
    )

    if st.button("🔓 Decode message", type="primary", key="decode_button"):
        st.session_state["decoder_revealed"] = True

    if st.session_state.get("decoder_revealed", False):
        st.success("Blind replay decoding completed successfully. The recovered text matches the input.")
        decoded_col, stats_col = st.columns([1.4, 1])
        with decoded_col:
            st.markdown("**Recovered message**")
            st.text_area(
                "Decoded output",
                value=decoded["message"],
                height=90,
                disabled=True,
                label_visibility="collapsed",
            )
        with stats_col:
            st.metric("Decoded carrier moves", decoded["carrier_moves"])
            st.metric("Reconstructed capacity", f"{decoded['theoretical_capacity_bits']:.2f} bits")

        st.markdown("**Step-by-step reconstruction**")
        st.dataframe(result["trace"], use_container_width=True, hide_index=True)
        st.caption(
            "Selected rank is 1-based for readability. The digit used by the mixed-radix decoder is 0-based. "
            "Candidate order is reconstructed from the replayed visible state and the same trained model."
        )
        st.markdown("**Recovery logic**")
        st.code(
            "digit = selected move's index in reconstructed candidate list\n"
            "recovered_integer += digit × current_multiplier\n"
            "current_multiplier *= candidate_count (radix)\n"
            "parse sentinel + 32-bit payload length + UTF-8 bytes",
            language="text",
        )
        st.success("MESSAGE RECOVERY: SUCCESS")


def main() -> None:
    st.markdown(
        "<div style='padding:6px 0 2px 0'>"
        "<div style='font-size:13px;letter-spacing:2px;color:#64748b;font-weight:700'>GAME-ACTION STEGANOGRAPHY LAB</div>"
        "<h1 style='margin:0'>💣 SteganoSweeper</h1>"
        "<p style='font-size:17px;color:#64748b;margin-top:4px'>Hide a short message in a computer-played Minesweeper game — then recover it from the public replay.</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    model = HumanBehaviorModel()
    if model.model_type != "conditional_logit":
        st.error(
            "Trained model not detected. Put your trained choice_model.json in this folder, "
            "beside behavior_model.py, then run: python train_behavior_model.py"
        )
        if getattr(model, "model_load_error", None):
            st.caption(f"Model loading detail: {model.model_load_error}")
        st.stop()

    st.caption(
        f"Loaded model: conditional logit · {model.learned_model.get('training_decisions', 0)} training decisions · "
        f"{model.learned_model.get('training_games', 0)} games"
    )

    with st.form("message_form"):
        st.subheader("Compose a secret message")
        message = st.text_area(
            "Message to hide",
            value="HI",
            max_chars=20,
            height=100,
            placeholder="Type a short message...",
            help=f"Demo limit: {MAX_PAYLOAD_BYTES} UTF-8 bytes. HI uses 2 bytes; HELLO uses 5 bytes. The protocol also adds a 1-bit sentinel and a 32-bit length header.",
        )
        settings = st.columns(3)
        seed_start = settings[0].number_input("Starting seed", min_value=0, max_value=2_000_000_000, value=42, step=1)
        attempts = settings[1].selectbox("Seeds to try", options=[1, 5, 12, 20, 30], index=2)
        settings[2].markdown(
            "**Board**\n\n16 × 16 · 40 mines\n\nGuaranteed-safe moves only",
        )
        submitted = st.form_submit_button("🔐 Encode message", type="primary", use_container_width=True)

    if submitted:
        st.session_state.pop("stegano_result", None)
        st.session_state.pop("animation_completed", None)
        st.session_state.pop("decoder_revealed", None)
        st.session_state.pop("replay_frame", None)
        if not message:
            st.error("Enter a message before encoding.")
        else:
            payload_bytes = len(message.encode("utf-8"))
            if payload_bytes > MAX_PAYLOAD_BYTES:
                st.error(
                    f"Message is {payload_bytes} UTF-8 bytes. The current demo limit is "
                    f"{MAX_PAYLOAD_BYTES} bytes. Shorten the text before encoding."
                )
            else:
                with st.spinner("Generating board, embedding the message and verifying blind decoding..."):
                    try:
                        st.session_state["stegano_result"] = encode_and_decode(
                            message, int(seed_start), int(attempts)
                        )
                    except Exception as exc:
                        st.session_state.pop("stegano_result", None)
                        st.error(str(exc))

    result = st.session_state.get("stegano_result")
    if result:
        show_result(result)

    st.divider()
    st.caption(
        "Research prototype: the displayed risk is the solver's estimated risk, not a security guarantee. "
        "The current demo uses a fixed 16×16 board and a short UTF-8 payload to keep the replay practical."
    )


if __name__ == "__main__":
    main()
