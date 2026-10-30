# Adaptive split flow: llmm-lrg_arb_lrg_16_ebmc

Rerun of the [manual lrg_arb case study](../../case_study_lrg_arb/README.md) with the adaptive flow in `src/case_study.py` (Phase 2/3 of issue #23). Same property, same model, same `case.json` (`bench/case.json`). Run on Mazu 2026-10-30, work dir `/var/tmp/neuroabs-runtime/adaptive-lrg-arb-20261030/`. LLM: `deepseek/deepseek-v4.1-flash` through the local gateway. Checker: rIC3 master 4d63899 `portfolio`, 8 pieces at a time, cap 3 s (rounds 1-2), 20 s (rounds 3-4), 120 s (rounds 5+).

## Result

Property proved in 3 rounds of checking: 5 leaf pieces (r1_c1, r3_c0-c3), all UNSAT, every split SAT-coverage-checked against its parent piece's scope. No piece was SAT, so the CEGAR replay path did not fire.

| | New flow | Old flow (case_study_lrg_arb) |
|---|---|---|
| LLM (calls, sequential) | 45.1 s (3 calls, 1 rejected) | 207.6 s (6 calls, 2 rejected) |
| rIC3 wall | 20.4 s (3 s, 3 s, 20 s passes + one 5 s summary pass) | 73.8 s |
| **End to end (`run`)** | **66.0 s** | about 281 s |
| Baseline (rIC3 portfolio, whole model) | - | TIMEOUT at 1200 s |
| Split-only control (same 5 leaves, no operators, 20 s cap) | 9.9 s wall, all UNSAT (r1_c1 1.2 s, r3_c0-c3 8.2-9.8 s) | 15.4 s (13 leaves) |
| LLM tokens / cost | 8022 in / 4082 out, 0.0066 USD | 16041 / 27271, 0.0363 USD |

About 4.3x faster end to end, and the LLM share fell from 74% to 68% of the time (it is now dominated by one rejected 32 s call). **As in the old study the gain comes from splitting only: the LLM chose `resplit` and no operators were applied anywhere**, so the split-only control is the same models again (9.9 s vs 9.2 s of the last pass). This is a case-analysis result, not an over-approximation result. No strict OA/no-op comparison or effective-final-location analysis applies, since there is no abstraction.

**Load.** `uptime` at the start of `run`: 0.23 / 0.13 / 0.11; at the end of the split-only control: 16.4 / 3.8 / 1.3 (the machine was idle; the rising load average is this run's own 8 parallel portfolios, plus the parent's matrix job starting up a minute later). So these times are close to unloaded; see the fifo_vis README for the loaded case. Contention cannot explain the 3 s timeouts here: r1_c0 also timed out in the 5 s single-engine summary pass, and the leaves still take 8-10 s in the control.

## Rounds and decisions

| Round | Pieces checked (cap) | Outcome | Decision |
|---|---|---|---|
| plan | - | call 1 rejected (coverage SAT check failed), call 2 split by `arbitrary_requester[4]` | r1_c0 (`[4]==0`), r1_c1 (`[4]==1`) |
| 1 | r1_c0, r1_c1 (3 s) | r1_c1 UNSAT 1.2 s; r1_c0 TIMEOUT | LLM asked (call 3) after a 5 s summary pass: IC3 depth 6, lemmas per frame `[1, 48, 167, 487, 422, 398, 878, 48]`, 5.4 literals of 92 state bits per lemma |
| 2 | r2_c0, r2_c1 (3 s) | both TIMEOUT | no LLM call: the tool auto-expanded the next index bit of `arbitrary_requester` (direction `auto:true`), so r3_c0-c1 under r2_c0, r3_c2-c3 under r2_c1 |
| 3 | r3_c0-c3 (20 s) | all UNSAT in 7.7-9.1 s | done |

Call 3 (r1_c0, `resplit`, `{"index":"arbitrary_requester","bits":2,"auto":true}`), reason as given by the LLM: "The assertion quantifies over the index register arbitrary_requester (it indexes o_grant_vec_ref and ranks); fixing its value instantiates the comparison and removes the index-quantification hardness that makes IC3 climb slowly (depth 6, ~500 lemmas per frame). Only bit 4 is fixed so far, so continue splitting the same index register and let the tool auto-split any child that still times out." The reasoning quotes the lemma summary it was shown.

Pruning: the 2-bit index split of r1_c0 produced four cases on `arbitrary_requester[4:3]`; two of them (`==2`, `==3`) contradict the parent case `[4]==0`, and the tool dropped them (`pruned_empty` event, SAT check `Study.empty`). Without this the contradictory pieces are vacuously proved (found in an earlier unpruned run by the vacuity check).

## Failure tags

| Call | Step | Tag | What happened |
|---|---|---|---|
| 1 | plan_split | misunderstood | 16 constant cases `arbitrary_requester == 0..15` only, assuming the register is always in range; the 5-bit register also takes 16-31, so coverage failed; rejected by the SAT coverage check, 32.1 s and 2783 output tokens wasted |
| 2 | plan_split | good | top bit of the index register, two cases, coverage-checked |
| 3 | decide | good | `resplit` with an index direction, reason cites the lemma summary |

Neither "poor" nor "stuck" occurred; there was no abstraction request (the LLM always chose resplit; abstraction is only asked for in `abstract`/`both`).

## Vacuity (run on the concrete model)

All 5 leaves: the case is reachable by BMC (SAT), and the piece assertion is violable when the index registers are free, so no proof is vacuous or trivially true. `uext_rewrite` was not needed for this bench.

## Variance

The same flow was also run once under the parent's matrix-job load, before `uptime` logging was added: the LLM split `arbitrary_requester` into 32 constant cases in one call (5.6 s), 29 of the 32 pieces proved only in the 5 s summary pass. That run (32 leaves, 1 LLM call) is not archived here; it shows that the tree shape depends on the LLM sample (2 index-bit levels here vs one direct 32-way split there), and both end in an all-UNSAT leaf set within about 30 s of rIC3 wall.

## Changes in this flow and findings from aborted runs

See [../fifo_vis/README.md](../fifo_vis/README.md) for the flow description (what changed, the lemma-summary finding, and the issues that earlier attempts exposed: an unbounded auto-expansion, contradictory index cases, `enable`+`enablen` build errors, and a budget starvation). The pruning fix above was found on the lrg_arb unpruned run: `/var/tmp/neuroabs-runtime/aborted-lrg-arb-unpruned-20261030/` on Mazu (vacuity flagged r2_c8, r2_c13, r3_c14-c25 as contradictory).

## Files

`llm_calls.jsonl` (prompt, raw response, verdict, tokens, cache, latency, cost per call; `extra_input` holds the structured per-piece decision with its reason), `tool_events.jsonl` (coverage, pruning, auto expansion, checks, pass wall times, split-only, vacuity, `load` events with `os.getloadavg()` at the start and end of each command), `state.json`, `run.out`, `split_only.out`, `vacuity.out`, `report.out`, `uptime_start.txt`, `uptime_end.txt`, `bench/case.json`. rIC3 logs stayed on Mazu.
