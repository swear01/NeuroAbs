import argparse
import hashlib
import json
import os
import sys


def prime_lhs(node, width_map):
    if node[0] in {"CONTINUOUS_ASSIGN", "BLOCKING_ASSIGN"}:
        lhs = node[1]
        name = lhs[1]
        next_name = f"__next__{name}"
        width_map[next_name] = width_map[name]
        return (node[0], ("ID", next_name), node[2])
    if node[0] == "CONDITION":
        return (node[0], node[1], prime_lhs(node[2], width_map))
    raise RuntimeError(f"Unexpected statement node: {node[0]}")


def classify(parser, original, abstract, width_map):
    from check import preprocess_string
    from z3 import Exists, Implies, Not, Solver, sat, unsat
    from z3_gen import build_smt_formula

    original_widths = width_map.copy()
    abstract_widths = width_map.copy()
    original_ast = prime_lhs(parser.parse(preprocess_string(original)), original_widths)
    abstract_ast = prime_lhs(parser.parse(preprocess_string(abstract)), abstract_widths)
    original_formula, _, original_unknowns, _ = build_smt_formula(
        original_ast, original_widths, True
    )
    abstract_formula, _, abstract_unknowns, _ = build_smt_formula(
        abstract_ast, abstract_widths, False
    )
    if original_unknowns:
        raise RuntimeError("Original statement unexpectedly contains an X value")

    abstract_relation = (
        Exists(list(abstract_unknowns), abstract_formula)
        if abstract_unknowns
        else abstract_formula
    )
    forward_solver = Solver()
    forward_solver.add(Not(Implies(original_formula, abstract_relation)))
    forward = forward_solver.check()

    strict_solver = Solver()
    strict_solver.add(abstract_formula, Not(original_formula))
    reverse_counterexample = strict_solver.check()
    if (forward != sat and forward != unsat) or (
        reverse_counterexample != sat and reverse_counterexample != unsat
    ):
        raise RuntimeError("Z3 returned unknown")
    return str(forward), str(reverse_counterexample)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--rtl", required=True)
    parser.add_argument("--top", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    sys.path.insert(0, os.path.join(args.project, "Pyverilog_NeuroAbs"))
    sys.path.insert(0, os.path.join(args.project, "src"))
    from check import VerilogAssignParser
    from example_dataflow_analyzer import lineno_extractor

    statement_parser = VerilogAssignParser(debug=False)
    _, width_map, _, _ = lineno_extractor(args.rtl, args.top)
    assert classify(statement_parser, "q <= q;", "q <= 'bx;", {"q": 1}) == (
        "unsat",
        "sat",
    )
    assert classify(statement_parser, "q <= q;", "q <= q;", {"q": 1}) == (
        "unsat",
        "unsat",
    )

    with open(args.results, encoding="utf-8") as source:
        lines = source.read().splitlines()
    if len(lines) % 3:
        raise RuntimeError(f"Expected three lines per result, got {len(lines)}")

    records = []
    for offset in range(0, len(lines), 3):
        original, abstract, logged_soundness = lines[offset : offset + 3]
        forward, reverse_counterexample = classify(
            statement_parser, original, abstract, width_map
        )
        records.append(
            {
                "request": offset // 3 + 1,
                "original": original,
                "abstract": abstract,
                "logged_soundness": logged_soundness,
                "forward_check": forward,
                "reverse_counterexample": reverse_counterexample,
                "sound": forward == "unsat",
                "strict": forward == "unsat" and reverse_counterexample == "sat",
                "equivalent": forward == "unsat"
                and reverse_counterexample == "unsat",
            }
        )

    summary = {
        "total": len(records),
        "logged_unsat": sum(row["logged_soundness"] == "unsat" for row in records),
        "sound": sum(row["sound"] for row in records),
        "strict": sum(row["strict"] for row in records),
        "equivalent": sum(row["equivalent"] for row in records),
        "invalid": sum(not row["sound"] for row in records),
        "equivalent_requests": [
            row["request"] for row in records if row["equivalent"]
        ],
    }
    encoded = (json.dumps({"summary": summary, "records": records}, indent=2) + "\n").encode()
    with open(args.output, "wb") as destination:
        destination.write(encoded)
    summary["report_sha256"] = hashlib.sha256(encoded).hexdigest()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
