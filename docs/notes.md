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
- Time with rIC3 master (`ric3 check --ui false model portfolio`), not 1.5.2:
  for `.btor`/`.btor2` input the 1.5.2 portfolio uses `wl_default`, which has no
  bit-level k-induction, and PicoRV32 B0 ADD and SLTI get no verdict within 30
  minutes. Master uses `bl_default` for every input format. Its exit status is 0
  for every verdict, so read `UNSAT`, `SAT` or `UNKNOWN` from the last output
  line.
- On the i9-14900K, an unpinned rIC3 portfolio spreads its workers over P- and
  E-cores, heats the package to 100 °C and throttles; repeated runs of one model
  differed by up to 1.95 times. Run one model at a time under
  `taskset -c 16-31` (the 16 E-cores): the spread drops to at most 1.07 times.
- The local DeepSeek gateway (`127.0.0.1:35001`) serves DeepSeek V4.1 Flash 1017
  only under `deepseek-v4.1-flash-1017`, routed solely to OpenRouter
  `deepseek/deepseek-v4.1-flash-1017` and billed to the OpenRouter account.
  Command Code cannot pin a snapshot (its `deepseek/deepseek-v4.1-flash` is
  undated), and the old `deepseek-v4-flash` alias, which fell back to
  `deepseek-v4-flash-0731`, is no longer allowed. The client still rejects any
  response whose `model` is not `deepseek/deepseek-v4.1-flash-1017`.
  `reasoning_effort` accepts `off` to `max`; with `off` the model ignores the
  answer-format instruction, and `thinking: disabled` is ignored.
- `src/run_checker.py` calls `sys.exit()` from its timer thread and only
  terminates the direct child, so it neither stops the script nor reliably kills
  rIC3 workers at its cap.
- The opencode Go endpoint sits behind Cloudflare, which rejects Python's default
  `Python-urllib` User-Agent with HTTP 403 (error code 1010). Send an explicit
  User-Agent. Its 429 responses carry `Retry-After`; the weekly Go limit asks
  for days, so the Luna client stops when the wait exceeds six hours instead of
  retrying.
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
  found no usable counterexample; it is not a property proof. An rIC3
  `UNSAT` result is the proof.
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
