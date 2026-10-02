"""A self-contained local SAT solver.

Implements the DPLL algorithm with unit propagation, pure literal
elimination and an occurrence-count branching heuristic. No external
SAT libraries or services are used; only the Python standard library.

Clause semantics (deterministic):
  - Empty formula (no clauses)        -> SAT, empty (freely extendable) model
  - Empty clause                      -> the formula is UNSAT
  - Duplicate literals in a clause    -> deduplicated
  - Tautological clause (x and -x)    -> always true, dropped
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field


class DimacsError(ValueError):
    """Raised when a DIMACS CNF input is malformed."""


@dataclass
class CNFFormula:
    """A parsed CNF formula.

    num_vars: declared number of variables (variables are 1..num_vars)
    clauses:  list of clauses; each clause is a tuple of non-zero ints
              (deduplicated, tautologies removed)
    """

    num_vars: int
    clauses: list


def parse_dimacs(text: str) -> CNFFormula:
    """Parse DIMACS CNF text with strict validation.

    Enforces:
      - exactly one ``p cnf <nvars> <nclauses>`` header before any clause
      - every literal is an integer in [-nvars, nvars] excluding 0
      - every clause is terminated by a single 0
      - the number of clauses matches the header exactly
      - nothing (except comment lines and an optional '%' end marker)
        may follow the last clause
    """
    num_vars = None
    expected_clauses = None
    clauses = []
    current = []
    seen_header = False
    saw_end_marker = False

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if saw_end_marker:
            if line.startswith("c"):
                continue
            raise DimacsError(
                f"line {lineno}: content found after '%' end marker"
            )
        if line.startswith("c"):
            continue
        if line.startswith("p"):
            if seen_header:
                raise DimacsError(f"line {lineno}: duplicate problem line")
            parts = line.split()
            if len(parts) != 4 or parts[1] != "cnf":
                raise DimacsError(
                    f"line {lineno}: malformed problem line, "
                    "expected 'p cnf <nvars> <nclauses>'"
                )
            try:
                num_vars = int(parts[2])
                expected_clauses = int(parts[3])
            except ValueError:
                raise DimacsError(
                    f"line {lineno}: nvars/nclauses must be integers"
                ) from None
            if num_vars < 0 or expected_clauses < 0:
                raise DimacsError(
                    f"line {lineno}: nvars/nclauses must be non-negative"
                )
            seen_header = True
            continue
        if line.startswith("%"):
            if not seen_header:
                raise DimacsError(
                    f"line {lineno}: '%' end marker before problem line"
                )
            if current:
                raise DimacsError(
                    f"line {lineno}: '%' end marker inside an "
                    "unterminated clause"
                )
            saw_end_marker = True
            continue
        if not seen_header:
            raise DimacsError(
                f"line {lineno}: clause data before problem line"
            )
        for token in line.split():
            try:
                lit = int(token)
            except ValueError:
                raise DimacsError(
                    f"line {lineno}: non-integer token {token!r}"
                ) from None
            if lit == 0:
                clauses.append(_normalize_clause(current))
                current = []
            else:
                if abs(lit) > num_vars:
                    raise DimacsError(
                        f"line {lineno}: literal {lit} exceeds declared "
                        f"variable count {num_vars}"
                    )
                current.append(lit)

    if not seen_header:
        raise DimacsError("missing problem line 'p cnf <nvars> <nclauses>'")
    if current:
        raise DimacsError("last clause is not terminated by 0")
    if len(clauses) != expected_clauses:
        raise DimacsError(
            f"header declares {expected_clauses} clause(s) but "
            f"{len(clauses)} were found"
        )
    return CNFFormula(num_vars=num_vars, clauses=clauses)


def _normalize_clause(literals):
    """Deduplicate literals; return None for tautological clauses."""
    seen = set()
    for lit in literals:
        if -lit in seen:
            return None  # tautology: clause is always satisfied
        seen.add(lit)
    return tuple(sorted(seen, key=abs))


@dataclass
class SolverStats:
    """Search statistics collected during DPLL."""

    propagations: int = 0  # forced assignments (unit + pure literal)
    decisions: int = 0     # branching variable guesses
    backtracks: int = 0    # failed branches undone


@dataclass
class SolveResult:
    satisfiable: bool
    model: dict = None  # var -> bool, complete when satisfiable
    stats: SolverStats = field(default_factory=SolverStats)


class DPLLSolver:
    """Recursive DPLL solver over a normalized clause set."""

    def __init__(self, num_vars: int, clauses):
        self.num_vars = num_vars
        # Drop tautologies (None) introduced by normalization.
        self.clauses = [c for c in clauses if c is not None]
        self.stats = SolverStats()

    def solve(self) -> SolveResult:
        assignment = {}
        sat = self._dpll(self.clauses, assignment)
        if not sat:
            return SolveResult(False, None, self.stats)
        # Extend to a complete model: variables not constrained by the
        # formula may take any value; default them to True.
        model = {v: assignment.get(v, True) for v in range(1, self.num_vars + 1)}
        return SolveResult(True, model, self.stats)

    # -- core search ----------------------------------------------------

    def _dpll(self, clauses, assignment) -> bool:
        # Unit propagation.
        clauses, conflict = self._propagate_units(clauses, assignment)
        if conflict:
            return False
        # Pure literal elimination.
        clauses = self._eliminate_pure_literals(clauses, assignment)
        if not clauses:
            return True

        var = self._choose_variable(clauses, assignment)
        for value in (True, False):
            assignment[var] = value
            self.stats.decisions += 1
            simplified = self._simplify(clauses, var, value)
            if self._dpll(simplified, assignment):
                return True
            # Undo the failed branch and every assignment it forced.
            self.stats.backtracks += 1
            self._unassign_descendants(assignment, var)
        del assignment[var]
        return False

    def _propagate_units(self, clauses, assignment):
        """Assign unit clauses until fixpoint. Returns (clauses, conflict)."""
        while True:
            if any(len(c) == 0 for c in clauses):
                return clauses, True
            unit = None
            for clause in clauses:
                if len(clause) == 1:
                    unit = clause[0]
                    break
            if unit is None:
                return clauses, False
            var, value = abs(unit), unit > 0
            existing = assignment.get(var)
            if existing is not None and existing != value:
                return clauses, True
            if existing is None:
                assignment[var] = value
                self.stats.propagations += 1
            clauses = self._simplify(clauses, var, value)

    def _eliminate_pure_literals(self, clauses, assignment):
        """Assign literals that appear with only one polarity."""
        while clauses:
            polarity = {}
            for clause in clauses:
                for lit in clause:
                    polarity.setdefault(abs(lit), set()).add(lit > 0)
            pure = None
            for var, signs in polarity.items():
                if len(signs) == 1 and var not in assignment:
                    pure = (var, signs.pop())
                    break
            if pure is None:
                return clauses
            var, value = pure
            assignment[var] = value
            self.stats.propagations += 1
            clauses = self._simplify(clauses, var, value)
        return clauses

    def _choose_variable(self, clauses, assignment) -> int:
        """Pick the unassigned variable occurring in the most clauses."""
        counts = {}
        for clause in clauses:
            for lit in clause:
                var = abs(lit)
                if var not in assignment:
                    counts[var] = counts.get(var, 0) + 1
        return max(counts, key=lambda v: (counts[v], -v))

    # -- helpers --------------------------------------------------------

    @staticmethod
    def _simplify(clauses, var, value):
        """Apply var=value: drop satisfied clauses, shorten others."""
        satisfied_lit = var if value else -var
        falsified_lit = -satisfied_lit
        new_clauses = []
        for clause in clauses:
            if satisfied_lit in clause:
                continue  # clause satisfied
            if falsified_lit in clause:
                new_clauses.append(tuple(l for l in clause if l != falsified_lit))
            else:
                new_clauses.append(clause)
        return new_clauses

    @staticmethod
    def _unassign_descendants(assignment, keep_var):
        """Remove assignments made after the decision on keep_var.

        Assignments are inserted in order, so everything inserted after
        keep_var belongs to the failed subtree. keep_var itself is
        removed by the caller when both branches fail.
        """
        keys = list(assignment)
        if keep_var not in assignment:
            return
        idx = keys.index(keep_var)
        for key in keys[idx + 1:]:
            del assignment[key]


def verify_model(clauses, model) -> bool:
    """Check that every (non-tautological) clause is satisfied by model."""
    for clause in clauses:
        if clause is None:
            continue
        if not any(model[abs(lit)] == (lit > 0) for lit in clause):
            return False
    return True


def solve_dimacs(text: str) -> SolveResult:
    """Convenience wrapper: parse DIMACS text and solve it."""
    formula = parse_dimacs(text)
    return DPLLSolver(formula.num_vars, formula.clauses).solve()


def main(argv) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <file.cnf>", file=sys.stderr)
        return 2
    try:
        with open(argv[1], "r", encoding="utf-8") as fh:
            formula = parse_dimacs(fh.read())
    except (OSError, DimacsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    result = DPLLSolver(formula.num_vars, formula.clauses).solve()
    if result.satisfiable:
        assert verify_model(formula.clauses, result.model)
        print("SAT")
        print(" ".join(
            str(v if val else -v) for v, val in sorted(result.model.items())
        ))
    else:
        print("UNSAT")
    stats = result.stats
    print(
        f"stats: propagations={stats.propagations} "
        f"decisions={stats.decisions} backtracks={stats.backtracks}"
    )
    return 0 if result.satisfiable else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
