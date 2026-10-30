# Manual case study: llmm-lrg_arb_lrg_16_ebmc (issue #25)

Same flow and harness as [`case_study_fifo_vis`](../case_study_fifo_vis/README.md) (`src/case_study.py`; per-bench settings are in `case.json`, copied to `<workdir>/bench/case.json`). Run on Mazu, 2026-10-29, work dir `/var/tmp/neuroabs-runtime/case-lrg-arb-20261029/`. Model: `deepseek/deepseek-v4.1-flash` through the local gateway. Checker: rIC3 master 4d63899 `portfolio`, 60 s per piece, 2 runs at a time. Property: `!rst -> (!(chosen & o_grant_vec_ref[arbitrary_requester]) || ~in_req_vec[another_arbitrary_requester] || ranks[arbitrary_requester] < ranks[another_arbitrary_requester])`.

## Result

Property proved in 2 rounds: 13 leaf pieces all UNSAT (r1_c0-c3 and r2_c0-c8; r1_c4 was split again). Every split was SAT-coverage-checked, so the pieces together imply the original assertion.

| | Time |
|---|---|
| LLM (6 calls, 2 of them rejected, sequential) | 207.6 s |
| rIC3, round 1 (60 s cap, 5 pieces) | 63.3 s wall: c0-c3 in 1.2-2.2 s, c4 TIMEOUT |
| rIC3, round 2 (60 s cap, 9 pieces) | 10.5 s wall: all UNSAT in 1.2-2.5 s |
| **End to end** | **about 281 s** (LLM + rIC3; Yosys and coverage checks are a few seconds) |
| Baseline (rIC3 portfolio on the whole model) | TIMEOUT at 1200 s |
| Split-only control (same 13 leaves, no operators, 60 s cap) | 15.4 s wall, all UNSAT in 1.2-2.7 s |

The flow proves a property the baseline cannot in 1200 s. But **the LLM-chosen abstraction contributed nothing**: it returned an empty operator list for every piece in both rounds, so the abstract models are the concrete ones and the split-only control is the same run again (15.4 s vs 10.5 s of rIC3, within noise). All of the gain comes from the round-2 split: it fixes `arbitrary_requester` to a pair of constant values (0-1, 2-3, ..., 14-15), which turns the dynamic bit-select/array index into a static one and makes each piece easy. This is a splitting (case-analysis) result, not an over-approximation result. About 74 s of the 281 s is rIC3, 208 s is LLM latency; the 60 s wasted on r1_c4 is a quarter of the rIC3 time.

## Per-step table

| Step | Proposals | Accepted | Rejected | LLM calls | Tokens in/out | LLM time | rIC3 |
|---|---|---|---|---|---|---|---|
| plan_split r1 | 5 cases (call 2; call 1 rejected) | 5 (coverage SAT passed) | call 1: unknown identifier `ranks` | 2 | 4714 / 4427 | 32.7 s | - |
| plan_abstraction r1 | 5 pieces, 0 ops | 0 ops | 0 | 1 | 2324 / 6062 | 49.2 s | c0-c3 UNSAT <=2.2 s, **c4 TIMEOUT 60 s** (63.3 s wall) |
| plan_split r2 (re-split r1_c4) | 9 cases (call 5; call 4 rejected) | 9 (coverage SAT passed against r1_c4's scope) | call 4: 17 cases, limit is 12 | 2 | 6129 / 10572 | 75.2 s | - |
| plan_abstraction r2 | 9 pieces, 0 ops | 0 ops | 0 | 1 | 2874 / 6210 | 50.6 s | 9 UNSAT <=2.5 s (10.5 s wall) |
| cegar / refine | none needed (no SAT piece) | - | - | 0 | - | - | - |
| vacuity | 13 proofs | - | - | 0 | - | - | see below |
| split-only control | 13 leaves, no operators | - | - | 0 | - | - | 13 UNSAT, 15.4 s wall |

Totals: 6 LLM calls (limit 30), 2 rounds (limit 5), 16041 input / 27271 output tokens, 0.0363 USD. The replay/refine path never fired (no SAT piece), so it is still untested on a real run here.

Round-1 pieces: c0 `~chosen`; c1 `chosen & arbitrary_requester >= 16`; c2 `chosen & arbitrary_requester < 16 & another_arbitrary_requester >= 16`; c3 both in range and `in_req_vec == 0`; c4 both in range and `in_req_vec != 0` (the hard piece, left whole). Round-2 pieces split r1_c4 by `in_req_vec[another_arbitrary_requester]` low (c0) and, when high, by `arbitrary_requester` in {0,1}, {2,3}, ..., {14,15} (c1-c8).

## Failure tags

| Call | Step | Tag | What happened |
|---|---|---|---|
| 1 | plan_split r1 | misunderstood | used `ranks` as an identifier; only the flattened `ranks_0..ranks_15` exist (the tool rejected it, retry fixed it) |
| 2 | plan_split r1 | poor | valid and coverage-checked, but split by output conditions and left the whole rank-ordering invariant in c4, which timed out |
| 3 | plan_abstraction r1 | poor | empty list for all pieces; for c4 it argued that any class-A operator on `ranks` makes the piece spuriously SAT and tried none (no `-enable`/`-slice` variant) |
| 4 | plan_split r2 | misunderstood | returned 17 cases against the stated limit of 12 (rejected, retry fixed it) |
| 5 | plan_split r2 | none | the useful answer: fix the index registers to constants |
| 6 | plan_abstraction r2 | none | empty list; nothing was needed since every piece proves in about 2 s |

Neither "stuck" nor an over-abstraction (spurious SAT) occurred.

## Vacuity (run on the concrete model)

- Case reachability (BMC depth 40, `case & !rst`): r1_c0, r1_c3 and all of r2_c0-c8 are reachable (SAT). r1_c1 and r1_c2 (an out-of-range index register) find no hit within depth 40 (UNKNOWN); those proofs are "the case never happens", which is expected since `arbitrary_requester` is always loaded as 0..15.
- Each piece assertion is violable when the registers are free (all 13), so no piece is trivially true.
- The harness reported UNKNOWN as `ERROR` on the first vacuity run for r1_c1 and r1_c2; this was fixed in `ric3()` and those two pieces were re-run (the `vacuity` events for them appear twice in `tool_events.jsonl`; the later one counts).
- `uext S -1 w` rewrite (lesson from fifo_vis): no model in this study contains such a node (`uext_rewrite` events: 0, and none in the original `model.btor2`), so the rewrite was never applied here.

## Harness changes since the fifo_vis PR

Per-bench settings (`case.json`: `.sv` paths, property text, memory/alias regexes, operator notes); the assertion is read from the flat netlist as `prop_a` / `prop_en` signals instead of the fifo-specific `equal`/`rst`; reachability vacuity runs on the concrete model; new `split-only` and `report` commands (LLM and rIC3 time separate); BMC `UNKNOWN` verdict; unrolled-loop temp wires (`name[4:0]`) are not exposed as signals. The fifo_vis prompt/pieces were produced by the previous version of the harness; its `case.json` is included but that study was not re-run.

## Files

`llm_calls.jsonl` (one record per LLM call with prompt, raw response, verdict, tag in `failure`, tokens, latency, cost), `tool_events.jsonl` (coverage, checks, per-pass wall times, split-only, vacuity), `state.json`, `logs/` (rIC3 log per run: `*_k0` abstraction run, `*_so` split-only, `*_reach` vacuity), `ctx_r2.txt` (extra input to the round-2 split), `case.json`.
