# Adaptive split flow: llmm-fifo_vis

Rerun of the [manual fifo_vis case study](../../case_study_fifo_vis/README.md) with the adaptive flow in `src/case_study.py` (Phase 2/3 of issue #23). Run on Mazu 2026-10-30, work dir `/var/tmp/neuroabs-runtime/adaptive-fifo-vis-20261030/`. LLM: `deepseek/deepseek-v4.1-flash`. Checker: rIC3 master 4d63899 `portfolio`, 8 pieces at a time, cap 3 s (rounds 1-2), 20 s (rounds 3-4), 120 s (rounds 5+).

## Result

Property proved in 4 rounds: 15 leaf pieces (r3_c2, r4_c0-c13), all UNSAT; every split SAT-coverage-checked. No SAT piece, so no CEGAR replay.

| | New flow | Old flow (case_study_fifo_vis) |
|---|---|---|
| LLM | 7.9 s (1 call) | 80.7 s (2 calls) |
| rIC3 wall | 53.0 s (3 s, 3 s, 20.1 s, 26.7 s passes) | 154.2 s (60 s pass + 94.2 s on c6) |
| **End to end (`run`)** | **62.2 s** | about 235 s |
| Baseline (rIC3 portfolio, whole model) | not rerun | about 199 s (unloaded, 2026-10-29) |
| Split-only control (same 15 leaves, no operators, 20 s cap) | 30.1 s wall: 14 UNSAT in 8.9-18.0 s, r3_c2 TIMEOUT at 20 s | - |
| LLM tokens / cost | 2692 in / 850 out, 0.0010 USD | - |

About 3.8x faster end to end than the old flow, and about 3x faster than the old baseline figure (the old flow was 1.2x slower than that baseline; the baseline was not rerun under today's load, so that comparison mixes load conditions). As in lrg_arb the **LLM chose a split direction only and no operator was applied**; the gain is from case analysis on the index register `rb_tail` (top bit, then the tool took the next bit each round with no LLM call).

**Load: these times were measured under heavy load.** `uptime` at the start of `run`: 66.0 / 41.4 / 17.4; at the end of `run`: 85.1 / 50.5 / 22.0; at the end of split-only: 97.1 / 56.9 / 25.0, on 32 cores (the unrelated agentic-ic3 `run_matrix` job). The split-only control ran right after the run, under comparable (slightly higher) load. Leaf times in the run (7.7-18.7 s) and in the control (8.9-18.0 s) agree within about 7 s of noise; the single disagreement is r3_c2: UNSAT in 15.9 s in the run but TIMEOUT at 20 s in the control, i.e. it sits at the cap and flips with contention. No leaf that timed out at 3 s proved in under 3 s in the control, because leaves only appear after the 20 s round; the 3 s timeouts of rounds 1-2 (6 pieces, all parents) cannot be separated into contention and hardness from this data, and the 7 r3 pieces that timed out at 20 s were split once more and then needed 8-19 s each, so rounds 3-4 are plausibly inflated by load.

## Rounds and decisions

| Round | Pieces checked (cap) | Outcome | Decision |
|---|---|---|---|
| plan | - | call 1, accepted | split by `rb_tail` top bit, `auto:true` (r1_c0, r1_c1) |
| 1 | 2 (3 s) | both TIMEOUT | auto-expanded: next bit of `rb_tail` (4 pieces) |
| 2 | 4 (3 s) | all TIMEOUT | auto-expanded (8 pieces) |
| 3 | 8 (20 s) | r3_c2 UNSAT 15.9 s, 7 TIMEOUT | auto-expanded 7 pieces (14 children) |
| 4 | 14 (20 s) | all UNSAT in 7.7-18.7 s | done |

The only LLM call (the plan; no timeout decision was needed because every timed-out piece had an `auto` direction) said: "The check 'equal' compares sr_mem[sr_tail] against rb_mem[rb_tail] plus the full/empty flags; the real hardness is the pointer arithmetic of the FIFOs, i.e. the proof quantifies over the index registers that select which memory slot is read/written (rb_tail, rb_head, sr_tail). Instantiating these pointers turns the all-slots data equality into a concrete slot comparison. Start by case-splitting the ring-buffer tail pointer rb_tail on its top bit (2 cases), with auto:true so the tool keeps splitting the remaining bits of rb_tail on the children that time out; later rounds can fix rb_head/sr_tail the same way. Splitting on outputs (full/empty/equal) is avoided since it would not instantiate the quantified index." The `decide` consultation path (resplit/abstract/both with lemma summary) therefore did not run in this final fifo run; it ran once in the lrg_arb README run.

## Failure tags

| Call | Step | Tag | What happened |
|---|---|---|---|
| 1 | plan_split | good | index direction on `rb_tail`, auto; reason names the quantified index registers |

Only `rb_tail` was fixed; `sr_tail` and `rb_head` were not needed, because fixing `rb_tail` to a constant in all 16 slot values (4 bits) was enough for IC3. Neither "poor", "misunderstood" nor "stuck" occurred in the final run.

## Vacuity (concrete model)

All 15 leaves: case reachable by BMC (SAT), assertion violable with free registers. 58 `uext_rewrite` events (the `uext S -1 w` fix from the first fifo study was applied to each piece model). 13 `pruned_empty` checks ran and dropped nothing (the splits were on distinct bits).

## Flow changes since the manual studies

- Up to 8 pieces in parallel (was 2), rIC3 `portfolio`; caps escalate 3 s (rounds 1-2), 20 s (3-4), 120 s (5+), configurable via `--caps`.
- A TIMEOUT never triggers an automatic re-split of its own accord. The LLM gets, for every timed-out piece, the piece condition, per-piece times of the round, and an IC3 summary, and returns `resplit`, `abstract` or `both` with a reason (logged in `llm_calls.jsonl`). Only pieces without an `auto` direction are sent to the LLM.
- Index directions `{"index":ID,"bits":n,"auto":bool}` expand `ID[hi:lo] == n'dv` cases top bit first; `auto:true` lets the tool take the next bit of a timed-out child with no LLM call. At most 32 new pieces per round (auto expansions use at most half of it). Proved pieces are never touched again. Coverage is SAT-checked against the parent scope; cases empty under the parent scope are pruned.
- **rIC3 lemma summary.** rIC3 cannot print named lemmas on a run that does not finish (`--cert` works only on UNSAT and writes anonymous latches); the log shows depth, lemmas per frame, and `mic` lengths. After a timeout the tool runs a single-engine IC3 for 5 s and gives the LLM depth, lemmas per frame and the average lemma length. That pass can also prove a piece outright (then it counts as proved).
- Abstraction is only requested for timed-out pieces; the class-A-only check is unchanged; `validate_op` has a commented hook where operator 8 of #24 ("k symbolic memory slots") will be validated.
- New: `enable` and `enablen` together in one operator are rejected at validation (Yosys: "Multiple enable condition are not supported").
- Kept: soundness checks, vacuity on the concrete model, split-only control, `report` (LLM time vs rIC3 time), JSONL logging of tokens/cache/latency/cost, and now `load` events with `os.getloadavg()` at the start and end of each command.

## Earlier attempts on the way (all on Mazu, not archived here)

1. `aborted-fifo-64pieces-20261030/`: auto expansions were not counted against the per-round limit; round 3 made 64 pieces. Fixed.
2. `loaded-fifo-builderror-20261030/`: 25 LLM calls, 8 rounds, ended with 11 pieces `BUILD_ERROR` because the LLM proposed `abstract_state` with both `enable` and `enablen`, which Yosys rejects. This path (LLM abstraction on timed-out pieces, CEGAR spurious replay at depth 33) was therefore the only run that exercised abstraction; it showed the LLM happily abstracting all memory words of both FIFOs on `sr_empty`/`rb_empty`, one piece (r4_c23) came back spurious at depth 33 and was UNSAT in 8.2 s after that refinement, but the run did not finish. Fixed in `validate_op`; build errors are now logged as `build_error` events.
3. `loaded-fifo-budget-20261030/`: after fix 2, auto expansion of 16 timed-out pieces used the whole 32-piece budget, so every LLM answer was rejected ("no valid answer after 3 attempts"). Fixed by capping auto expansions at half the budget.

## Files

As in the lrg_arb README: `llm_calls.jsonl`, `tool_events.jsonl`, `state.json`, `run.out`, `split_only.out`, `vacuity.out`, `report.out`, `uptime_*.txt`, `bench/case.json`.
