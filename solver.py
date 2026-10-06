from __future__ import annotations

from math import comb
from typing import Dict, List, Optional, Set, Tuple


from minesweeper import Minesweeper


CellPos = Tuple[int, int]
Constraint = Tuple[Set[CellPos], int]


class MinesweeperSolver:
    """
    Player-view Minesweeper solver.

    Uses only information visible to the player:

        - revealed cells
        - revealed numbers
        - flags

    It does NOT use hidden mine information for reasoning.

    Features:
        - Direct constraint deduction
        - Subset constraint deduction
        - Guaranteed-safe detection
        - Guaranteed-mine detection
        - Exact probability estimation for manageable
          frontier components
    """

    def __init__(
        self,
        game: Minesweeper,
        max_component_cells: int = 20,
    ):
        self.game = game
        self.max_component_cells = max_component_cells

    # ==============================================================
    # NEIGHBORS
    # ==============================================================

    def _get_unknown_neighbors(
        self,
        row: int,
        col: int,
    ) -> Set[CellPos]:

        result = set()

        for nr, nc in self.game._neighbors(row, col):

            cell = self.game.board[nr][nc]

            if (
                not cell.revealed
                and not cell.flagged
            ):
                result.add((nr, nc))

        return result

    def _get_flagged_neighbors(
        self,
        row: int,
        col: int,
    ) -> int:

        return sum(
            1
            for nr, nc in self.game._neighbors(row, col)
            if self.game.board[nr][nc].flagged
        )

    # ==============================================================
    # BUILD VISIBLE CONSTRAINTS
    # ==============================================================

    def build_constraints(
        self,
    ) -> List[Constraint]:
        """
        Convert visible numbered cells into equations.

        Example:

            A + B + C = 1

        means exactly one of A, B, C is a mine.
        """

        constraints: List[Constraint] = []

        for row in range(self.game.rows):
            for col in range(self.game.cols):

                cell = self.game.board[row][col]

                if not cell.revealed:
                    continue

                unknown = self._get_unknown_neighbors(
                    row,
                    col,
                )

                if not unknown:
                    continue

                flagged = self._get_flagged_neighbors(
                    row,
                    col,
                )

                mines_required = (
                    cell.adjacent_mines - flagged
                )

                if (
                    0 <= mines_required
                    <= len(unknown)
                ):

                    constraints.append(
                        (
                            set(unknown),
                            mines_required,
                        )
                    )

        return constraints

    # ==============================================================
    # LOGICAL INFERENCE
    # ==============================================================

    def _infer(
        self,
        constraints: List[Constraint],
    ) -> Tuple[
        Set[CellPos],
        Set[CellPos],
    ]:
        """
        Infer guaranteed-safe and guaranteed-mine cells.

        Uses:

            1. Direct constraints
            2. Constraint subtraction / subset reasoning
        """

        working = [
            (
                set(cells),
                required,
            )
            for cells, required in constraints
        ]

        known_safe: Set[CellPos] = set()
        known_mines: Set[CellPos] = set()

        changed = True

        while changed:

            changed = False

            simplified: List[Constraint] = []

            # ------------------------------------------------------
            # Direct inference
            # ------------------------------------------------------

            for cells, required in working:

                # Remove cells already proven to be mines.
                known_mine_count = len(
                    cells & known_mines
                )

                required -= known_mine_count

                # Remove known cells.
                cells = cells - known_mines
                cells = cells - known_safe

                # Ignore contradictory constraints.
                if required < 0:
                    continue

                if required > len(cells):
                    continue

                # No mines remain.
                if required == 0:

                    before = len(
                        known_safe
                    )

                    known_safe.update(
                        cells
                    )

                    if len(known_safe) > before:
                        changed = True

                    continue

                # Every remaining cell is a mine.
                if required == len(cells):

                    before = len(
                        known_mines
                    )

                    known_mines.update(
                        cells
                    )

                    if len(known_mines) > before:
                        changed = True

                    continue

                if cells:

                    simplified.append(
                        (
                            set(cells),
                            required,
                        )
                    )

            # ------------------------------------------------------
            # Subset reasoning
            #
            # A + B = 1
            # A + B + C = 1
            #
            # therefore:
            #
            # C = 0
            # ------------------------------------------------------

            existing = {
                (
                    frozenset(cells),
                    required,
                )
                for cells, required
                in simplified
            }

            new_constraints = list(
                simplified
            )

            for i, (
                cells_a,
                required_a,
            ) in enumerate(
                simplified
            ):

                for j, (
                    cells_b,
                    required_b,
                ) in enumerate(
                    simplified
                ):

                    if i == j:
                        continue

                    if cells_a < cells_b:

                        difference = (
                            cells_b - cells_a
                        )

                        required_difference = (
                            required_b
                            - required_a
                        )

                        if (
                            difference
                            and
                            0 <= required_difference
                            <= len(difference)
                        ):

                            key = (
                                frozenset(
                                    difference
                                ),
                                required_difference,
                            )

                            if key not in existing:

                                new_constraints.append(
                                    (
                                        set(
                                            difference
                                        ),
                                        required_difference,
                                    )
                                )

                                existing.add(
                                    key
                                )

                                changed = True

            working = new_constraints

        return (
            known_safe,
            known_mines,
        )

    # ==============================================================
    # GUARANTEED SAFE
    # ==============================================================

    def find_guaranteed_safe_moves(
        self,
    ) -> Set[CellPos]:

        constraints = (
            self.build_constraints()
        )

        safe, _ = self._infer(
            constraints
        )

        return safe

    # ==============================================================
    # GUARANTEED MINES
    # ==============================================================

    def find_guaranteed_mines(
        self,
    ) -> Set[CellPos]:

        constraints = (
            self.build_constraints()
        )

        _, mines = self._infer(
            constraints
        )

        return mines

    # ==============================================================
    # FLAG GUARANTEED MINES
    # ==============================================================

    def flag_guaranteed_mines(
        self,
    ) -> Set[CellPos]:

        mines = (
            self.find_guaranteed_mines()
        )

        newly_flagged = set()

        for row, col in mines:

            cell = self.game.board[
                row
            ][
                col
            ]

            if (
                not cell.revealed
                and not cell.flagged
            ):

                self.game.flag(
                    row,
                    col,
                )

                newly_flagged.add(
                    (
                        row,
                        col,
                    )
                )

        return newly_flagged

    # ==============================================================
    # SAFE CANDIDATES
    # ==============================================================

    def get_candidate_moves(
        self,
    ) -> List[CellPos]:

        safe = (
            self.find_guaranteed_safe_moves()
        )

        candidates = [
            (
                row,
                col,
            )
            for row, col in safe
            if (
                not self.game.board[row][col].revealed
                and not self.game.board[row][col].flagged
            )
        ]

        return sorted(
            candidates
        )

    # ==============================================================
    # FRONTIER
    # ==============================================================

    def get_frontier_cells(
        self,
    ) -> Set[CellPos]:

        constraints = (
            self.build_constraints()
        )

        frontier = set()

        for cells, _ in constraints:

            frontier.update(
                cells
            )

        return frontier

    # ==============================================================
    # COMPONENT DISCOVERY
    # ==============================================================

    def _find_components(
        self,
        constraints: List[Constraint],
    ) -> List[
        Tuple[
            Set[CellPos],
            List[Constraint],
        ]
    ]:

        if not constraints:
            return []

        graph = [
            set()
            for _ in range(
                len(constraints)
            )
        ]

        # Two constraints are connected when
        # they share at least one unknown cell.
        for i in range(
            len(constraints)
        ):

            cells_i = constraints[i][0]

            for j in range(
                i + 1,
                len(constraints),
            ):

                cells_j = constraints[j][0]

                if cells_i & cells_j:

                    graph[i].add(j)
                    graph[j].add(i)

        visited = set()
        components = []

        for start in range(
            len(constraints)
        ):

            if start in visited:
                continue

            stack = [start]
            visited.add(start)

            indices = []

            while stack:

                current = stack.pop()

                indices.append(
                    current
                )

                for nxt in graph[current]:

                    if nxt not in visited:

                        visited.add(
                            nxt
                        )

                        stack.append(
                            nxt
                        )

            component_constraints = [
                constraints[index]
                for index in indices
            ]

            component_cells = set()

            for cells, _ in (
                component_constraints
            ):

                component_cells.update(
                    cells
                )

            components.append(
                (
                    component_cells,
                    component_constraints,
                )
            )

        return components

    # ==============================================================
    # COMPONENT ENUMERATION
    # ==============================================================

    def _enumerate_component(
        self,
        cells: Set[CellPos],
        constraints: List[Constraint],
    ) -> Optional[Dict]:

        cell_list = sorted(
            cells
        )

        n = len(
            cell_list
        )

        if n == 0:
            return {
                "cells": [],
                "count_by_mines": [1],
                "mine_occurrence": [],
                "solution_count": 1,
            }

        if n > self.max_component_cells:

            return None

        cell_index = {
            cell: index
            for index, cell
            in enumerate(cell_list)
        }

        # ----------------------------------------------------------
        # Convert constraints into local integer indices.
        # ----------------------------------------------------------

        local_constraints = []

        for constraint_cells, required in constraints:

            indices = [
                cell_index[cell]
                for cell in constraint_cells
            ]

            local_constraints.append(
                (
                    indices,
                    required,
                )
            )

        # ----------------------------------------------------------
        # Constraint membership for every cell.
        # ----------------------------------------------------------

        cell_constraints = [
            []
            for _ in range(n)
        ]

        for ci, (
            indices,
            _,
        ) in enumerate(
            local_constraints
        ):

            for index in indices:

                cell_constraints[
                    index
                ].append(ci)

        # More constrained cells first.
        order = sorted(
            range(n),
            key=lambda index: len(
                cell_constraints[index]
            ),
            reverse=True,
        )

        assigned = [-1] * n

        assigned_mines = [
            0
            for _ in local_constraints
        ]

        assigned_count = [
            0
            for _ in local_constraints
        ]

        count_by_mines = [
            0
            for _ in range(
                n + 1
            )
        ]

        mine_occurrence = [
            [
                0
                for _ in range(
                    n + 1
                )
            ]
            for _ in range(n)
        ]

        solution_count = 0

        def assign_variable(
            variable: int,
            value: int,
        ) -> bool:

            for ci in (
                cell_constraints[
                    variable
                ]
            ):

                _, required = (
                    local_constraints[ci]
                )

                assigned_count[ci] += 1

                if value == 1:
                    assigned_mines[ci] += 1

                remaining = (
                    len(
                        local_constraints[ci][0]
                    )
                    - assigned_count[ci]
                )

                # Too many mines.
                if (
                    assigned_mines[ci]
                    > required
                ):

                    return False

                # Not enough cells left to reach
                # required number of mines.
                if (
                    assigned_mines[ci]
                    + remaining
                    < required
                ):

                    return False

            return True

        def undo_variable(
            variable: int,
            value: int,
        ):

            for ci in (
                cell_constraints[
                    variable
                ]
            ):

                assigned_count[ci] -= 1

                if value == 1:
                    assigned_mines[ci] -= 1

        def save_solution(
            total_mines: int,
        ):

            nonlocal solution_count

            solution_count += 1

            count_by_mines[
                total_mines
            ] += 1

            for index, value in enumerate(
                assigned
            ):

                if value == 1:

                    mine_occurrence[
                        index
                    ][
                        total_mines
                    ] += 1

        def search(
            position: int,
            total_mines: int,
        ):

            if position == n:

                save_solution(
                    total_mines
                )

                return

            variable = order[
                position
            ]

            # Try safe first.
            for value in (
                0,
                1,
            ):

                assigned[
                    variable
                ] = value

                valid = assign_variable(
                    variable,
                    value,
                )

                if valid:

                    search(
                        position + 1,
                        total_mines + value,
                    )

                undo_variable(
                    variable,
                    value,
                )

                assigned[
                    variable
                ] = -1

        search(
            0,
            0,
        )

        if solution_count == 0:

            return {
                "contradiction": True
            }

        return {
            "cells": cell_list,
            "count_by_mines": count_by_mines,
            "mine_occurrence": mine_occurrence,
            "solution_count": solution_count,
        }

    # ==============================================================
    # CONVOLUTION
    # ==============================================================

    @staticmethod
    def _convolve(
        a: List[int],
        b: List[int],
        maximum: int,
    ) -> List[int]:

        result = [
            0
            for _ in range(
                maximum + 1
            )
        ]

        for i, value_a in enumerate(a):

            if value_a == 0:
                continue

            for j, value_b in enumerate(b):

                if value_b == 0:
                    continue

                if i + j <= maximum:

                    result[
                        i + j
                    ] += (
                        value_a
                        * value_b
                    )

        return result

    # ==============================================================
    # PREPARE CONSTRAINTS FOR PROBABILITY CALCULATION
    # ==============================================================

    def _reduce_constraints_for_probability(
        self,
        constraints: List[Constraint],
        known_safe: Set[CellPos],
        known_mines: Set[CellPos],
    ) -> List[Constraint]:
        """
        Remove cells whose states are already known.

        This is the important correction that keeps the
        probability engine consistent with the logical solver.
        """

        reduced = []

        for cells, required in constraints:

            # Already-known mines contribute 1 each.
            known_mine_count = len(
                cells & known_mines
            )

            new_required = (
                required
                - known_mine_count
            )

            new_cells = (
                cells
                - known_safe
                - known_mines
            )

            if new_required < 0:
                continue

            if new_required > len(
                new_cells
            ):
                continue

            if not new_cells:
                continue

            reduced.append(
                (
                    new_cells,
                    new_required,
                )
            )

        return reduced

    # ==============================================================
    # EXACT PROBABILITIES
    # ==============================================================

    def compute_probabilities(
        self,
    ) -> Dict[CellPos, float]:
        """
        Estimate exact mine probabilities for manageable
        constraint components.

        Guaranteed-safe cells are explicitly assigned 0.0.

        Guaranteed-mine cells are explicitly assigned 1.0.
        """

        # ----------------------------------------------------------
        # First perform logical inference.
        # ----------------------------------------------------------

        base_constraints = (
            self.build_constraints()
        )

        known_safe, known_mines = (
            self._infer(
                base_constraints
            )
        )

        # ----------------------------------------------------------
        # Start with guaranteed values.
        # ----------------------------------------------------------

        probabilities: Dict[
            CellPos,
            float
        ] = {}

        for cell in known_safe:

            probabilities[
                cell
            ] = 0.0

        for cell in known_mines:

            probabilities[
                cell
            ] = 1.0

        # ----------------------------------------------------------
        # Visible hidden cells.
        # ----------------------------------------------------------

        hidden_cells = [
            (
                row,
                col,
            )
            for row in range(
                self.game.rows
            )
            for col in range(
                self.game.cols
            )
            if (
                not self.game.board[
                    row
                ][
                    col
                ].revealed
                and
                not self.game.board[
                    row
                ][
                    col
                ].flagged
            )
        ]

        if not hidden_cells:
            return probabilities

        flagged_mines = sum(
            1
            for row in range(
                self.game.rows
            )
            for col in range(
                self.game.cols
            )
            if self.game.board[
                row
            ][
                col
            ].flagged
        )

        remaining_mines = (
            self.game.mine_count
            - flagged_mines
        )

        if (
            remaining_mines < 0
            or
            remaining_mines > len(
                hidden_cells
            )
        ):

            return probabilities

        # ----------------------------------------------------------
        # Reduce constraints using logical deductions.
        # ----------------------------------------------------------

        constraints = (
            self._reduce_constraints_for_probability(
                base_constraints,
                known_safe,
                known_mines,
            )
        )

        components = (
            self._find_components(
                constraints
            )
        )

        # ----------------------------------------------------------
        # Enumerate components.
        # ----------------------------------------------------------

        component_stats = []

        frontier = set()

        for cells, component_constraints in (
            components
        ):

            frontier.update(
                cells
            )

            stats = (
                self._enumerate_component(
                    cells,
                    component_constraints,
                )
            )

            if stats is None:

                # Exact enumeration is intentionally
                # disabled for large components.
                return probabilities

            if stats.get(
                "contradiction",
                False,
            ):

                return probabilities

            component_stats.append(
                stats
            )

        # ----------------------------------------------------------
        # Cells not in any unresolved frontier component.
        #
        # Known-safe cells MUST be excluded here.
        # ----------------------------------------------------------

        outside_cells = [
            cell
            for cell in hidden_cells
            if (
                cell not in frontier
                and cell not in known_safe
            )
        ]

        outside_distribution = [
            0
            for _ in range(
                min(
                    remaining_mines,
                    len(outside_cells),
                )
                + 1
            )
        ]

        for mine_count in range(
            len(
                outside_distribution
            )
        ):

            if (
                0 <= mine_count
                <= len(outside_cells)
                and
                mine_count
                <= remaining_mines
            ):

                outside_distribution[
                    mine_count
                ] = comb(
                    len(outside_cells),
                    mine_count,
                )

        # ----------------------------------------------------------
        # Combine component mine-count distributions.
        # ----------------------------------------------------------

        component_dp = [
            0
            for _ in range(
                remaining_mines + 1
            )
        ]

        component_dp[0] = 1

        for stats in component_stats:

            component_dp = (
                self._convolve(
                    component_dp,
                    stats[
                        "count_by_mines"
                    ],
                    remaining_mines,
                )
            )

        total_distribution = (
            self._convolve(
                component_dp,
                outside_distribution,
                remaining_mines,
            )
        )

        total_models = (
            total_distribution[
                remaining_mines
            ]
            if (
                remaining_mines
                < len(
                    total_distribution
                )
            )
            else 0
        )

        if total_models == 0:

            # We still retain guaranteed 0/1 values.
            return probabilities

        # ----------------------------------------------------------
        # Prefix / suffix distributions.
        # ----------------------------------------------------------

        component_count = len(
            component_stats
        )

        prefix = [
            None
            for _ in range(
                component_count + 1
            )
        ]

        suffix = [
            None
            for _ in range(
                component_count + 1
            )
        ]

        prefix[0] = (
            [1]
            + [
                0
                for _ in range(
                    remaining_mines
                )
            ]
        )

        for i in range(
            component_count
        ):

            prefix[i + 1] = (
                self._convolve(
                    prefix[i],
                    component_stats[i][
                        "count_by_mines"
                    ],
                    remaining_mines,
                )
            )

        suffix[
            component_count
        ] = (
            [1]
            + [
                0
                for _ in range(
                    remaining_mines
                )
            ]
        )

        for i in range(
            component_count - 1,
            -1,
            -1,
        ):

            suffix[i] = (
                self._convolve(
                    component_stats[i][
                        "count_by_mines"
                    ],
                    suffix[i + 1],
                    remaining_mines,
                )
            )

        # ----------------------------------------------------------
        # Frontier-cell probabilities.
        # ----------------------------------------------------------

        for component_index, stats in (
            enumerate(
                component_stats
            )
        ):

            context = (
                self._convolve(
                    prefix[
                        component_index
                    ],
                    suffix[
                        component_index + 1
                    ],
                    remaining_mines,
                )
            )

            context = (
                self._convolve(
                    context,
                    outside_distribution,
                    remaining_mines,
                )
            )

            cells = stats[
                "cells"
            ]

            occurrence = stats[
                "mine_occurrence"
            ]

            for local_index, cell in enumerate(
                cells
            ):

                numerator = 0

                for component_mines, ways in (
                    enumerate(
                        occurrence[
                            local_index
                        ]
                    )
                ):

                    if ways == 0:
                        continue

                    remaining_for_context = (
                        remaining_mines
                        - component_mines
                    )

                    if (
                        0 <= remaining_for_context
                        < len(context)
                    ):

                        numerator += (
                            ways
                            * context[
                                remaining_for_context
                            ]
                        )

                probabilities[
                    cell
                ] = (
                    numerator
                    / total_models
                )

        # ----------------------------------------------------------
        # Outside probability.
        #
        # All unresolved outside cells are exchangeable.
        # ----------------------------------------------------------

        if outside_cells:

            expected_outside_mines = 0

            for outside_mines, outside_ways in (
                enumerate(
                    outside_distribution
                )
            ):

                if outside_ways == 0:
                    continue

                component_mines = (
                    remaining_mines
                    - outside_mines
                )

                if (
                    0 <= component_mines
                    < len(component_dp)
                ):

                    expected_outside_mines += (
                        outside_mines
                        * outside_ways
                        * component_dp[
                            component_mines
                        ]
                    )

            outside_probability = (
                expected_outside_mines
                /
                (
                    total_models
                    * len(
                        outside_cells
                    )
                )
            )

            for cell in outside_cells:

                probabilities[
                    cell
                ] = outside_probability

        # ----------------------------------------------------------
        # Final consistency enforcement.
        # ----------------------------------------------------------

        for cell in known_safe:

            probabilities[
                cell
            ] = 0.0

        for cell in known_mines:

            probabilities[
                cell
            ] = 1.0

        return probabilities

    # ==============================================================
    # RISK API
    # ==============================================================

    def get_move_risks(
        self,
    ) -> Dict[CellPos, float]:

        return self.compute_probabilities()

    def get_best_guess(
        self,
    ) -> Optional[
        Tuple[
            CellPos,
            float,
        ]
    ]:

        probabilities = (
            self.compute_probabilities()
        )

        if not probabilities:
            return None

        candidates = [
            (
                cell,
                probability,
            )
            for cell, probability
            in probabilities.items()
            if (
                not self.game.board[
                    cell[0]
                ][
                    cell[1]
                ].revealed
                and
                not self.game.board[
                    cell[0]
                ][
                    cell[1]
                ].flagged
            )
        ]

        if not candidates:
            return None

        cell, probability = min(
            candidates,
            key=lambda item: (
                item[1],
                item[0],
            )
        )

        return (
            cell,
            probability,
        )

    # ==============================================================
    # REASONING STATE
    # ==============================================================

    def get_reasoning_state(
        self,
    ) -> Dict[str, object]:

        constraints = (
            self.build_constraints()
        )

        safe, mines = (
            self._infer(
                constraints
            )
        )

        probabilities = (
            self.compute_probabilities()
        )

        return {
            "constraint_count": len(
                constraints
            ),
            "safe_moves": sorted(
                safe
            ),
            "known_mines": sorted(
                mines
            ),
            "probabilities": probabilities,
        }

    # ==============================================================
    # DEBUG OUTPUT
    # ==============================================================

    def print_reasoning_state(
        self,
    ):

        state = (
            self.get_reasoning_state()
        )

        print("\nSolver reasoning")
        print("-" * 60)

        print(
            "Constraints:",
            state[
                "constraint_count"
            ],
        )

        print(
            "Guaranteed safe:",
            state[
                "safe_moves"
            ],
        )

        print(
            "Guaranteed mines:",
            state[
                "known_mines"
            ],
        )

        probabilities = state[
            "probabilities"
        ]

        if probabilities:

            print(
                "\nLowest-risk cells:"
            )

            ranked = sorted(
                probabilities.items(),
                key=lambda item: (
                    item[1],
                    item[0],
                ),
            )

            for cell, probability in (
                ranked[:15]
            ):

                print(
                    f"{cell} -> "
                    f"{probability * 100:.2f}% mine"
                )

        else:

            print(
                "\nProbability estimates "
                "unavailable."
            )

        print("-" * 60)