# Project Notes

- Every generative LLM backend must prepend `src/initial_context.txt` to the
  per-statement message. The examples and abstraction rules in that file are part
  of the NeuroAbs experiment prompt, not optional setup text. The
  `luna-decision` backend asks a keep-or-X question instead and uses
  `src/decision_context.txt`, because the generative output rules contradict
  its JSON answer format.
- Yosys 0.68 removed `abc -fast`; the Yosys changelog says to replace
  `abc -g AND -fast` with `aigmap`. It also turns `$display` into `$print`
  cells, which `write_aiger` rejects, and `write_aiger` rejects remaining X
  bits. The PicoRV32 constant-propagation template therefore deletes `$print`
  cells after `proc` and runs `setundef -anyseq` before writing AIGER, matching
  the BTOR2 `design.ys` flow.
- The PicoRV32 `picorv32_input.v` files already contain 21 `add_input*` ports.
  They replace X constants of upstream PicoRV32 (see the case's `picorv32.v`)
  and are equivalent under `setundef -anyseq`; they are not LLM abstractions.
- rIC3 1.5.2 (the latest crates.io release as of 2026-10-22) does not enforce
  `--time-limit` in portfolio mode: a 3600-second run on PicoRV32 ADD was still
  running after 69 minutes, and a 5-second limit was ignored. Enforce the cap
  outside rIC3 and kill the whole process group, as
  `src/run_decision_experiment.py` does; report such runs as `TIMEOUT`.
- `src/run_checker.py` calls `sys.exit()` from its timer thread and only
  terminates the direct child, so it neither stops the script nor reliably kills
  rIC3 workers at its cap.
- The opencode Go endpoint sits behind Cloudflare, which rejects Python's default
  `Python-urllib` User-Agent with HTTP 403 (error code 1010). Send an explicit
  User-Agent.
- The SMT statement checker cannot encode part-select or concatenation
  assignment targets, `|{...}` reductions, `$signed`, or statements that start
  with indented `if (...)`. On PicoRV32 ADD, 71 of the 232 all-X rewrites fail
  this way. The original `main.py` loop stopped on these exceptions; the Luna and
  all-X backends record them as `error` and keep the original statement.
- Keep the paper's checker experiments separate: RQ2 uses rIC3 portfolio formal
  proof with a 3600-second cap, while RQ3 uses kissat BMC depth exploration only
  when formal proof does not conclude. The paper concluded the I2C and PicoRV32
  cases in RQ2 and therefore omitted them from RQ3.
- Pono returning `unknown` after the CEGAR bound-25 query only means that query
  found no usable counterexample; it is not a property proof. A modern rIC3
  `UNSAT` result is the proof, and rIC3 reports that result with exit status 20.
- An `UNSAT` result for every forward statement implication proves sound OA only;
  it does not show that any rewrite is a useful abstraction. Apply the
  transition-aware strict-OA procedure in [`evaluation.md`](evaluation.md) and
  count semantic no-ops separately. In particular, X presence is not a valid
  substitute, and assignment targets must be modeled as next-state variables.
- Keep three abstraction counts separate: verification scenarios, checked LLM
  statement attempts, and effective final rewrite locations. In the Muse I2C
  artifact these are 1, 184, and 121 respectively. Identical statement strings
  currently collide in `update_statement_lineno`, so generated input count is
  not a reliable effective-abstraction count.
