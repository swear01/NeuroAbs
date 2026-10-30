# Adaptive split flow: llmm-simple_cam_8_ebmc

Adaptive flow of `src/case_study.py` (PR #29) on a bench whose whole-model baseline times out. Property (`bench/case.json`): `!rst -> (!(chosen & chosen_not_popped & lookup_id == chosen_push_id) || |lookup_match)`, top module `simple_cam` (8 entries, 3-bit ids; `case.json` key `top`). Run on Mazu 2026-10-30, work dir `/var/tmp/neuroabs-runtime/adaptive-simple-cam-8-20261030/`. LLM: `deepseek/deepseek-v4.1-flash`. Checker: rIC3 master 4d63899 `portfolio`, 8 pieces at a time, caps 3 s / 20 s / 120 s, end-to-end budget 1200 s (`--budget`, never reached).

## Result

Property proved in 2 rounds of checking: **16 leaf pieces, all UNSAT** (r2_c0-c15; the 8 round-1 pieces were split again). Every split was SAT-coverage-checked. No SAT piece, so no spurious CEX and no CEGAR replay.

| | Time |
|---|---|
| LLM (2 calls: plan_split 39.3 s, decide 147.2 s) | 186.5 s |
| rIC3 (3.1 s + 5.2 s summary + 3.7 s + 0.04 s summary) | about 12 s |
| **End to end (`run`)** | **199 s** |
| Baseline (rIC3 portfolio, whole model) | TIMEOUT at 1200 s (`case-baseline-20261029`) |
| Split-only control (same 16 leaves, no operators, 20 s cap) | 8.8 s wall, all UNSAT |
| LLM tokens / cost | 7068 in / 25819 out, 0.0325 USD |

**Abstraction was used, and it did not help.** In round 1 the LLM split on `chosen_push_id` (8 constants, `auto`); all 8 timed out at 3 s and also at a 5 s IC3 summary run (r1_c0 also times out at 100 s on its own). The `decide` call answered `both` for every piece: split each on "some valid entry holds `chosen_push_id`" vs "none does" and apply `abstract_state entity_cnt`. All 16 children are UNSAT, none SAT. The gain comes from that witness-existence split; the control without the operator proves the same 16 leaves (evens 0.1 s, odds 1.5-8.2 s with 8 in parallel). With the operator, evens take 0.1-2.2 s; the 6 odd pieces that timed out at the 3 s cap were proved by the 5 s single-engine IC3 summary pass (the abstracted model collapses to 3 variables after rIC3 preprocessing). So: abstraction gave UNSAT (sound, no spurious CEX), no speed-up over the split-only control. Run alone, `portfolio --cex` takes about 1.1 s on an abstract odd piece and 0.05 s without `--cex`; the 3 s timeouts are portfolio start-up plus 8 parallel portfolios, not proof difficulty.

**Load.** `uptime` at start of `run`: 1.31 / 9.56 / 14.05; end of `run`: 1.16 / 5.51 / 11.57; split-only control right after: 1.15 / 5.4 / 11.5. The machine was idle (no agentic-ic3 `run_matrix` job); the 1-minute load is this run's own parallel portfolios.

## Rounds and decisions

| Round | Pieces (cap) | Outcome | Decision |
|---|---|---|---|
| plan | - | call 1 (accepted): `chosen_push_id`, 3 bits, auto | r1_c0-c7 (`chosen_push_id == 0..7`) |
| 1 | r1_c0-c7 (3 s) | all TIMEOUT; 5 s IC3 summary: all TIMEOUT | LLM `decide` (call 2): `both` x8 |
| 2 | r2_c0-c15 (3 s) | 10 UNSAT (0.1-2.2 s), 6 TIMEOUT at 3 s | 5 s IC3 summary pass proves the 6 (0.0 s) |

No auto-expansion fired (the direction was resolved by the `decide` call).

## Failure tags

| Call | Step | Tag | What happened |
|---|---|---|---|
| 1 | plan_split | good | fixes `chosen_push_id`, the register the proof quantifies over; not enough alone (still TIMEOUT) |
| 2 | decide | good (split), poor (abstraction) | the "witness exists" split is what makes every piece easy; the `entity_cnt` abstraction was redundant, and its stated reason misreads `entity_cnt` as an "8-bit 1-bit-wide counter" (it is 8 one-bit counters) |

No call was rejected, stuck or over-abstracted. Neither bench needed operator 8 of #24 (k symbolic slots): the case split on a value-in-slot predicate was enough.

## Vacuity (concrete model)

All 16 cases are reachable within BMC depth 40 (SAT), and every piece assertion is violable with free registers (16/16), so no proof is trivially true.

## Files

`llm_calls.jsonl`, `tool_events.jsonl` (per-check verdicts and times, summary passes, load events), `state.json`, `report.out`, `run.out`, `split_only.out`, `vacuity.out`, `uptime_*.txt`, `bench/case.json`. rIC3 logs omitted.
