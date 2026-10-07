import csv
import json
import math
import os
import random
import shutil
import time
import tkinter as tk
from datetime import datetime


class CSVLoggerBase:
    """Small reusable CSV writer with safe schema migration."""

    def __init__(self, filename, fieldnames):
        self.filename = os.path.abspath(filename)
        self.fieldnames = list(fieldnames)
        os.makedirs(os.path.dirname(self.filename) or ".", exist_ok=True)
        self._ensure_schema()

    def _ensure_schema(self):
        if not os.path.exists(self.filename) or os.path.getsize(self.filename) == 0:
            with open(self.filename, "w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=self.fieldnames).writeheader()
            return

        try:
            with open(self.filename, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                old_fields = reader.fieldnames or []
                rows = list(reader)

            if old_fields == self.fieldnames:
                return

            backup = (
                os.path.splitext(self.filename)[0]
                + "_backup_"
                + datetime.now().strftime("%Y%m%d_%H%M%S")
                + ".csv"
            )
            shutil.copy2(self.filename, backup)

            with open(self.filename, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.fieldnames)
                writer.writeheader()
                for old_row in rows:
                    writer.writerow({field: old_row.get(field, "") for field in self.fieldnames})

            print(f"CSV schema updated: {os.path.basename(self.filename)}")
            print(f"Backup created: {backup}")

        except (OSError, csv.Error) as exc:
            raise RuntimeError(f"Could not prepare CSV file '{self.filename}': {exc}") from exc


class CSVGameplayLogger(CSVLoggerBase):
    """One row per genuine GUI action.

    Only player-visible board information and derived features are written.
    Hidden mine coordinates are never written.
    """

    FIELDNAMES = [
        "session_id",
        "game_id",
        "game_seed",
        "board_rows",
        "board_cols",
        "mine_count",
        "step",
        "timestamp",
        "elapsed_sec",
        "delta_sec",
        "action",
        "source",
        "row",
        "col",
        "first_move",
        "revealed_before",
        "revealed_after",
        "flags_before",
        "flags_after",
        "remaining_mines_before",
        "remaining_mines_after",
        "adjacent_revealed_before",
        "adjacent_numbered_before",
        "hidden_neighbors_before",
        "frontier_score_before",
        "distance_from_last_action",
        "distance_to_nearest_revealed_before",
        "distance_to_nearest_numbered_before",
        "mean_adjacent_clue_before",
        "min_adjacent_clue_before",
        "max_adjacent_clue_before",
        "constraint_count_before",
        "risk_estimate_before",
        "information_proxy_before",
        "is_frontier_before",
        "visible_board_before",
        "visible_board_after",
        "outcome",
        "game_status",
    ]

    def __init__(self, filename="human_gameplay.csv", session_id=None):
        super().__init__(filename, self.FIELDNAMES)
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.game_counter = 0
        self.step = 0
        self.previous_action_time = None

    def start_game(self):
        self.game_counter += 1
        self.step = 0
        self.previous_action_time = None

    def log(
        self,
        event,
        game,
        visible_before,
        visible_after,
        features,
        flags_before,
        flags_after,
        remaining_before,
        remaining_after,
        revealed_before,
        revealed_after,
        first_move,
        outcome,
        source="direct",
    ):
        now = time.time()
        delta = "" if self.previous_action_time is None else round(now - self.previous_action_time, 4)
        self.previous_action_time = now
        self.step += 1

        status = "playing"
        if game.game_over:
            status = "won" if game.win else "lost"

        row = {
            "session_id": self.session_id,
            "game_id": self.game_counter,
            "game_seed": game.current_seed,
            "board_rows": game.rows,
            "board_cols": game.cols,
            "mine_count": game.mine_count,
            "step": self.step,
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "elapsed_sec": game.elapsed,
            "delta_sec": delta,
            "action": event,
            "source": source,
            "row": features["row"],
            "col": features["col"],
            "first_move": int(first_move),
            "revealed_before": revealed_before,
            "revealed_after": revealed_after,
            "flags_before": flags_before,
            "flags_after": flags_after,
            "remaining_mines_before": remaining_before,
            "remaining_mines_after": remaining_after,
            "adjacent_revealed_before": features["adjacent_revealed"],
            "adjacent_numbered_before": features["adjacent_numbered"],
            "hidden_neighbors_before": features["hidden_neighbors"],
            "frontier_score_before": round(features["frontier_score"], 6),
            "distance_from_last_action": round(features["distance_from_last_action"], 6),
            "distance_to_nearest_revealed_before": round(features["distance_to_nearest_revealed"], 6),
            "distance_to_nearest_numbered_before": round(features["distance_to_nearest_numbered"], 6),
            "mean_adjacent_clue_before": _csv_float(features["mean_adjacent_clue"]),
            "min_adjacent_clue_before": _csv_float(features["min_adjacent_clue"]),
            "max_adjacent_clue_before": _csv_float(features["max_adjacent_clue"]),
            "constraint_count_before": features["constraint_count"],
            "risk_estimate_before": _csv_float(features["risk_estimate"]),
            "information_proxy_before": round(features["information_proxy"], 6),
            "is_frontier_before": int(features["is_frontier"]),
            "visible_board_before": visible_before,
            "visible_board_after": visible_after,
            "outcome": outcome,
            "game_status": status,
        }

        with open(self.filename, "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=self.fieldnames).writerow(row)


class HumanDecisionLogger(CSVLoggerBase):
    """One row per independent human reveal decision.

    Candidate alternatives are stored as JSON in one row. This avoids creating
    hundreds of CSV rows for every single decision while preserving the full
    candidate-choice information needed for later ML preprocessing.
    """

    FIELDNAMES = [
        "session_id",
        "game_id",
        "game_seed",
        "decision_step",
        "timestamp",
        "elapsed_sec",
        "decision_delta_sec",
        "selected_row",
        "selected_col",
        "selected_outcome",
        "selected_is_frontier",
        "selected_risk_estimate",
        "selected_adjacent_numbered",
        "selected_frontier_score",
        "selected_information_proxy",
        "candidate_count",
        "frontier_candidate_count",
        "selected_in_candidate_pool",
        "candidate_generation",
        "candidates_json",
        "game_status",
    ]

    def __init__(self, filename="human_decisions.csv", session_id=None):
        super().__init__(filename, self.FIELDNAMES)
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.decision_counter = 0
        self.previous_decision_time = None

    def start_game(self):
        self.previous_decision_time = None

    def log_decision(
        self,
        game,
        selected_features,
        selected_outcome,
        candidates,
        candidate_generation,
    ):
        now = time.time()
        delta = "" if self.previous_decision_time is None else round(now - self.previous_decision_time, 4)
        self.previous_decision_time = now
        self.decision_counter += 1

        status = "playing"
        if game.game_over:
            status = "won" if game.win else "lost"

        # The GUI guarantees the selected cell is represented in the final
        # candidate list, but we also record whether it was already in the
        # naturally generated pool before that safeguard.
        naturally_in_pool = any(
            c["row"] == selected_features["row"]
            and c["col"] == selected_features["col"]
            for c in candidates
        )

        candidate_count = len(candidates)
        frontier_count = sum(int(c["is_frontier"]) for c in candidates)

        candidates_json = json.dumps(candidates, separators=(",", ":"))

        row = {
            "session_id": self.session_id,
            "game_id": self._game_id(game),
            "game_seed": game.current_seed,
            "decision_step": self.decision_counter,
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "elapsed_sec": game.elapsed,
            "decision_delta_sec": delta,
            "selected_row": selected_features["row"],
            "selected_col": selected_features["col"],
            "selected_outcome": selected_outcome,
            "selected_is_frontier": int(selected_features["is_frontier"]),
            "selected_risk_estimate": _csv_float(selected_features["risk_estimate"]),
            "selected_adjacent_numbered": selected_features["adjacent_numbered"],
            "selected_frontier_score": round(selected_features["frontier_score"], 6),
            "selected_information_proxy": round(selected_features["information_proxy"], 6),
            "candidate_count": candidate_count,
            "frontier_candidate_count": frontier_count,
            "selected_in_candidate_pool": int(naturally_in_pool),
            "candidate_generation": candidate_generation,
            "candidates_json": candidates_json,
            "game_status": status,
        }

        with open(self.filename, "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=self.fieldnames).writerow(row)

    def _game_id(self, game):
        return game.logger.game_counter


class MinesweeperGUI:
    """Clickable Minesweeper with research-grade human gameplay logging.

    Controls
    --------
    Left click   : reveal
    Right click  : flag / unflag
    Double click : chord a revealed number

    Files produced
    --------------
    human_gameplay.csv  : one row per genuine action
    human_decisions.csv : one row per independent reveal decision, with
                          candidate alternatives stored as JSON

    Hidden mine coordinates are never written into either dataset.
    """

    NUMBER_COLORS = {
        1: "#0000FF",
        2: "#008000",
        3: "#FF0000",
        4: "#000080",
        5: "#800000",
        6: "#008080",
        7: "#000000",
        8: "#808080",
    }

    MAX_EXPLORATION_CANDIDATES = 12

    def __init__(
        self,
        root,
        rows=16,
        cols=16,
        mines=40,
        seed=None,
        csv_filename="human_gameplay.csv",
        decisions_filename="human_decisions.csv",
    ):
        self.root = root
        self.rows = rows
        self.cols = cols
        self.mine_count = mines
        self.seed = seed

        # One shared session ID links both CSV files.
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.logger = CSVGameplayLogger(csv_filename, session_id=session_id)
        self.decision_logger = HumanDecisionLogger(decisions_filename, session_id=session_id)

        self.last_action_cell = None

        self.root.title("Minesweeper — Human Gameplay Data Collection")
        self.root.resizable(False, False)
        self.root.configure(bg="#c0c0c0")

        self.buttons = []
        self._build_ui()
        self.new_game()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        outer = tk.Frame(self.root, bg="#c0c0c0", bd=6, relief=tk.RAISED)
        outer.pack(padx=8, pady=8)

        top = tk.Frame(outer, bg="#c0c0c0", bd=3, relief=tk.SUNKEN)
        top.pack(fill="x", pady=(0, 6))

        self.mine_display = tk.Label(
            top,
            text="040",
            font=("Courier New", 20, "bold"),
            fg="#ff2020",
            bg="#000000",
            width=4,
            relief=tk.SUNKEN,
        )
        self.mine_display.pack(side="left", padx=6, pady=5)

        self.face = tk.Button(
            top,
            text="🙂",
            font=("Segoe UI Emoji", 18),
            width=3,
            height=1,
            command=self.new_game,
            bd=3,
            relief=tk.RAISED,
        )
        self.face.pack(side="left", expand=True, padx=8, pady=4)

        self.timer_display = tk.Label(
            top,
            text="000",
            font=("Courier New", 20, "bold"),
            fg="#ff2020",
            bg="#000000",
            width=4,
            relief=tk.SUNKEN,
        )
        self.timer_display.pack(side="right", padx=6, pady=5)

        board_frame = tk.Frame(outer, bg="#808080", bd=3, relief=tk.SUNKEN)
        board_frame.pack()

        for r in range(self.rows):
            row_buttons = []
            for c in range(self.cols):
                btn = tk.Button(
                    board_frame,
                    text="",
                    width=2,
                    height=1,
                    font=("Consolas", 10, "bold"),
                    bd=2,
                    relief=tk.RAISED,
                    padx=0,
                    pady=0,
                    takefocus=False,
                )
                btn.grid(row=r, column=c, sticky="nsew")
                btn.bind("<Button-1>", lambda e, rr=r, cc=c: self.left_click(rr, cc))
                btn.bind("<Button-3>", lambda e, rr=r, cc=c: self.right_click(rr, cc))
                btn.bind("<Double-Button-1>", lambda e, rr=r, cc=c: self.chord(rr, cc))
                row_buttons.append(btn)
            self.buttons.append(row_buttons)

        self.status = tk.Label(
            outer,
            text="Left click to reveal • Right click to flag",
            font=("Segoe UI", 9),
            bg="#c0c0c0",
            fg="#202020",
            pady=5,
        )
        self.status.pack()

        self.csv_status = tk.Label(
            outer,
            text="Recording → human_gameplay.csv + human_decisions.csv",
            font=("Segoe UI", 8),
            bg="#c0c0c0",
            fg="#555555",
            pady=5,
        )
        self.csv_status.pack()

    # ------------------------------------------------------------------
    # Game state
    # ------------------------------------------------------------------

    def new_game(self):
        self.current_seed = (
            random.randrange(1, 2**31 - 1)
            if self.seed is None
            else self.seed
        )

        self.rng = random.Random(self.current_seed)
        self.mines = set()
        self.numbers = [[0 for _ in range(self.cols)] for _ in range(self.rows)]
        self.revealed = [[False for _ in range(self.cols)] for _ in range(self.rows)]
        self.flagged = [[False for _ in range(self.cols)] for _ in range(self.rows)]

        self.first_move = True
        self.game_over = False
        self.win = False
        self.start_time = None
        self.elapsed = 0
        self.last_action_cell = None
        self._hit_mine = None

        self._reset_buttons()
        self._update_counters()
        self.timer_display.config(text="000")
        self.face.config(text="🙂")
        self.status.config(text="Left click to reveal • Right click to flag")

        self.logger.start_game()
        self.decision_logger.start_game()

        if hasattr(self, "timer_job"):
            try:
                self.root.after_cancel(self.timer_job)
            except Exception:
                pass
        self.timer_job = self.root.after(250, self._update_timer)

    def _reset_buttons(self):
        for r in range(self.rows):
            for c in range(self.cols):
                self.buttons[r][c].config(
                    text="",
                    state=tk.NORMAL,
                    relief=tk.RAISED,
                    bd=2,
                    bg="#c0c0c0",
                    fg="#000000",
                )

    def _count_revealed(self):
        return sum(
            self.revealed[r][c]
            for r in range(self.rows)
            for c in range(self.cols)
        )

    def _count_flags(self):
        return sum(
            self.flagged[r][c]
            for r in range(self.rows)
            for c in range(self.cols)
        )

    def _update_counters(self):
        remaining = self.mine_count - self._count_flags()
        self.mine_display.config(text=f"{remaining:03d}")

    def _update_timer(self):
        if self.start_time is not None and not self.game_over:
            self.elapsed = min(999, int(time.time() - self.start_time))
            self.timer_display.config(text=f"{self.elapsed:03d}")
        self.timer_job = self.root.after(250, self._update_timer)

    # ------------------------------------------------------------------
    # Board helpers
    # ------------------------------------------------------------------

    def _neighbors(self, r, c):
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                rr = r + dr
                cc = c + dc
                if 0 <= rr < self.rows and 0 <= cc < self.cols:
                    yield rr, cc

    def _place_mines(self, first_r, first_c):
        # Preserve the first-click-safe behavior.
        protected = {(first_r, first_c)}
        protected.update(self._neighbors(first_r, first_c))

        available = [
            (r, c)
            for r in range(self.rows)
            for c in range(self.cols)
            if (r, c) not in protected
        ]

        if self.mine_count > len(available):
            raise ValueError("Too many mines for this board size.")

        self.mines = set(self.rng.sample(available, self.mine_count))

        for r in range(self.rows):
            for c in range(self.cols):
                if (r, c) in self.mines:
                    self.numbers[r][c] = -1
                else:
                    self.numbers[r][c] = sum(
                        (nr, nc) in self.mines
                        for nr, nc in self._neighbors(r, c)
                    )

    # ------------------------------------------------------------------
    # Visible-state / behavior features
    # ------------------------------------------------------------------

    def _visible_board(self):
        """Serialize only what the human can currently see."""
        rows = []
        for r in range(self.rows):
            cells = []
            for c in range(self.cols):
                if self.flagged[r][c]:
                    cells.append("F")
                elif not self.revealed[r][c]:
                    cells.append("#")
                else:
                    cells.append(str(self.numbers[r][c]))
            rows.append("".join(cells))
        return "/".join(rows)

    @staticmethod
    def _euclidean(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def _distance_to_nearest(self, r, c, cells):
        if not cells:
            return 0.0
        return min(self._euclidean((r, c), cell) for cell in cells)

    def _visible_constraints_for_candidate(self, r, c):
        """Return visible clue-derived mine-ratio evidence for candidate.

        This uses ONLY revealed numbers and visible flags. It does not inspect
        self.mines, so it is safe to use as a human-information feature.
        """
        ratios = []
        constraint_count = 0

        for nr, nc in self._neighbors(r, c):
            if not self.revealed[nr][nc]:
                continue

            clue = self.numbers[nr][nc]
            if clue < 0:
                continue

            neigh = list(self._neighbors(nr, nc))
            unknown_cells = [
                (ar, ac)
                for ar, ac in neigh
                if not self.revealed[ar][ac] and not self.flagged[ar][ac]
            ]
            flag_count = sum(self.flagged[ar][ac] for ar, ac in neigh)

            if unknown_cells:
                remaining = clue - flag_count
                ratios.append(max(0.0, min(1.0, remaining / len(unknown_cells))))
                constraint_count += 1

        return ratios, constraint_count

    def _candidate_features(self, r, c, for_first_move=False):
        neighbors = list(self._neighbors(r, c))

        adjacent_revealed = sum(self.revealed[nr][nc] for nr, nc in neighbors)
        adjacent_numbered_values = [
            self.numbers[nr][nc]
            for nr, nc in neighbors
            if self.revealed[nr][nc] and self.numbers[nr][nc] > 0
        ]
        hidden_neighbors = sum(
            not self.revealed[nr][nc] and not self.flagged[nr][nc]
            for nr, nc in neighbors
        )

        frontier_score = adjacent_numbered_values.__len__() / max(1, len(neighbors))
        is_frontier = bool(adjacent_numbered_values)

        if self.last_action_cell is None:
            distance_from_last_action = 0.0
        else:
            distance_from_last_action = self._euclidean(
                (r, c), self.last_action_cell
            )

        revealed_cells = [
            (rr, cc)
            for rr in range(self.rows)
            for cc in range(self.cols)
            if self.revealed[rr][cc]
        ]
        numbered_cells = [
            (rr, cc)
            for rr in range(self.rows)
            for cc in range(self.cols)
            if self.revealed[rr][cc] and self.numbers[rr][cc] > 0
        ]

        mean_clue = (
            sum(adjacent_numbered_values) / len(adjacent_numbered_values)
            if adjacent_numbered_values
            else None
        )
        min_clue = min(adjacent_numbered_values) if adjacent_numbered_values else None
        max_clue = max(adjacent_numbered_values) if adjacent_numbered_values else None

        ratios, constraint_count = self._visible_constraints_for_candidate(r, c)

        # If visible clue constraints touch the candidate, use their average
        # mine-ratio evidence. Otherwise use the global visible mine density.
        if for_first_move:
            risk_estimate = None
        elif ratios:
            risk_estimate = sum(ratios) / len(ratios)
        else:
            unknown_unflagged = sum(
                not self.revealed[rr][cc] and not self.flagged[rr][cc]
                for rr in range(self.rows)
                for cc in range(self.cols)
            )
            remaining_mines = max(0, self.mine_count - self._count_flags())
            risk_estimate = (
                min(1.0, remaining_mines / unknown_unflagged)
                if unknown_unflagged
                else 0.0
            )

        # This is a deliberately simple, interpretable information proxy,
        # not a claim of true expected information gain.
        information_proxy = (
            0.5 * (adjacent_numbered_values.__len__() / 8.0)
            + 0.5 * (hidden_neighbors / 8.0)
        )

        return {
            "row": r,
            "col": c,
            "adjacent_revealed": adjacent_revealed,
            "adjacent_numbered": len(adjacent_numbered_values),
            "hidden_neighbors": hidden_neighbors,
            "frontier_score": frontier_score,
            "distance_from_last_action": distance_from_last_action,
            "distance_to_nearest_revealed": self._distance_to_nearest(r, c, revealed_cells),
            "distance_to_nearest_numbered": self._distance_to_nearest(r, c, numbered_cells),
            "mean_adjacent_clue": mean_clue,
            "min_adjacent_clue": min_clue,
            "max_adjacent_clue": max_clue,
            "constraint_count": constraint_count,
            "risk_estimate": risk_estimate,
            "information_proxy": information_proxy,
            "is_frontier": is_frontier,
        }

    def _build_candidate_pool(self, selected_r, selected_c):
        """Generate a human-oriented candidate pool before a direct reveal.

        Priority is given to hidden cells adjacent to revealed numbered cells,
        because these are the board frontier. To preserve exploration behavior,
        a small deterministic set of nearby non-frontier cells is added.
        The actual selected cell is always included so accidental exploration
        remains represented correctly.
        """
        hidden = [
            (r, c)
            for r in range(self.rows)
            for c in range(self.cols)
            if not self.revealed[r][c] and not self.flagged[r][c]
        ]

        frontier = []
        non_frontier = []

        for r, c in hidden:
            f = self._candidate_features(r, c)
            if f["is_frontier"]:
                frontier.append(f)
            else:
                non_frontier.append(f)

        # Stable sorting: board context first, then proximity.
        frontier.sort(
            key=lambda f: (
                -f["adjacent_numbered"],
                f["distance_to_nearest_numbered"],
                f["distance_from_last_action"],
                f["row"],
                f["col"],
            )
        )

        non_frontier.sort(
            key=lambda f: (
                f["distance_to_nearest_revealed"],
                f["distance_from_last_action"],
                f["row"],
                f["col"],
            )
        )

        # Keep all frontier cells. Add a small exploration context around the
        # known region so the model can learn that humans sometimes explore.
        candidates = frontier + non_frontier[: self.MAX_EXPLORATION_CANDIDATES]

        selected_exists = any(
            f["row"] == selected_r and f["col"] == selected_c
            for f in candidates
        )

        if not selected_exists:
            candidates.append(self._candidate_features(selected_r, selected_c))

        # Deterministic ordering for reproducibility and later preprocessing.
        candidates.sort(key=lambda f: (f["row"], f["col"]))

        return candidates, len(frontier)

    # ------------------------------------------------------------------
    # Action logging
    # ------------------------------------------------------------------

    def _emit_action(
        self,
        action,
        r,
        c,
        source="direct",
        first_move=False,
        visible_before=None,
        flags_before=None,
        remaining_before=None,
        revealed_before=None,
        outcome="unknown",
        features=None,
    ):
        features = features or self._candidate_features(r, c, for_first_move=first_move)
        visible_before = visible_before if visible_before is not None else self._visible_board()
        flags_before = flags_before if flags_before is not None else self._count_flags()
        remaining_before = (
            remaining_before
            if remaining_before is not None
            else self.mine_count - flags_before
        )
        revealed_before = (
            revealed_before
            if revealed_before is not None
            else self._count_revealed()
        )

        visible_after = self._visible_board()
        flags_after = self._count_flags()
        remaining_after = self.mine_count - flags_after
        revealed_after = self._count_revealed()

        self.logger.log(
            action,
            self,
            visible_before,
            visible_after,
            features,
            flags_before,
            flags_after,
            remaining_before,
            remaining_after,
            revealed_before,
            revealed_after,
            first_move,
            outcome,
            source=source,
        )

        self.last_action_cell = (r, c)

    # ------------------------------------------------------------------
    # Player actions
    # ------------------------------------------------------------------

    def left_click(self, r, c, log_action=True, source="direct"):
        if self.game_over or self.flagged[r][c] or self.revealed[r][c]:
            return

        visible_before = self._visible_board()
        flags_before = self._count_flags()
        remaining_before = self.mine_count - flags_before
        revealed_before = self._count_revealed()
        was_first_move = self.first_move

        # Candidate data only makes sense for an independent human reveal.
        # The first move initializes the board, so it is intentionally skipped.
        candidates = None
        frontier_count = 0
        candidate_generation = "not_recorded_first_move"

        if not was_first_move and source == "direct":
            candidates, frontier_count = self._build_candidate_pool(r, c)
            candidate_generation = "frontier_plus_nearby_exploration"

        features = self._candidate_features(
            r,
            c,
            for_first_move=was_first_move,
        )

        # First click creates the hidden board after the player chooses it.
        if self.first_move:
            self._place_mines(r, c)
            self.first_move = False
            self.start_time = time.time()

        # Process the action BEFORE logging the result.
        if (r, c) in self.mines:
            self.revealed[r][c] = True
            self._reveal_mine_hit(r, c)
            self._lose()
            outcome = "mine_hit"
        else:
            self._reveal_from(r, c)
            self._check_win()
            outcome = "safe_win" if self.game_over and self.win else "safe"

        if log_action:
            self._emit_action(
                "reveal",
                r,
                c,
                source=source,
                first_move=was_first_move,
                visible_before=visible_before,
                flags_before=flags_before,
                remaining_before=remaining_before,
                revealed_before=revealed_before,
                outcome=outcome,
                features=features,
            )

        # Only direct human reveals are used as independent choice examples.
        if not was_first_move and source == "direct" and candidates is not None:
            self.decision_logger.log_decision(
                self,
                features,
                outcome,
                candidates,
                candidate_generation,
            )

    def right_click(self, r, c):
        if self.game_over or self.revealed[r][c]:
            return

        if self.first_move:
            self.status.config(text="Reveal a cell first.")
            return

        visible_before = self._visible_board()
        flags_before = self._count_flags()
        remaining_before = self.mine_count - flags_before
        revealed_before = self._count_revealed()
        features = self._candidate_features(r, c)

        new_flag_state = not self.flagged[r][c]
        self.flagged[r][c] = new_flag_state

        self._render_cell(r, c)
        self._update_counters()

        outcome = "flagged" if new_flag_state else "unflagged"

        self._emit_action(
            "flag" if new_flag_state else "unflag",
            r,
            c,
            first_move=False,
            visible_before=visible_before,
            flags_before=flags_before,
            remaining_before=remaining_before,
            revealed_before=revealed_before,
            outcome=outcome,
            features=features,
        )

        self._check_win()

    def chord(self, r, c):
        if (
            self.game_over
            or not self.revealed[r][c]
            or self.numbers[r][c] <= 0
        ):
            return

        neighbors = list(self._neighbors(r, c))
        flag_count = sum(self.flagged[nr][nc] for nr, nc in neighbors)

        if flag_count != self.numbers[r][c]:
            return

        for nr, nc in neighbors:
            if not self.flagged[nr][nc] and not self.revealed[nr][nc]:
                self.left_click(nr, nc, source="chord")
                if self.game_over:
                    break

    def _reveal_from(self, start_r, start_c):
        stack = [(start_r, start_c)]
        visited = set()

        while stack:
            r, c = stack.pop()
            if (r, c) in visited:
                continue
            visited.add((r, c))

            if self.flagged[r][c] or self.revealed[r][c] or (r, c) in self.mines:
                continue

            self.revealed[r][c] = True
            self._render_cell(r, c)

            if self.numbers[r][c] == 0:
                for nr, nc in self._neighbors(r, c):
                    if not self.revealed[nr][nc] and not self.flagged[nr][nc]:
                        stack.append((nr, nc))

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_cell(self, r, c):
        btn = self.buttons[r][c]

        if self.flagged[r][c]:
            btn.config(text="🚩", fg="#d00000", bg="#c0c0c0", relief=tk.RAISED)
            return

        if not self.revealed[r][c]:
            btn.config(text="", bg="#c0c0c0", relief=tk.RAISED)
            return

        value = self.numbers[r][c]
        btn.config(relief=tk.SUNKEN, bd=1, bg="#d0d0d0")

        if value == 0:
            btn.config(text="", fg="#000000")
        elif value == -1:
            btn.config(text="💣", fg="#000000", bg="#ffb0b0")
        else:
            btn.config(text=str(value), fg=self.NUMBER_COLORS.get(value, "#000000"))

    def _reveal_mine_hit(self, r, c):
        self._hit_mine = (r, c)
        self.buttons[r][c].config(
            text="💣",
            fg="#000000",
            bg="#ff6666",
            relief=tk.SUNKEN,
            bd=1,
        )

    def _show_board_after_loss(self):
        for r in range(self.rows):
            for c in range(self.cols):
                btn = self.buttons[r][c]

                if (r, c) in self.mines:
                    if (r, c) == getattr(self, "_hit_mine", None):
                        btn.config(text="💣", bg="#ff6666", relief=tk.SUNKEN)
                    elif self.flagged[r][c]:
                        btn.config(text="🚩", fg="#008000", bg="#d0d0d0")
                    else:
                        btn.config(text="💣", bg="#e0e0e0", relief=tk.SUNKEN)

                elif self.flagged[r][c]:
                    btn.config(text="✖", fg="#ff0000", bg="#e0e0e0", relief=tk.SUNKEN)

                if not self.revealed[r][c]:
                    btn.config(state=tk.DISABLED)

    def _show_board_after_win(self):
        for r, c in self.mines:
            self.flagged[r][c] = True
            self.buttons[r][c].config(
                text="🚩",
                fg="#008000",
                bg="#d0d0d0",
            )
        self._update_counters()

    # ------------------------------------------------------------------
    # Game end
    # ------------------------------------------------------------------

    def _lose(self):
        self.game_over = True
        self.win = False
        self.face.config(text="😵")
        self.status.config(text="Game over — you hit a mine. Click 😵 to play again.")
        self._show_board_after_loss()

    def _check_win(self):
        safe_cells = self.rows * self.cols - self.mine_count
        revealed_count = self._count_revealed()

        if revealed_count >= safe_cells:
            self.game_over = True
            self.win = True
            self.face.config(text="😎")
            self.status.config(
                text=(
                    f"You cleared the board in {self.elapsed} seconds! "
                    "Click 😎 for a new game."
                )
            )
            self._show_board_after_win()


def _csv_float(value):
    if value is None:
        return ""
    return round(float(value), 6)


def main():
    root = tk.Tk()
    MinesweeperGUI(
        root,
        rows=16,
        cols=16,
        mines=40,
        seed=None,
        csv_filename="human_gameplay.csv",
        decisions_filename="human_decisions.csv",
    )
    root.mainloop()


if __name__ == "__main__":
    main()
