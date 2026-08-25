# NeuroAbs evaluation requirements

Use all of the following gates before claiming that an LLM or an abstraction is
effective.

## Statement-level abstraction

Account for every requested rewrite: total responses, parse/API failures,
accepted sound rewrites, rejected rewrites, strict over-approximations, and
equivalent no-ops.

For an original statement relation `S` and an abstract relation `A`:

1. Sound OA: check `S AND NOT A`. `UNSAT` proves `S => A`.
2. Strict OA: after soundness passes, check `A AND NOT S`. `SAT` proves that the
   abstract relation admits at least one additional behavior. `UNSAT` means the
   rewrite is semantically equivalent under the encoding and must be counted as
   a no-op.

Model assignment targets as next-state variables (`V'`) while keeping right-hand
side references as current-state variables (`V`). Treat each X-value in `A` as
a fresh nondeterministic input. The current `check_implies()` implementation
does not distinguish `V'` from `V`, so calling it in reverse is not a valid
strict-OA test for nonblocking self-assignments such as `q <= q`.

Do not infer strictness from textual changes or the presence of X/free inputs.
Report the strict OA denominator, count, rate, and the request IDs and statements
for every equivalent no-op. The paper uses sound OA and strict OA as separate RQ1
metrics; see [Section 4.3](https://arxiv.org/html/2608.17304#S4.SS3).

## End-to-end verification

- Classify the final checker result as `SAT`, `UNSAT`, or `UNKNOWN`; never report
  `UNKNOWN` or completed bounded exploration as a proof.
- For RQ2, run a formal proof on both concrete and abstract models with the same
  checker, hardware, timeout, and repeated timing procedure.
- Use RQ3-style BMC only when formal proof does not conclude, and compare reached
  depth under the same time budget.
- Report LLM/AST/SMT construction time, CEGAR time, and final checker time
  separately. A sound or strict rewrite count alone does not demonstrate proof
  acceleration or end-to-end speedup.

Retain the original/abstract statement pairs, both SMT directions, commands,
logs, generated models, and SHA-256 hashes needed to reproduce each claim.
