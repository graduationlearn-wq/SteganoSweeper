from __future__ import annotations

from dataclasses import dataclass
import random
from typing import List, Tuple, Optional


@dataclass
class Cell:
    mine: bool = False
    revealed: bool = False
    flagged: bool = False
    adjacent_mines: int = 0


class Minesweeper:
    """
    Minesweeper game engine.

    The first click is guaranteed to be a zero-valued cell:
    the clicked cell and all of its neighbors are protected
    from mine placement.
    """

    def __init__(
        self,
        rows: int = 10,
        cols: int = 10,
        mines: int = 20,
        seed: Optional[int] = None,
    ):
        if rows <= 0 or cols <= 0:
            raise ValueError("Rows and columns must be positive.")

        if mines <= 0 or mines >= rows * cols:
            raise ValueError(
                "Mines must be between 1 and rows*cols - 1."
            )

        self.rows = rows
        self.cols = cols
        self.mine_count = mines

        self.rng = random.Random(seed)

        self.board: List[List[Cell]] = [
            [Cell() for _ in range(cols)]
            for _ in range(rows)
        ]

        self.mines_initialized = False
        self.game_over = False
        self.won = False

    # ---------------------------------------------------------------
    # NEIGHBORS
    # ---------------------------------------------------------------

    def _neighbors(self, row: int, col: int):
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):

                if dr == 0 and dc == 0:
                    continue

                nr = row + dr
                nc = col + dc

                if (
                    0 <= nr < self.rows
                    and 0 <= nc < self.cols
                ):
                    yield nr, nc

    # ---------------------------------------------------------------
    # MINE GENERATION
    # ---------------------------------------------------------------

    def _place_mines(
        self,
        first_row: int,
        first_col: int
    ):
        """
        Place mines while protecting the opening cell and
        all of its neighbors.

        This guarantees the first click has value 0.
        """

        protected = {
            (first_row, first_col)
        }

        protected.update(
            self._neighbors(first_row, first_col)
        )

        positions = [
            (r, c)
            for r in range(self.rows)
            for c in range(self.cols)
            if (r, c) not in protected
        ]

        if self.mine_count > len(positions):
            raise ValueError(
                "Too many mines for a guaranteed-zero opening."
            )

        mine_positions = self.rng.sample(
            positions,
            self.mine_count
        )

        for r, c in mine_positions:
            self.board[r][c].mine = True

        self._calculate_numbers()

        self.mines_initialized = True

    def _calculate_numbers(self):

        for r in range(self.rows):
            for c in range(self.cols):

                cell = self.board[r][c]

                if cell.mine:
                    continue

                cell.adjacent_mines = sum(
                    self.board[nr][nc].mine
                    for nr, nc in self._neighbors(r, c)
                )

    # ---------------------------------------------------------------
    # REVEAL
    # ---------------------------------------------------------------

    def reveal(
        self,
        row: int,
        col: int
    ) -> bool:

        if self.game_over:
            raise RuntimeError("Game is already over.")

        if not (
            0 <= row < self.rows
            and 0 <= col < self.cols
        ):
            raise ValueError("Invalid cell coordinates.")

        # First click initializes the board.
        if not self.mines_initialized:
            self._place_mines(row, col)

        cell = self.board[row][col]

        if cell.revealed or cell.flagged:
            return True

        if cell.mine:
            cell.revealed = True
            self.game_over = True
            self.won = False
            return False

        self._reveal_recursive(row, col)

        self._check_win()

        return True

    def _reveal_recursive(
        self,
        row: int,
        col: int
    ):

        cell = self.board[row][col]

        if cell.revealed:
            return

        if cell.flagged:
            return

        if cell.mine:
            return

        cell.revealed = True

        if cell.adjacent_mines == 0:

            for nr, nc in self._neighbors(row, col):
                self._reveal_recursive(nr, nc)

    # ---------------------------------------------------------------
    # FLAG
    # ---------------------------------------------------------------

    def flag(
        self,
        row: int,
        col: int
    ):

        if self.game_over:
            raise RuntimeError("Game is already over.")

        cell = self.board[row][col]

        if cell.revealed:
            return

        cell.flagged = not cell.flagged

    # ---------------------------------------------------------------
    # WIN
    # ---------------------------------------------------------------

    def _check_win(self):

        for r in range(self.rows):
            for c in range(self.cols):

                cell = self.board[r][c]

                if not cell.mine and not cell.revealed:
                    return

        self.game_over = True
        self.won = True

    # ---------------------------------------------------------------
    # DISPLAY
    # ---------------------------------------------------------------

    def display(
        self,
        reveal_mines: bool = False
    ):

        for r in range(self.rows):

            row_values = []

            for c in range(self.cols):

                cell = self.board[r][c]

                if reveal_mines and cell.mine:
                    value = "*"

                elif cell.flagged:
                    value = "F"

                elif not cell.revealed:
                    value = "#"

                elif cell.adjacent_mines == 0:
                    value = " "

                else:
                    value = str(cell.adjacent_mines)

                row_values.append(value)

            print(" | ".join(row_values))

        print()