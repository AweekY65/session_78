"""A self-contained local SAT solver.

Implements the DPLL algorithm with unit propagation, pure literal
elimination and a frequency-based branching heuristic. No external
solver, service or network access is used anywhere: CNF inputs, solver
state, models and test data live only in local files or memory.

Usage:
    python3 -m sat_solver <file.cnf>
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field


class DimacsError(ValueError):
    """Raised when a DIMACS CNF input is malformed."""


@dataclass
class CNF:
    """A parsed and normalised CNF formula.

    Clauses are stored as frozensets of non-zero integers. A literal ``i``
    denotes variable ``i`` assigned True, ``-i`` denotes False.

    Normalisation semantics (deterministic):
      * duplicate literals inside a clause are collapsed;
      * tautological clauses (containing both ``x`` and ``-x``) are dropped;
      * an empty clause makes the formula trivially UNSAT;
      * an empty formula (no clauses) is trivially SAT.
    """

    num_vars: int
    clauses: list  # list[frozenset[int]]

    def normalised(self) -> "CNF":
        out = []
        for clause in self.clauses:
            if any(-lit in clause for lit in clause):
                continue  # tautology: always satisfied, drop it
            out.append(frozenset(clause))  # frozenset collapses duplicates
        return CNF(self.num_vars, out)


def parse_dimacs(text: str) -> CNF:
    """Parse DIMACS CNF text with strict validation.

    Enforces: exactly one ``p cnf <nvars> <nclauses>`` header before any
    clause, literals within ``1..nvars``, every clause terminated by ``0``,
    the actual clause count matching the header, and an optional ``%``
    end-of-file marker after which only whitespace may follow.
    """
    num_vars = None
    expected_clauses = None
    clauses: list = []
    current: list = []
    saw_eof_marker = False

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if saw_eof_marker:
            if line:
                raise DimacsError(
                    f"line {lineno}: content after '%' end-of-file marker"
                )
            continue
        if not line:
            continue
        if line.startswith("c"):
            continue  # comment line
        if line == "%":
            saw_eof_marker = True
            continue
        if line.startswith("p"):
            if num_vars is not None:
                raise DimacsError(f"line {lineno}: duplicate header line")
            if clauses or current:
                raise DimacsError(f"line {lineno}: header must precede clauses")
            parts = line.split()
            if len(parts) != 4 or parts[1] != "cnf":
                raise DimacsError(
                    f"line {lineno}: expected 'p cnf <nvars> <nclauses>'"
                )
            try:
                num_vars = int(parts[2])
                expected_clauses = int(parts[3])
            except ValueError:
                raise DimacsError(f"line {lineno}: non-integer header fields")
            if num_vars < 0 or expected_clauses < 0:
                raise DimacsError(f"line {lineno}: negative header fields")
            continue

        # Clause token line.
        if num_vars is None:
            raise DimacsError(f"line {lineno}: clause data before header")
        for token in line.split():
            try:
                lit = int(token)
            except ValueError:
                raise DimacsError(f"line {lineno}: invalid literal {token!r}")
            if lit == 0:
                clauses.append(frozenset(current))
                current = []
                continue
            if abs(lit) > num_vars:
                raise DimacsError(
                    f"line {lineno}: literal {lit} exceeds declared "
                    f"{num_vars} variables"
                )
            current.append(lit)

    if num_vars is None:
        raise DimacsError("missing 'p cnf' header")
    if current:
        raise DimacsError("file ended inside a clause: missing '0' terminator")
    if len(clauses) != expected_clauses:
        raise DimacsError(
            f"header declares {expected_clauses} clauses but "
            f"{len(clauses)} were found"
        )
    return CNF(num_vars, clauses).normalised()


@dataclass
class Stats:
    """Search statistics collected during a DPLL run."""

    propagations: int = 0  # forced assignments via unit propagation
    pure_literals: int = 0  # forced assignments via pure literal elimination
    decisions: int = 0  # branching variable guesses
    backtracks: int = 0  # failed branches that were undone


def _simplify(clauses, lit):
    """Assign literal ``lit`` True and simplify the clause set."""
    out = []
    neg = -lit
    for clause in clauses:
        if lit in clause:
            continue  # clause satisfied
        reduced = clause - {neg}
        out.append(frozenset(reduced) if len(reduced) != len(clause) else clause)
    return out


def _choose_variable(clauses):
    """Pick the variable with the most occurrences in the shortest clauses.

    This is a cheap dynamic-largest-individual-sum style heuristic: shorter
    clauses constrain the search more, so literals there weigh more.
    """
    scores = {}
    for clause in clauses:
        weight = 1.0 / len(clause)
        for lit in clause:
            scores[abs(lit)] = scores.get(abs(lit), 0.0) + weight
    return max(scores, key=scores.get)


class DPLLSolver:
    """Recursive DPLL solver over a normalised :class:`CNF`."""

    def __init__(self, cnf: CNF):
        self.cnf = cnf
        self.stats = Stats()

    def solve(self):
        """Return ``(sat, model)``.

        ``model`` maps every variable ``1..num_vars`` to a bool when SAT
        (unconstrained variables are assigned False, so the model is always
        complete), and is ``None`` when UNSAT.
        """
        assignment = {}
        result = self._dpll(list(self.cnf.clauses), assignment)
        if result is None:
            return False, None
        for var in range(1, self.cnf.num_vars + 1):
            result.setdefault(var, False)  # extend to a complete model
        return True, result

    def _dpll(self, clauses, assignment):
        while True:
            if any(len(c) == 0 for c in clauses):
                return None  # conflict: an empty clause was derived
            if not clauses:
                return assignment

            unit = next((c for c in clauses if len(c) == 1), None)
            if unit is not None:
                lit = next(iter(unit))
                assignment[abs(lit)] = lit > 0
                self.stats.propagations += 1
                clauses = _simplify(clauses, lit)
                continue

            polarity = {}
            for clause in clauses:
                for lit in clause:
                    polarity.setdefault(abs(lit), set()).add(lit > 0)
            pure = next(
                (v for v, signs in polarity.items() if len(signs) == 1), None
            )
            if pure is not None:
                sign = polarity[pure].pop()
                assignment[pure] = sign
                self.stats.pure_literals += 1
                clauses = _simplify(clauses, pure if sign else -pure)
                continue
            break

        var = _choose_variable(clauses)
        for value in (True, False):
            self.stats.decisions += 1
            branch = dict(assignment)
            branch[var] = value
            lit = var if value else -var
            result = self._dpll(_simplify(clauses, lit), branch)
            if result is not None:
                return result
            self.stats.backtracks += 1
        return None


def verify_model(cnf: CNF, model: dict) -> bool:
    """Check that ``model`` satisfies every clause of ``cnf``."""
    for clause in cnf.clauses:
        if not any(model.get(abs(lit), False) == (lit > 0) for lit in clause):
            return False
    return True


def solve_dimacs(text: str):
    """Convenience wrapper: parse, solve, verify. Returns (cnf, sat, model, stats)."""
    cnf = parse_dimacs(text)
    solver = DPLLSolver(cnf)
    sat, model = solver.solve()
    if sat:
        assert verify_model(cnf, model), "internal error: model failed verification"
    return cnf, sat, model, solver.stats


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("usage: python3 -m sat_solver <file.cnf>", file=sys.stderr)
        return 2
    with open(argv[0], "r", encoding="utf-8") as fh:
        text = fh.read()
    try:
        cnf, sat, model, stats = solve_dimacs(text)
    except DimacsError as exc:
        print(f"parse error: {exc}", file=sys.stderr)
        return 1

    print(f"vars={cnf.num_vars} clauses={len(cnf.clauses)}")
    if sat:
        print("SAT")
        print("model:", " ".join(f"{v}={int(model[v])}" for v in sorted(model)))
    else:
        print("UNSAT")
    print(
        f"stats: propagations={stats.propagations} "
        f"pure_literals={stats.pure_literals} "
        f"decisions={stats.decisions} backtracks={stats.backtracks}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
