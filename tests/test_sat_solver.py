import itertools
import random
import unittest

from sat_solver import (
    CNFFormula,
    DimacsError,
    DPLLSolver,
    parse_dimacs,
    solve_dimacs,
    verify_model,
)


def brute_force_sat(num_vars, clauses):
    """Exhaustive oracle: try all 2^n assignments."""
    real_clauses = [c for c in clauses if c is not None]
    for values in itertools.product([False, True], repeat=num_vars):
        model = {v + 1: values[v] for v in range(num_vars)}
        if verify_model(real_clauses, model):
            return True
    return False


class TestDimacsParsing(unittest.TestCase):
    def test_basic_parse(self):
        formula = parse_dimacs("c comment\np cnf 3 2\n1 -2 0\n3 0\n")
        self.assertEqual(formula.num_vars, 3)
        self.assertEqual(formula.clauses, [(1, -2), (3,)])

    def test_clause_spanning_lines_and_multiple_per_line(self):
        formula = parse_dimacs("p cnf 2 2\n1\n2 0 -1\n-2 0\n")
        self.assertEqual(formula.clauses, [(1, 2), (-1, -2)])

    def test_duplicate_literals_deduplicated(self):
        formula = parse_dimacs("p cnf 2 1\n1 1 -2 -2 0\n")
        self.assertEqual(formula.clauses, [(1, -2)])

    def test_tautology_becomes_none(self):
        formula = parse_dimacs("p cnf 2 2\n1 -1 0\n2 0\n")
        self.assertEqual(formula.clauses, [None, (2,)])

    def test_empty_clause(self):
        formula = parse_dimacs("p cnf 1 1\n0\n")
        self.assertEqual(formula.clauses, [()])

    def test_empty_formula(self):
        formula = parse_dimacs("p cnf 5 0\n")
        self.assertEqual(formula.clauses, [])

    def test_optional_percent_end_marker(self):
        formula = parse_dimacs("p cnf 1 1\n1 0\n%\nc trailing comment\n")
        self.assertEqual(formula.clauses, [(1,)])

    def test_missing_header(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("1 0\n")

    def test_duplicate_header(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 1 0\np cnf 1 0\n")

    def test_malformed_header(self):
        for bad in ("p cnf 1\n", "p sat 1 1\n", "p cnf x 1\n", "p cnf -1 0\n"):
            with self.assertRaises(DimacsError, msg=bad):
                parse_dimacs(bad)

    def test_literal_out_of_range(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 2 1\n3 0\n")

    def test_non_integer_token(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 2 1\n1 a 0\n")

    def test_unterminated_clause(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 2 1\n1 2\n")

    def test_clause_count_mismatch(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 2 2\n1 0\n")
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 2 1\n1 0\n2 0\n")

    def test_content_after_end_marker(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 1 1\n1 0\n%\n2 0\n")

    def test_end_marker_inside_clause(self):
        with self.assertRaises(DimacsError):
            parse_dimacs("p cnf 2 1\n1 %\n")


class TestSemantics(unittest.TestCase):
    def test_empty_formula_is_sat(self):
        result = solve_dimacs("p cnf 3 0\n")
        self.assertTrue(result.satisfiable)
        self.assertEqual(set(result.model), {1, 2, 3})

    def test_empty_clause_is_unsat(self):
        result = solve_dimacs("p cnf 2 1\n0\n")
        self.assertFalse(result.satisfiable)
        self.assertIsNone(result.model)

    def test_tautology_clause_dropped(self):
        result = solve_dimacs("p cnf 1 1\n1 -1 0\n")
        self.assertTrue(result.satisfiable)

    def test_duplicate_literals(self):
        result = solve_dimacs("p cnf 1 2\n1 1 1 0\n-1 -1 0\n")
        self.assertFalse(result.satisfiable)


class TestDPLL(unittest.TestCase):
    def solve(self, num_vars, clauses):
        return DPLLSolver(num_vars, clauses).solve()

    def test_simple_sat(self):
        result = solve_dimacs("p cnf 3 2\n1 -2 0\n2 3 0\n")
        self.assertTrue(result.satisfiable)
        self.assertEqual(len(result.model), 3)
        formula = parse_dimacs("p cnf 3 2\n1 -2 0\n2 3 0\n")
        self.assertTrue(verify_model(formula.clauses, result.model))

    def test_simple_unsat(self):
        result = solve_dimacs("p cnf 1 2\n1 0\n-1 0\n")
        self.assertFalse(result.satisfiable)

    def test_unit_propagation_chain(self):
        # (x1) & (~x1 v x2) & (~x2 v x3) forces x1=x2=x3=True.
        result = solve_dimacs("p cnf 3 3\n1 0\n-1 2 0\n-2 3 0\n")
        self.assertTrue(result.satisfiable)
        self.assertEqual(result.model, {1: True, 2: True, 3: True})
        self.assertGreaterEqual(result.stats.propagations, 3)
        self.assertEqual(result.stats.decisions, 0)

    def test_pure_literal_elimination(self):
        # x2 occurs only positively; no decisions should be needed.
        result = solve_dimacs("p cnf 2 2\n1 2 0\n-1 2 0\n")
        self.assertTrue(result.satisfiable)
        self.assertTrue(result.model[2])
        self.assertEqual(result.stats.decisions, 0)
        self.assertGreaterEqual(result.stats.propagations, 1)

    def test_deep_backtracking_unsat(self):
        # Pigeonhole: 4 pigeons, 3 holes -> UNSAT, forces real search.
        pigeons, holes = 4, 3
        clauses = []
        var = lambda p, h: p * holes + h + 1
        for p in range(pigeons):
            clauses.append(tuple(var(p, h) for h in range(holes)))
        for h in range(holes):
            for p1 in range(pigeons):
                for p2 in range(p1 + 1, pigeons):
                    clauses.append((-var(p1, h), -var(p2, h)))
        result = self.solve(pigeons * holes, clauses)
        self.assertFalse(result.satisfiable)
        self.assertGreater(result.stats.backtracks, 0)
        self.assertGreater(result.stats.decisions, 0)

    def test_backtracking_finds_late_model(self):
        # First branch choices fail; solver must backtrack to find SAT.
        clauses = [(-1, -2), (-1, 2), (1, -2, -3), (1, -2, 3), (2, 3)]
        result = self.solve(3, clauses)
        expected = brute_force_sat(3, clauses)
        self.assertEqual(result.satisfiable, expected)
        if result.satisfiable:
            self.assertTrue(verify_model(clauses, result.model))

    def test_stats_fields(self):
        result = solve_dimacs("p cnf 2 2\n1 2 0\n-1 0\n")
        for field_name in ("propagations", "decisions", "backtracks"):
            self.assertGreaterEqual(getattr(result.stats, field_name), 0)

    def test_model_is_complete(self):
        # Variable 3 never appears; model must still assign it.
        result = solve_dimacs("p cnf 3 1\n1 0\n")
        self.assertTrue(result.satisfiable)
        self.assertEqual(set(result.model), {1, 2, 3})


class TestRandomFormulasAgainstOracle(unittest.TestCase):
    def test_random_small_formulas(self):
        rng = random.Random(20261002)
        for trial in range(300):
            num_vars = rng.randint(1, 6)
            num_clauses = rng.randint(0, 10)
            clauses = []
            for _ in range(num_clauses):
                size = rng.randint(1, 3)
                clause = tuple(
                    rng.choice([-1, 1]) * rng.randint(1, num_vars)
                    for _ in range(size)
                )
                clauses.append(clause)
            # Normalize the same way the solver does.
            normalized = []
            for clause in clauses:
                seen = set()
                taut = False
                for lit in clause:
                    if -lit in seen:
                        taut = True
                        break
                    seen.add(lit)
                normalized.append(None if taut else tuple(seen))
            result = DPLLSolver(num_vars, normalized).solve()
            expected = brute_force_sat(num_vars, normalized)
            self.assertEqual(
                result.satisfiable, expected,
                msg=f"trial {trial}: vars={num_vars} clauses={clauses}",
            )
            if result.satisfiable:
                self.assertEqual(set(result.model), set(range(1, num_vars + 1)))
                self.assertTrue(verify_model(normalized, result.model))


if __name__ == "__main__":
    unittest.main()
