# Adaptive split flow: llmm-fifo_ref_16_ebmc

Adaptive flow of `src/case_study.py` (PR #29) on a bench whose whole-model baseline times out. Property (`bench/case.json`): `!rst -> (!(pop && (!ALLOW_BYPASS || fifo_size > 0)) || data_out == ref_fifo[ref_fifo_head])` (16-deep FIFO against a reference array). Run on Mazu 2026-10-30, work dir `/var/tmp/neuroabs-runtime/adaptive-fifo-ref-16-20261030/`. LLM: `deepseek/deepseek-v4.1-flash`. Checker: rIC3 master 4d63899 `portfolio`, 8 pieces at a time, caps 3 s / 20 s / 120 s, end-to-end budget 1200 s (`--budget`, never reached).

## Result

Property proved in 6 rounds of checking: **23 leaf pieces, all UNSAT** (r1_c1, r5_c0/c3/c6/c7/c9/c10/c12-c15, r6_c0-c11). Every split was SAT-coverage-checked. No SAT piece, so no spurious CEX and no CEGAR replay. No operator was ever applied (the LLM answered `resplit` for every timed-out piece).

| | Time |
|---|---|
| LLM (2 calls: plan_split 25.8 s, decide 22.6 s) | 48.4 s |
| rIC3 (3.1 + 3.1 + 20.1 + 20.2 + 231.9 + 5.3 summary + 102.4 s) | 386 s |
| **End to end (`run`)** | **437 s** |
| Baseline (rIC3 portfolio, whole model) | TIMEOUT at 1200 s |
| Split-only control, same 23 leaves, 20 s cap, run right after (loaded) | 41.1 s wall: 7 UNSAT (0.1 s), 16 TIMEOUT at 20 s |
| One hard leaf (r6_c0) alone, 200 s cap, machine idle | UNSAT in 23.9 s (95.7 s in the 8-parallel run) |
| LLM tokens / cost | 8700 in / 6129 out, 0.0094 USD |

**The gain is again pure splitting; abstraction was not used.** Round 1: the LLM split on `fv_env_ref_fifo_head` (auto, 1 bit). The tool then auto-expanded that index one bit per round (rounds 1-4, no LLM call) until round 5 had it fixed to all 16 values: 10 of the 16 pieces were UNSAT (87-111 s), 6 TIMEOUT at 120 s. The `decide` call (call 2) answered `resplit` for those 6 on `dut_head` (the DUT read pointer), giving 12 children; 6 were UNSAT at 0.1 s and 6 at 95-102 s. Fixing both pointers turns `ref_fifo[head]` and `buffer[dut_head]` into plain slot registers. The LLM never asked for `abstract` or `both`, so there is nothing to compare against the split-only control (it is the same models). The IC3 summary on the 6 timed-out pieces was uninformative, and the LLM did not use it to propose an operator.

**Load: this run is heavily contended, by its own parallelism.** `uptime` at the start of `run`: 1.3 / 5.4 / 11.5 (idle); at the end of `run` (round 6 done): 87.2 / 74.0 / 43.2; at the end of the split-only control: 99.4 / 79.4 / 46.5. I did not see the agentic-ic3 `run_matrix` job running at the end (no such process at 11:02), so I attribute the load to 8 parallel portfolios (about 10 threads each) on 32 cores. Effect: r6_c0 takes 95.7 s in the run but 23.9 s alone, so the 90-110 s leaf times are about 4x inflated and the real total is lower. The 20 s split-only control timed out for the same reason, so it says nothing about hardness. The 3 s/20 s timeouts in rounds 1-4 (pieces with 1-4 bits fixed) were measured at low load.

## Rounds and decisions

| Round | Pieces (cap) | Outcome | Decision |
|---|---|---|---|
| plan | - | call 1: `fv_env_ref_fifo_head`, 1 bit, auto | r1_c0, r1_c1 (bit 4; r1_c1 is the out-of-range half) |
| 1 | 2 (3 s) | r1_c1 UNSAT 0.0 s; r1_c0 TIMEOUT | auto-expand |
| 2 | 2 (3 s) | both TIMEOUT | auto-expand |
| 3 | 4 (20 s) | all TIMEOUT | auto-expand |
| 4 | 8 (20 s) | all TIMEOUT | auto-expand |
| 5 | 16 (120 s) | 10 UNSAT (87-111 s), 6 TIMEOUT; 5 s IC3 summary: all TIMEOUT | LLM `decide`: `resplit` on `dut_head` x6 |
| 6 | 12 (120 s) | all UNSAT: 6 at 0.1 s, 6 at 95-102 s | done |

## Failure tags

| Call | Step | Tag | What happened |
|---|---|---|---|
| 1 | plan_split | good | picks the reference pointer; auto-expansion does the rest |
| 2 | decide | good | reads the situation correctly (reference slot fixed, DUT pointer remains) and picks `dut_head`; its children are easy |

No call was rejected, stuck or over-abstracted. Operator 8 of #24 (k symbolic slots) was not needed here either: instantiating the two pointers suffices.

## Vacuity (concrete model)

Piece assertion violable with free registers: 23/23. Case reachability at BMC depth 40: 16 SAT; 7 UNKNOWN (r1_c1 and the six r6 pieces with an out-of-range or unreachable pointer combination, which prove vacuously, as expected).

## Files

`llm_calls.jsonl`, `tool_events.jsonl` (includes the r6_c0 idle rerun), `state.json`, `report.out`, `run.out`, `split_only_loaded.out` (control during the load), `vacuity.out`, `uptime_*.txt`, `bench/case.json`. rIC3 logs omitted.
