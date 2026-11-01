# Reruns with short prompts (#32)

Same 14 runs as `results/decide_fix` (fifo_ref_64 hint ×2 at budget 1800 s; fifo_ref_16 hint, fifo_vis hint, fifo_vis no hint and simple_cam_8 no hint ×3 at budget 1200 s), now with the short decide/refine prompts of #32:
range-folded signal names, labelled operator sets, decisions per group of pieces (at most 8 groups per call), a one-line lemma summary, and refine counterexamples cut to the property's cone of influence. The request timeout went from 300 s to 600 s.
Same machine (Mazu, shared), same model (deepseek-flash through the local gateway), run sequentially by `scripts/decide_fix_chain.sh`.

`offline_sizes.jsonl` rebuilds the decide and refine prompts of the `results/decide_fix` runs with the new code (`scripts/prompt_size.py`), without LLM calls.
Per-run tables below come from `python scripts/llm_cost_summary.py results/short_prompts` (and `results/decide_fix` for the old runs).

## Per run

| run | verdict | rounds | wall s | decide | refine | decide KB max | refine KB max | prompt KB total | output tok | latency mean/max s | LLM s | timeouts |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fifo_ref_16-hint-1 | open | 4 | 1585 | 3 | 16 | 8.9 | 4.7 | 77 | 151187 | 59/141 | 1473 | 0 |
| fifo_ref_16-hint-2 | open | 6 | 1781 | 4 | 8 | 7.8 | 3.5 | 50 | 122245 | 82/362 | 1388 | 0 |
| fifo_ref_16-hint-3 | open | 5 | 1198 | 4 | 0 | 8.0 | 0.0 | 30 | 72543 | 144/548 | 1011 | 0 |
| fifo_ref_64-hint-1 | open | 6 | 3929 | 3 | 24 | 8.8 | 14.4 | 180 | 318202 | 119/250 | 3319 | 0 |
| fifo_ref_64-hint-2 | open | 8 | 2226 | 6 | 0 | 11.9 | 0.0 | 55 | 71377 | 71/371 | 927 | 0 |
| fifo_vis-hint-1 | **proved** | 5 | 836 | 4 | 0 | 7.1 | 0.0 | 26 | 39238 | 64/155 | 445 | 0 |
| fifo_vis-hint-2 | open | 7 | 1753 | 3 | 30 | 7.0 | 1.6 | 65 | 149534 | 42/198 | 1496 | 0 |
| fifo_vis-hint-3 | **proved** | 1 | 27 | 0 | 0 | 0.0 | 0.0 | 1 | 972 | 12/12 | 12 | 0 |
| fifo_vis-nohint-1 | **proved** | 5 | 371 | 2 | 0 | 5.1 | 0.0 | 8 | 8726 | 34/62 | 102 | 0 |
| fifo_vis-nohint-2 | **proved** | 5 | 273 | 2 | 0 | 2.3 | 0.0 | 5 | 17773 | 49/156 | 195 | 0 |
| fifo_vis-nohint-3 | **proved** | 4 | 579 | 1 | 0 | 1.9 | 0.0 | 3 | 6044 | 34/58 | 67 | 0 |
| simple_cam_8-nohint-1 | open | 6 | 1221 | 5 | 0 | 11.0 | 0.0 | 29 | 59861 | 71/146 | 565 | 0 |
| simple_cam_8-nohint-2 | open | 6 | 1616 | 5 | 0 | 13.0 | 0.0 | 33 | 38289 | 88/324 | 705 | 0 |
| simple_cam_8-nohint-3 | open | 4 | 1415 | 5 | 0 | 9.2 | 0.0 | 31 | 75218 | 74/234 | 737 | 0 |

"open" = pieces still open at the end (out of rounds or budget). No run found a real counterexample.
fifo_vis-hint-3 proved in round 1 after the split plan alone (one LLM call, 16 pieces each proved by IC3).
The vacuity check of fifo_vis-nohint-2 hit its 1800 s limit (`vacuity.rc` = 124); the other 13 passed.
simple_cam_8-nohint-2, fifo_ref_16-hint-3 and fifo_vis-hint-3 first crashed on a gateway outage (HTTP 503, `no_available_provider`, see `chain.status`) and were rerun from scratch once the gateway was back.

## Old prompts vs short prompts, all 14 runs

| | old (`results/decide_fix`) | short |
|---|---|---|
| largest decide prompt | 57.1 KB | 13.0 KB |
| largest refine prompt | 233.8 KB | 14.4 KB |
| prompt text sent, all runs | 6900 KB | 593 KB |
| output tokens, all runs | 1.35 M | 1.13 M |
| LLM calls (decide / refine) | 174 (40 / 110) | 169 (47 / 78) |
| latency per call, median / p90 / max | 60 / 169 / 271 s (successful calls only) | 49 / 155 / 548 s |
| calls over 300 s | at least 4 (2 runs each ended after 2 timeouts) | 4 (all finished under the 600 s limit) |
| LLM time, all runs | 13219 s | 12442 s |
| proved | 5/14 | 5/14 |

| cell | old: proved | short: proved |
|---|---|---|
| fifo_ref_16 hint | 1/3 | 0/3 |
| fifo_vis hint | 2/3 | 2/3 |
| fifo_vis no hint | 2/3 | 3/3 |
| simple_cam_8 no hint | 0/3 | 0/3 |
| fifo_ref_64 hint | 0/2 | 0/2 |

## Findings

* **Prompts are 4-16x smaller,** and 12x smaller in total. The largest request is now 14 KB.
* **Prompt size was not what made requests slow.** Over the 174 old calls, latency tracks output tokens (correlation 0.98) and not prompt size (-0.02): about 100 output tokens per second, so a 25k-token answer takes about 250 s whatever the prompt. The short prompts did not shorten the answers much (1.35 M → 1.13 M output tokens) and mean latency stayed at about 75 s. The 4 calls over 300 s in this rerun had 17-23 KB prompts (system prompt included); three of them produced only 4-12k tokens, so the gateway itself was slow then (it also had an outage during this rerun). The earlier note "long decide prompts time out" (`results/decide_fix/README.md`) was wrong about the cause: the timeouts most likely came from long answers or a slow gateway, not from the prompt. The 600 s limit is what kept these 4 calls from ending their runs.
* **The proof rate did not change** (5/14 both times; the per-cell changes are within n=3 noise).
* **Refine loops are still the main failure.** 4 runs entered `cegar_refine` (78 calls in all) and none proved; 5 of the 10 runs without a refine loop proved. fifo_vis-hint-2 spent 30 refine calls, fifo_ref_64-hint-1 24.
* **The budget still does not cover LLM time:** fifo_ref_64-hint-1 ran 3929 s on an 1800 s budget, 3319 s of it in the LLM.

## Caveats

* n = 3 per cell (2 for fifo_ref_64); Mazu was shared with unrelated jobs, and the gateway had an outage mid-run.
* Old and new runs are on different days, so rIC3 and LLM times are not directly comparable.
* The old timed-out requests are not in `llm_calls.jsonl`, so the old latency figures cover successful calls only.
* Kept per run: `state.json`, `llm_calls.jsonl`, `deepseek_calls.jsonl`, `tool_events.jsonl`, wall/uptime/rc files and the count of timed-out requests (`llm_timeouts.txt`); rIC3 and build logs are not kept.
