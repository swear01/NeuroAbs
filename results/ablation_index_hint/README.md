# Index-hint ablation and sampling variance (adaptive split flow)

Flow: `src/case_study.py` as in PR #29 plus (a) the `--no-index-hint` switch, (b) a 300 s per-request LLM timeout with one retry (`llm_timeout` -> unsolved), (c) a fix for a TypeError in the `budget_exhausted` event. rIC3 4d63899 on Mazu, DeepSeek `deepseek/deepseek-v4.1-flash`, `--budget 1200`, 3 runs per cell, runs strictly sequential (`scripts/ablation_chain.sh`, `scripts/ablation_summary.py`).

`--no-index-hint` removes only the two prompt passages that say "split on the source of hardness, e.g. the quantified index or pointer" (system prompt) and "which index, pointer or slot does the proof quantify over" (first-split request). Everything else, including the `index` split form, is unchanged.

## Result (mean ± sd over 3 runs, wall seconds, `proved` = runs that ended PROVED)

| bench | hint wall | hint proved | no-hint wall | no-hint proved | first split on the quantified index (hint / no hint) |
|---|---|---|---|---|---|
| lrg_arb_16 | 36 ± 15 (24-58) | 3/3 | 280 ± 101 (170-414) | 3/3 | 3/3 / 3/3 |
| fifo_vis | 984 ± 178 (733-1112) | 2/3 | 588 ± 93 (484-710) | 2/3 | 3/3 / 0/3 |
| simple_cam_8 | 1240 ± 911 (49-2263) | 1/3 | 909 ± 540 (378-1650) | 0/3 | 3/3 / 3/3 |
| fifo_ref_16 | 910 ± 351 (548-1385) | 1/3 | 962 ± 371 (449-1315) | 2/3 | 3/3 / 1/3 |

(sd = sample sd of 3; wall includes LLM and rIC3; the simple_cam_8 hint-1 cell is the rerun, see below.) PR #29 single runs: lrg_arb 66 s, fifo_vis 62 s, simple_cam_8 199 s, fifo_ref_16 437 s.

Per-run line (wall, LLM s, rIC3 s, first-split variables, leaves, rounds, abstraction ops, LLM calls (rejected), verdict, `uptime` 1-min load at start->end of run):

```
fifo_ref_16-hint-1       wall  1385 llm 760.7 ric3  620.1 first=dut_head                                 idx=True  leaves=88 rounds=5 abs=111 calls=13(rej 4) UNRESOLVED open load 9.0->3.2
fifo_ref_16-hint-2       wall   799 llm 281.9 ric3  515.0 first=dut_head                                 idx=True  leaves=54 rounds=6 abs=53 calls=5(rej 2) PROVED load 14.6->79.4
fifo_ref_16-hint-3       wall   548 llm 372.8 ric3  163.5 first=fv_env_ref_fifo_head                     idx=True  leaves=64 rounds=5 abs=80 calls=6(rej 3) UNRESOLVED open,timeout load 0.3->2.8
fifo_ref_16-nohint-1     wall  1123 llm 518.2 ric3  599.9 first=dut_head,fv_env_fifo_size,fv_env_ref_fif idx=True  leaves=96 rounds=6 abs=95 calls=10(rej 4) PROVED load 2.7->90.3
fifo_ref_16-nohint-2     wall   449 llm  77.8 ric3  370.1 first=dut_bypass_detected,error,fv_env_fifo_si idx=False leaves=28 rounds=6 abs=0 calls=4(rej 1) PROVED load 73.4->75.0
fifo_ref_16-nohint-3     wall  1315 llm 1271.7 ric3   37.9 first=dut_bypass_detected,fv_env_fifo_size,pop idx=False leaves=44 rounds=5 abs=39 calls=29(rej 2) UNRESOLVED open load 2.8->1.4
fifo_vis-hint-1          wall  1112 llm 475.9 ric3  327.0 first=sr_tail                                  idx=True  leaves=76 rounds=5 abs=92 calls=9(rej 4) PROVED load 10.0->80.8
fifo_vis-hint-2          wall   733 llm 440.7 ric3  286.7 first=sr_tail                                  idx=True  leaves=72 rounds=5 abs=70 calls=9(rej 5) UNRESOLVED open,timeout load 12.6->29.1
fifo_vis-hint-3          wall  1107 llm 601.1 ric3  385.8 first=sr_tail                                  idx=True  leaves=58 rounds=5 abs=91 calls=10(rej 4) PROVED load 4.8->114.4
fifo_vis-nohint-1        wall   710 llm 503.3 ric3  199.0 first=rbEmpty,rbFull,srEmpty,srFull            idx=False leaves=69 rounds=4 abs=0 calls=9(rej 5) UNRESOLVED timeout load 35.6->4.6
fifo_vis-nohint-2        wall   484 llm 303.8 ric3  180.0 first=rbEmpty,rbFull,srEmpty,srFull            idx=False leaves=77 rounds=5 abs=0 calls=8(rej 3) PROVED load 19.5->68.1
fifo_vis-nohint-3        wall   569 llm 302.3 ric3  265.6 first=rbEmpty,srEmpty                          idx=False leaves=33 rounds=5 abs=30 calls=5(rej 2) PROVED load 55.4->105.5
lrg_arb-hint-1           wall    28 llm   7.6 ric3   18.5 first=arbitrary_requester                      idx=True  leaves=22 rounds=3 abs=0 calls=1(rej 0) PROVED load 1.2->20.6
lrg_arb-hint-2           wall    58 llm  40.6 ric3   16.6 first=arbitrary_requester                      idx=True  leaves= 5 rounds=3 abs=0 calls=1(rej 0) PROVED load 3.5->14.8
lrg_arb-hint-3           wall    24 llm   6.5 ric3   16.7 first=arbitrary_requester                      idx=True  leaves=24 rounds=2 abs=0 calls=1(rej 0) PROVED load 69.3->57.0
lrg_arb-nohint-1         wall   414 llm 182.3 ric3   11.4 first=another_arbitrary_requester,arbitrary_re idx=True  leaves=22 rounds=2 abs=0 calls=4(rej 2) PROVED load 19.1->10.2
lrg_arb-nohint-2         wall   170 llm 151.2 ric3   18.4 first=another_arbitrary_requester,arbitrary_re idx=True  leaves=19 rounds=2 abs=0 calls=2(rej 0) PROVED load 14.0->12.6
lrg_arb-nohint-3         wall   256 llm 234.3 ric3   21.6 first=another_arbitrary_requester,arbitrary_re idx=True  leaves= 9 rounds=3 abs=0 calls=6(rej 3) PROVED load 52.8->4.8
simple_cam_8-hint-1      wall  1407 llm 871.6 ric3  233.9 first=chosen_push_id                           idx=True  leaves=80 rounds=5 abs=120 calls=8(rej 3) UNRESOLVED open load 2.2->3.7
simple_cam_8-hint-2      wall  2263 llm 2040.5 ric3  219.1 first=chosen_push_id                           idx=True  leaves=84 rounds=5 abs=125 calls=25(rej 4) UNRESOLVED open load 30.7->2.3
simple_cam_8-hint-3      wall    49 llm  46.0 ric3    3.1 first=cam,cam_valid,chosen_push_id,h7          idx=True  leaves= 9 rounds=1 abs=0 calls=2(rej 1) PROVED load 64.7->31.1
simple_cam_8-nohint-1    wall  1650 llm 1478.0 ric3  164.9 first=chosen,chosen_not_popped,chosen_push_id, idx=True  leaves=68 rounds=5 abs=89 calls=27(rej 4) UNRESOLVED open load 2.2->8.8
simple_cam_8-nohint-2    wall   378 llm 230.4 ric3  145.4 first=chosen,chosen_not_popped,chosen_push_id, idx=True  leaves=51 rounds=5 abs=64 calls=7(rej 3) UNRESOLVED open,timeout load 2.9->14.6
simple_cam_8-nohint-3    wall   699 llm 256.9 ric3  137.3 first=chosen,chosen_not_popped,chosen_push_id, idx=True  leaves=44 rounds=5 abs=56 calls=7(rej 3) UNRESOLVED open,timeout load 31.1->0.3
```

Verdict "UNRESOLVED open" = the flow ended with pieces still open (usually `no valid answer to decide after 3 attempts`; `timeout` = pieces left at the cap). No run found a real counterexample or a vacuity problem.

## Findings

* **lrg_arb_16**: the hint is decisive for time (36 s vs 280 s, 8x) but not for success. Without it the LLM still splits on `arbitrary_requester` in 3/3 runs, but via `another_arbitrary_requester` first, and 2 of 4+ calls per run are rejected; the cost is LLM time (150-230 s vs 7-40 s), rIC3 time is the same.
* **fifo_vis**: without the hint the LLM never splits on a head/tail pointer. It splits on the output flags (`rbEmpty/rbFull/srEmpty/srFull`) 3/3 times and instead leans on `resplit` of timeouts. Proof rate is the same (2/3) and the mean is lower (588 s vs 984 s); the sample spread (484-1112 s) is larger than the effect, and the PR #29 62 s result was not reproduced with the hint (all three hint runs took 733-1112 s).
* **simple_cam_8**: both modes pick `chosen_push_id` first (the no-hint prompt still lists the index split form). The hint runs span 49 s to 2263 s: one run found a 9-leaf proof in 49 s, another used 25 calls and 2040 s of LLM time without finishing. 0/3 proved without the hint, 1/3 with it; 3 runs per cell cannot separate these.
* **fifo_ref_16**: `dut_head`/`fv_env_ref_fifo_head` first 3/3 with the hint, 1/3 without (the others split on `dut_bypass_detected`, `fv_env_fifo_size`, `pop`); 2/3 vs 1/3 proved.
* **Sampling variance dominates.** Within a cell, wall time varies by a factor 2-46x across identical runs. The hint changes which variable is split first (index first: 12/12 hint runs vs 7/12 without), and clearly helps lrg_arb, but on the other three benches the 3-run means overlap.
* **Where the flow fails** (10 of 24 runs did not prove; rc is not the verdict: rc=0 also occurs with open pieces): 5 ended with `no valid answer to decide after 3 attempts` (fifo_ref_16 hint-3, fifo_vis hint-2 and nohint-1, simple_cam_8 nohint-2 and nohint-3): every reply was rejected by the tool's checks (piece list not exactly the pending pieces, more than MAX_NEW=32 new pieces once the tool's own 16 auto-split pieces are counted, or an unchanged operator list). 5 ran out of budget with pieces still open (fifo_ref_16 hint-1 and nohint-3, simple_cam_8 hint-1, hint-2 and nohint-1). Two of those (fifo_ref_16 hint-1, simple_cam_8 nohint-1) then crashed with rc=1 in the `budget_exhausted` event (TypeError, fixed, see below); the other three ended cleanly with rc=0. No run ended in `llm_timeout`, a code error other than that TypeError, or a real counterexample.

## Tagging of LLM calls

Automatic, from the tool's verdict in `llm_calls.jsonl`. **good** = accepted by the tool (valid, SAT-covered split or decision; says nothing about whether it was a good idea), **misunderstood** = rejected for format/count/piece-list reasons, **poor** = rejected because the split did not cover or the operator list was unchanged, **stuck** = the run ended because 3 attempts failed.

| cell | good | misunderstood | poor | stuck runs |
|---|---|---|---|---|
| lrg_arb hint | 3 | 0 | 0 | 0 |
| lrg_arb no hint | 7 | 4 | 1 | 0 |
| fifo_vis hint | 15 | 13 | 0 | 1 |
| fifo_vis no hint | 12 | 9 | 1 | 1 |
| simple_cam_8 hint (1 rerun, 2, 3) | 5+21+1 | 2+2+1 | 1+2+0 | 0 |
| simple_cam_8 no hint | 31 | 9 | 1 | 2 |
| fifo_ref_16 hint | 15 | 9 | 0 | 1 |
| fifo_ref_16 no hint | 36 | 7 | 0 | 0 |

A manual reading of the first-split reasons is in the `llm_calls.jsonl` files (`plan_split` call, field `reason`).

## The killed run (LLM-infrastructure failure, not a method result)

`simple_cam_8-hint-1-hung/`: the first attempt blocked for more than 1600 s on one `cegar_refine` gateway request (round 4, no tool events, one open socket to 127.0.0.1:35001) and was killed at 2050 s. That run is **excluded** from the table; the cell was rerun at the end (`simple_cam_8-hint-1/`, 1407 s). The 300 s request timeout was added after it.

## Which runs have which fixes

* Timeout (300 s + 1 retry, `llm_timeout`): active from 18:12:14 on. It applies to every run except lrg_arb hint-1/nohint-1, fifo_vis hint-1/nohint-1 and the killed simple_cam_8 hint-1 (these, and simple_cam_8 nohint-1, started before it; see `chain.status`). It fired once as a retry (simple_cam_8 nohint-3, attempt 1) and never ended a run as `llm_timeout`.
* `budget_exhausted` TypeError fix: deployed 20:09:48; runs started after fifo_vis nohint-2 have it. fifo_ref_16 hint-1 and simple_cam_8 nohint-1 hit the crash; their verdicts are read from state.

## Limitations

* **Mazu was not quiet.** Unrelated agentic-ic3 `kernel.run` jobs ran on the same host; the 1-minute load at run end reached 114 (see per-run loads, `uptime_*.txt` in each run). rIC3 times and, through the 20 s caps, which pieces time out, are affected; LLM times are not. Wall-time comparisons between cells therefore have an unquantified load component.
* n = 3 per cell: the spread is larger than most differences, so only the lrg_arb time difference and the fifo_vis first-split behaviour are clear.
* The tagging is mechanical (accepted/rejected), not a judgement of whether a split was sensible.
* `--budget 1200` only limits rIC3 caps, so runs can end beyond it because of LLM time (simple_cam_8 hint-2: 2263 s).
* DeepSeek sampling is not seeded; runs were not rerun with identical randomness.
* The hint also changes the order effects of one prompt only; other prompt text (e.g. the example of the `index` form) still suggests index splits, so "no hint" is not "no index knowledge".
