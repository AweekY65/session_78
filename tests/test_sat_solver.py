import itertools
import random
import unittest

from sat_solver import (
    CNF,
    DimacsError,
    DPLLSolver,
    parse_dimacs,
    solve_dimacs,
    verify_model,
)


def brute_force(num_vars, clauses):
    """Exhaustive oracle: first satisfying assignment over 1..num_vars, or None."""
    for values in itertools.product([False, True], repeat=num_vars):
        model = {i + 1: values[i] for i in range(num_vars)}
        if all(
            any(model[abs(lit)] == (lit > 0) for lit in clause)
            for clause in clauses
        ):
            return model
    return None


class TestDimacsParsing(unittest.TestCase):
    def test_basic_parse(self):
        cnf = parse_dimacs("c hello\np cnf 3 2\n1 -2 0\n2 3 0\n")
        self.assertEqual(cnf.num_vars, 3)
        self.assertEqual(cnf.clauses, [frozenset({1, -2}), frozenset({2, 3})])

    def test_multiline_clause_and_eof_marker(self):
        cnf = parse_dimacs("p cnf 2 1\n1\n-2\n0\n%\n")
        self.assertEqual(cnf.clauses, [frozenset({1, -2})])

    def test_duplicate_literals_collapsed(self):
        cnf = parse_dimacs("p cnf 2 1\n1 1 -2 -2 0\n")
        self.assertEqual(cnf.clauses, [frozenset({1, -2})])

    def test_tautology_clause_dropped(self):
        cnf = parse_dimacs("p cnf 2 2\n1 -1 0\n2 0\n")
        self.assertEqual(cnf.clauses, [frozenset({2})])

    def test_empty_formula(self):
        cnf = parse_dimacs("p cnf 3 0\n")
        self.assertEqual(cnf.clauses, [])
        sat, model = DPLLSolver(cnf).solve()
        self.assertTrue(sat)
        self.assertEqual(model, {1: False, 2: False, 3: False})

    def test_empty_clause_is_unsat(self):
        cnf = parse_dimacs("p cnf 2 1\n0\n")
        self.assertEqual(cnf.clauses, [frozenset()])
        sat, model = DPLLSolver(cnf).solve()
        self.assertFalse(sat)
        self.assertIsNone(model)

    def test_missing_header(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("1 0\n")

    def test_duplicate_header(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 1 0\np cnf 1 0\n")

    def test_bad_header_format(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p sat 1 0\n")
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 1\n")
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf x 1\n")

    def test_literal_out_of_range(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 2 1\n3 0\n")
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 2 1\n-3 0\n")

    def test_missing_clause_terminator(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 2 1\n1 -2\n")

    def test_clause_count_mismatch(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 2 2\n1 0\n")
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 2 1\n1 0\n2 0\n")

    def test_invalid_token(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 2 1\n1 a 0\n")

    def test_content_after_eof_marker(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 1 1\n1 0\n%\n1 0\n")

    def test_clause_before_header(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("1 0\np cnf 1 1\n")


class TestDPLL(unittest.TestCase):
    def solve(self, num_vars, clauses):
        cnf = CNF(num_vars, [frozenset(c) for c in clauses]).normalised()
        solver = DPLLSolver(cnf)
        sat, model = solver.solve()
        return cnf, solver, sat, model

    def test_simple_sat(self):
        cnf, solver, sat, model = self.solve(2, [{1, 2}, {-1, 2}])
        self.assertTrue(sat)
        self.assertTrue(model[2])
        self.assertTrue(verify_model(cnf, model))

    def test_simple_unsat(self):
        _, _, sat, model = self.solve(1, [{1}, {-1}])
        self.assertFalse(sat)
        self.assertIsNone(model)

    def test_unit_propagation_chain(self):
        # (1) & (-1 v 2) & (-2 v 3) forces 1, 2, 3 by propagation only.
        cnf, solver, sat, model = self.solve(3, [{1}, {-1, 2}, {-2, 3}])
        self.assertTrue(sat)
        self.assertEqual(model, {1: True, 2: True, 3: True})
        self.assertEqual(solver.stats.propagations, 3)
        self.assertEqual(solver.stats.decisions, 0)
        self.assertEqual(solver.stats.backtracks, 0)

    def test_pure_literal_elimination(self):
        # Variable 2 occurs only positively: no decision needed for it.
        cnf, solver, sat, model = self.solve(2, [{1, 2}, {-1, 2}])
        self.assertTrue(sat)
        self.assertTrue(model[2])
        self.assertGreaterEqual(solver.stats.pure_literals, 1)
        self.assertTrue(verify_model(cnf, model))

    def test_deep_backtracking(self):
        # Pigeonhole: 4 pigeons, 3 holes is UNSAT and forces deep search.
        pigeons, holes = 4, 3
        var = lambda p, h: p * holes + h + 1
        clauses = []
        for p in range(pigeons):
            clauses.append({var(p, h) for h in range(holes)})
        for h in range(holes):
            for p1 in range(pigeons):
                for p2 in range(p1 + 1, pigeons):
                    clauses.append({-var(p1, h), -var(p2, h)})
        cnf, solver, sat, _ = self.solve(pigeons * holes, clauses)
        self.assertFalse(sat)
        self.assertGreater(solver.stats.backtracks, 0)
        self.assertGreater(solver.stats.decisions, 0)

    def test_backtracking_finds_late_model(self):
        # Variable 1 scores highest but is False in every model, so the
        # first decision (1=True) conflicts and the solver must backtrack.
        clauses = [{-1, 2}, {-1, -2}, {1, 3}, {1, 2, 3}, {1, -3, 2}]
        cnf, solver, sat, model = self.solve(3, clauses)
        self.assertTrue(sat)
        self.assertFalse(model[1])
        self.assertGreaterEqual(solver.stats.backtracks, 1)
        self.assertTrue(verify_model(cnf, model))

    def test_stats_reported(self):
        _, solver, sat, _ = self.solve(3, [{1, -2}, {2, 3}, {-1, -3}])
        self.assertTrue(sat)
        for field in ("propagations", "decisions", "backtracks", "pure_literals"):
            self.assertGreaterEqual(getattr(solver.stats, field), 0)

    def test_model_is_complete(self):
        _, _, sat, model = self.solve(5, [{1}])
        self.assertTrue(sat)
        self.assertEqual(set(model), {1, 2, 3, 4, 5})


class TestRandomAgainstOracle(unittest.TestCase):
    def test_random_small_formulas(self):
        rng = random.Random(20261002)
        for trial in range(300):
            num_vars = rng.randint(1, 6)
            num_clauses = rng.randint(0, 12)
            clauses = []
            for _ in range(num_clauses):
                size = rng.randint(1, 3)
                clause = {
                    rng.choice((1, -1)) * rng.randint(1, num_vars)
                    for _ in range(size)
                }
                clauses.append(clause)
            cnf = CNF(num_vars, [frozenset(c) for c in clauses]).normalised()
            solver = DPLLSolver(cnf)
            sat, model = solver.solve()
            oracle = brute_force(num_vars, cnf.clauses)
            self.assertEqual(
                sat, oracle is not None, f"trial {trial}: {cnf.clauses}"
            )
            if sat:
                self.assertTrue(verify_model(cnf, model))


class TestEndToEnd(unittest.TestCase):
    def test_solve_dimacs_sat(self):
        text = "c demo\np cnf 3 2\n1 -2 0\n2 3 0\n%\n"
        cnf, sat, model, stats = solve_dimacs(text)
        self.assertTrue(sat)
        self.assertTrue(verify_model(cnf, model))

    def test_solve_dimacs_unsat(self):
        text = "p cnf 2 4\n1 2 0\n1 -2 0\n-1 2 0\n-1 -2 0\n"
        _, sat, model, _ = solve_dimacs(text)
        self.assertFalse(sat)
        self.assertIsNone(model)


if __name__ == "__main__":
    unittest.main()
