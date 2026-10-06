import csv
import os
import random
import shutil
import time
import tkinter as tk
from datetime import datetime


class CSVGameplayLogger:
    """Append human gameplay actions to a CSV file.

    Only information visible/available to the human at decision time is
    recorded. Hidden mine positions are never written to the dataset.
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
        "hidden_neighbors_before",
        "frontier_score_before",
        "distance_from_last_action",
        "visible_board_before",
        "visible_board_after",
        "outcome",
        "game_status",
    ]

    def __init__(self, filename="human_gameplay.csv"):
        self.filename = os.path.abspath(filename)
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.game_counter = 0
        self.step = 0
        self.previous_action_time = None

        os.makedirs(os.path.dirname(self.filename) or ".", exist_ok=True)
        self._ensure_csv_schema()

    def _ensure_csv_schema(self):
        """Create the CSV or migrate the older 28-column version safely."""
        if not os.path.exists(self.filename) or os.path.getsize(self.filename) == 0:
            with open(self.filename, "w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=self.FIELDNAMES).writeheader()
            return

        try:
            with open(self.filename, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                old_fieldnames = reader.fieldnames or []
                rows = list(reader)

            if old_fieldnames == self.FIELDNAMES:
                return

            # Keep the old dataset. Add any new columns (currently "outcome")
            # as blank rather than inventing historical labels.
            backup = (
                os.path.splitext(self.filename)[0]
                + "_backup_"
                + datetime.now().strftime("%Y%m%d_%H%M%S")
                + ".csv"
            )
            shutil.copy2(self.filename, backup)

            with open(self.filename, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
                writer.writeheader()

                for old_row in rows:
                    new_row = {field: old_row.get(field, "") for field in self.FIELDNAMES}
                    writer.writerow(new_row)

            print(f"CSV schema updated. Backup created: {backup}")

        except (OSError, csv.Error) as exc:
            raise RuntimeError(f"Could not prepare CSV file: {exc}") from exc

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
        selected_features,
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

        delta = (
            ""
            if self.previous_action_time is None
            else round(now - self.previous_action_time, 4)
        )

        self.previous_action_time = now
        self.step += 1

        if game.game_over:
            status = "won" if game.win else "lost"
        else:
            status = "playing"

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
            "row": selected_features["row"],
            "col": selected_features["col"],
            "first_move": int(first_move),
            "revealed_before": revealed_before,
            "revealed_after": revealed_after,
            "flags_before": flags_before,
            "flags_after": flags_after,
            "remaining_mines_before": remaining_before,
            "remaining_mines_after": remaining_after,
            "adjacent_revealed_before": selected_features["adjacent_revealed"],
            "hidden_neighbors_before": selected_features["hidden_neighbors"],
            "frontier_score_before": round(
                selected_features["frontier_score"], 4
            ),
            "distance_from_last_action": round(
                selected_features["distance_from_last_action"], 4
            ),
            "visible_board_before": visible_before,
            "visible_board_after": visible_after,
            "outcome": outcome,
            "game_status": status,
        }

        with open(self.filename, "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=self.FIELDNAMES).writerow(row)


class MinesweeperGUI:
    """Clickable Minesweeper clone with automatic human-gameplay logging.

    Left click   : reveal cell
    Right click  : flag / unflag cell
    Double click : chord a revealed number

    Every genuine player action is appended to human_gameplay.csv.
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

    def __init__(
        self,
        root,
        rows=16,
        cols=16,
        mines=40,
        seed=None,
        csv_filename="human_gameplay.csv",
    ):
        self.root = root
        self.rows = rows
        self.cols = cols
        self.mine_count = mines
        self.seed = seed

        self.logger = CSVGameplayLogger(csv_filename)
        self.last_action_cell = None

        self.root.title("Minesweeper — Human Gameplay Data Collection")
        self.root.resizable(False, False)
        self.root.configure(bg="#c0c0c0")

        self.buttons = []
        self._build_ui()
        self.new_game()

    # -----------------------------------------------------------------
    # UI
    # -----------------------------------------------------------------

    def _build_ui(self):
        outer = tk.Frame(
            self.root,
            bg="#c0c0c0",
            bd=6,
            relief=tk.RAISED,
        )
        outer.pack(padx=8, pady=8)

        top = tk.Frame(
            outer,
            bg="#c0c0c0",
            bd=3,
            relief=tk.SUNKEN,
        )
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

        board_frame = tk.Frame(
            outer,
            bg="#808080",
            bd=3,
            relief=tk.SUNKEN,
        )
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

                btn.bind(
                    "<Button-1>",
                    lambda e, rr=r, cc=c: self.left_click(rr, cc),
                )
                btn.bind(
                    "<Button-3>",
                    lambda e, rr=r, cc=c: self.right_click(rr, cc),
                )
                btn.bind(
                    "<Double-Button-1>",
                    lambda e, rr=r, cc=c: self.chord(rr, cc),
                )

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
            text=f"Recording gameplay → {os.path.basename(self.logger.filename)}",
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
        if self.seed is None:
            self.current_seed = random.randrange(1, 2**31 - 1)
        else:
            self.current_seed = self.seed

        self.rng = random.Random(self.current_seed)

        self.mines = set()
        self.numbers = [
            [0 for _ in range(self.cols)]
            for _ in range(self.rows)
        ]
        self.revealed = [
            [False for _ in range(self.cols)]
            for _ in range(self.rows)
        ]
        self.flagged = [
            [False for _ in range(self.cols)]
            for _ in range(self.rows)
        ]

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
        self.status.config(
            text="Left click to reveal • Right click to flag"
        )

        self.logger.start_game()

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

    def _update_counters(self):
        flags = sum(
            self.flagged[r][c]
            for r in range(self.rows)
            for c in range(self.cols)
        )
        remaining = self.mine_count - flags
        self.mine_display.config(text=f"{remaining:03d}")

    def _update_timer(self):
        if self.start_time is not None and not self.game_over:
            self.elapsed = min(
                999,
                int(time.time() - self.start_time),
            )
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
        # First click and all surrounding cells are protected.
        protected = {(first_r, first_c)}
        protected.update(self._neighbors(first_r, first_c))

        available = [
            (r, c)
            for r in range(self.rows)
            for c in range(self.cols)
            if (r, c) not in protected
        ]

        if self.mine_count > len(available):
            raise ValueError(
                "Too many mines for this board size."
            )

        self.mines = set(
            self.rng.sample(available, self.mine_count)
        )

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
    # Dataset helpers
    # ------------------------------------------------------------------

    def _visible_board(self):
        """Serialize only the information currently visible to the human."""
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

    def _local_features(self, r, c):
        neighbors = list(self._neighbors(r, c))

        adjacent_revealed = sum(
            self.revealed[nr][nc]
            for nr, nc in neighbors
        )

        hidden_neighbors = sum(
            not self.revealed[nr][nc]
            and not self.flagged[nr][nc]
            for nr, nc in neighbors
        )

        frontier_score = (
            adjacent_revealed / max(1, len(neighbors))
        )

        if self.last_action_cell is None:
            distance = 0.0
        else:
            lr, lc = self.last_action_cell
            distance = (
                (r - lr) ** 2 + (c - lc) ** 2
            ) ** 0.5

        return {
            "row": r,
            "col": c,
            "adjacent_revealed": adjacent_revealed,
            "hidden_neighbors": hidden_neighbors,
            "frontier_score": frontier_score,
            "distance_from_last_action": distance,
        }

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
        if features is None:
            features = self._local_features(r, c)

        if visible_before is None:
            visible_before = self._visible_board()

        if flags_before is None:
            flags_before = self._count_flags()

        if remaining_before is None:
            remaining_before = self.mine_count - flags_before

        if revealed_before is None:
            revealed_before = self._count_revealed()

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
        if self.game_over:
            return

        if self.flagged[r][c] or self.revealed[r][c]:
            return

        # Capture the complete state BEFORE changing the board.
        visible_before = self._visible_board()
        flags_before = self._count_flags()
        remaining_before = self.mine_count - flags_before
        revealed_before = self._count_revealed()
        features = self._local_features(r, c)
        was_first_move = self.first_move

        # Mines are generated only after the first click, making that
        # first click guaranteed safe.
        if self.first_move:
            self._place_mines(r, c)
            self.first_move = False
            self.start_time = time.time()

        # --------------------------------------------------------------
        # Process the click BEFORE writing the CSV row.
        # This guarantees the CSV records the true outcome.
        # --------------------------------------------------------------

        if (r, c) in self.mines:
            self.revealed[r][c] = True
            self._reveal_mine_hit(r, c)
            self._lose()

            outcome = "mine_hit"

        else:
            self._reveal_from(r, c)
            self._check_win()

            outcome = (
                "safe_win"
                if self.game_over and self.win
                else "safe"
            )

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

    def right_click(self, r, c):
        if self.game_over or self.revealed[r][c]:
            return

        # We intentionally do not allow a flag before the first reveal,
        # matching the intended first-move-safe flow.
        if self.first_move:
            self.status.config(
                text="Reveal a cell first."
            )
            return

        visible_before = self._visible_board()
        flags_before = self._count_flags()
        remaining_before = self.mine_count - flags_before
        revealed_before = self._count_revealed()
        features = self._local_features(r, c)

        new_flag_state = not self.flagged[r][c]
        self.flagged[r][c] = new_flag_state

        self._render_cell(r, c)
        self._update_counters()

        outcome = (
            "flagged"
            if new_flag_state
            else "unflagged"
        )

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

        # Flags do not themselves win the game. Winning requires all safe
        # cells to be revealed.
        self._check_win()

    def chord(self, r, c):
        if (
            self.game_over
            or not self.revealed[r][c]
            or self.numbers[r][c] <= 0
        ):
            return

        neighbors = list(self._neighbors(r, c))

        flag_count = sum(
            self.flagged[nr][nc]
            for nr, nc in neighbors
        )

        if flag_count != self.numbers[r][c]:
            return

        # Chording produces real reveal actions. Each revealed cell is
        # tagged source="chord" so it can be separated during analysis.
        for nr, nc in neighbors:
            if (
                not self.flagged[nr][nc]
                and not self.revealed[nr][nc]
            ):
                self.left_click(
                    nr,
                    nc,
                    source="chord",
                )

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

            if (
                self.flagged[r][c]
                or self.revealed[r][c]
                or (r, c) in self.mines
            ):
                continue

            self.revealed[r][c] = True
            self._render_cell(r, c)

            if self.numbers[r][c] == 0:
                for nr, nc in self._neighbors(r, c):
                    if (
                        not self.revealed[nr][nc]
                        and not self.flagged[nr][nc]
                    ):
                        stack.append((nr, nc))

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_cell(self, r, c):
        btn = self.buttons[r][c]

        if self.flagged[r][c]:
            btn.config(
                text="🚩",
                fg="#d00000",
                bg="#c0c0c0",
                relief=tk.RAISED,
            )
            return

        if not self.revealed[r][c]:
            btn.config(
                text="",
                bg="#c0c0c0",
                relief=tk.RAISED,
            )
            return

        value = self.numbers[r][c]

        btn.config(
            relief=tk.SUNKEN,
            bd=1,
            bg="#d0d0d0",
        )

        if value == 0:
            btn.config(
                text="",
                fg="#000000",
            )
        elif value == -1:
            btn.config(
                text="💣",
                fg="#000000",
                bg="#ffb0b0",
            )
        else:
            btn.config(
                text=str(value),
                fg=self.NUMBER_COLORS.get(
                    value,
                    "#000000",
                ),
            )

    def _reveal_mine_hit(self, r, c):
        """Render and remember the mine that was actually clicked."""
        self._hit_mine = (r, c)
        btn = self.buttons[r][c]
        btn.config(
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
                        btn.config(
                            text="💣",
                            bg="#ff6666",
                            relief=tk.SUNKEN,
                        )
                    elif self.flagged[r][c]:
                        btn.config(
                            text="🚩",
                            fg="#008000",
                            bg="#d0d0d0",
                        )
                    else:
                        btn.config(
                            text="💣",
                            bg="#e0e0e0",
                            relief=tk.SUNKEN,
                        )

                elif self.flagged[r][c]:
                    # A flag placed on a non-mine is an incorrect flag.
                    btn.config(
                        text="✖",
                        fg="#ff0000",
                        bg="#e0e0e0",
                        relief=tk.SUNKEN,
                    )

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
        self.status.config(
            text="Game over — you hit a mine. Click 😵 to play again."
        )

        self._show_board_after_loss()

    def _check_win(self):
        safe_cells = (
            self.rows * self.cols
            - self.mine_count
        )

        revealed_count = self._count_revealed()

        if revealed_count >= safe_cells:
            self.game_over = True
            self.win = True

            self.face.config(text="😎")
            self.status.config(
                text=(
                    f"You cleared the board in "
                    f"{self.elapsed} seconds! "
                    f"Click 😎 for a new game."
                )
            )

            self._show_board_after_win()


def main():
    root = tk.Tk()

    MinesweeperGUI(
        root,
        rows=16,
        cols=16,
        mines=40,
        seed=None,
        csv_filename="human_gameplay.csv",
    )

    root.mainloop()


if __name__ == "__main__":
    main()
