# Manual case study: llmm-fifo_vis (issue #25)

Harness: `src/case_study.py` (split / abstract / check / cegar / refine / vacuity). Run on Mazu, 2026-10-29, work dir `/var/tmp/neuroabs-runtime/case-fifo-vis-20261029/`. Model under test: `deepseek/deepseek-v4.1-flash` through the local gateway (`call_deepseek`). Checker: rIC3 master 4d63899 `portfolio`, one run per piece, 2 runs at a time.

## Result

Property proved: all 8 pieces UNSAT, so `fifo_vis` is SAFE under the split (the split is SAT-coverage-checked, so the pieces together imply the original assertion).

| | Time |
|---|---|
| LLM (2 calls, sequential) | 80.7 s |
| rIC3, pass 1 (60 s cap, 8 pieces) | 60.0 s wall; 7 pieces proved in 0.0-1.2 s, c6 timed out |
| rIC3, pass 2 (c6 alone, 300 s cap) | 94.2 s |
| **End to end** | **about 235 s** |
| Baseline (rIC3 portfolio on the whole model) | about 199 s |

So the LLM-guided flow was **not faster** than the baseline here (about 1.2x slower). Seven of eight pieces are trivial. The hard work is piece c6 (both FIFOs non-empty, flags equal, data different, proved unreachable): the LLM left it concrete, and rIC3 needed 94 s on it, about half of the baseline. The 60 s first pass wasted 60 s on c6; going straight to 300 s would give about 175 s. The proof effort is therefore the data-equivalence invariant itself, which the class-A operators did not reduce.

## Per-step table

| Step | Proposals | Accepted | Rejected | LLM calls | Tokens in/out | LLM time | rIC3 |
|---|---|---|---|---|---|---|---|
| plan_split (round 1) | 8 cases | 8 (coverage SAT passed first try) | 0 | 1 | 2370 / 1142 | 11.5 s | - |
| plan_abstraction | 8 pieces, 128 ops (`abstract_state` on all 32 memory registers for c1-c4; c0, c5, c6, c7 concrete) | 128 | 0 | 1 | 2554 / 12472 | 69.2 s | 7 UNSAT in <=1.2 s, c6 TIMEOUT 60 s |
| check c6, 300 s | - | - | - | 0 | - | - | UNSAT 94.2 s |
| cegar / refine | none needed (no SAT piece) | - | - | 0 | - | - | - |
| vacuity | 8 proofs | - | - | 0 | - | - | see below |

Totals: 2 LLM calls (limit 30), 1 round (limit 5), 4924 input / 13614 output tokens, cost 0.0172 USD (`deepseek_prices.usage_cost`). Cache: the gateway reports `usage.prompt_tokens_details.cached_tokens` (2048 in call 2), not `prompt_cache_hit_tokens`; those two fields are null in the JSONL and the raw `usage` object is kept.

Pieces (cond over the signal ids): c0 `rst`; c1 `!rst & srEmpty & !rbEmpty`; c2 `!rst & !srEmpty & rbEmpty`; c3/c4 flag mismatch `srFull != rbFull` with both empty / both non-empty; c5 both empty and flags equal; c6 non-empty, flags equal, `srDataOut != rbDataOut`; c7 same with `==`.

## Vacuity

- Each piece assertion is violable when the registers are free, except c0 (`rst` makes `equal` hold structurally). That check shows the piece is not trivially true.
- Case reachability (BMC, depth 40, `case & !rst`): c5 and c7 are reachable (SAT). c1-c4 find no hit within 40 cycles, and c6 hits the 300 s cap. This is the expected shape: c1-c4 and c6 are the cases the proof shows never happen in a correct FIFO pair, so their proofs are "the case is unreachable", not a vacuous pass. A bounded BMC miss does not prove unreachability by itself; the UNSAT results do.

## Failure tags

No LLM answer was rejected or retried, so there is nothing to tag as stuck, misunderstood or poor. One planning weakness: the LLM chose not to abstract c6 and said so in its reason; it did not try an `-enable`/`-slice` abstraction of the memories that could shrink the hard piece. No extra input was needed.

Harness failures fixed during setup (not LLM failures): Yosys 0.69 unconditional `abstract -value/-state` leaves conflicting drivers (workaround: `-enable` on a constant-1 wire); `write_btor` emits `uext S -1 w` that rIC3 rejects (rewritten to `const`); `cover` is a Verilog keyword.

## Limits of this harness

`cutpoint -blackbox` and UF pairing do not apply (flat netlist, the two FIFOs compute different functions); memory havoc is `abstract_state` on the 32 memory registers; k-symbolic-address tracking is not implemented. The replay path (SAT, concrete simulation, spurious) was exercised offline on a deliberately coarse abstraction but never fired in the real run, since no piece was SAT.

## Files

`llm_calls.jsonl` (one record per LLM call: prompt, raw response, verdict, tokens, latency, cost, cumulative), `tool_events.jsonl` (coverage, checks, vacuity), `state.json`, `logs/` (rIC3 logs per piece).
