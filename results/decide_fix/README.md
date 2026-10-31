# Reruns after the decide-quota fix

The `decide` prompt now lists only the pieces the LLM has to decide (pieces the tool already auto-split are marked "not yours to decide"), states how many new pieces are left this round (`MAX_NEW - counter`) and that an index split of b bits makes 2^b pieces. Extra ids in the answer are ignored; missing ids are named in the rejection.

Reran fifo_ref_64 (hint, budget 1800) twice and, 3 times each, the four ablation cells that had ended in `no valid answer to decide after 3 attempts` (budget 1200). Same machine (Mazu, shared, load 3-130), same model, run sequentially by `scripts/decide_fix_chain.sh`.

## Per run

| run | verdict | rounds | wall s | decide calls | cegar_refine calls | spurious CEX | LLM s | $ |
|---|---|---|---|---|---|---|---|---|
| fifo_ref_64-hint-1 | open | 6 | 2461 | 3 | 16 | 18 | 1794 | 0.68 |
| fifo_ref_64-hint-2 | llm_timeout | - | 2408 | 2 | 17 | 17 | 949 | 0.61 |
| fifo_ref_16-hint-1 | llm_timeout | - | 1161 | 2 | 0 | 0 | 338 | 0.06 |
| fifo_ref_16-hint-2 | **proved** | 7 | 793 | 3 | 0 | 5 | 359 | 0.05 |
| fifo_ref_16-hint-3 | open | 6 | 2018 | 4 | 17 | 17 | 1618 | 0.24 |
| fifo_vis-hint-1 | open | 3 | 2430 | 1 | 30 | 30 | 2403 | 0.32 |
| fifo_vis-hint-2 | **proved** | 4 | 123 | 1 | 0 | 1 | 92 | 0.01 |
| fifo_vis-hint-3 | **proved** | 6 | 633 | 3 | 0 | 0 | 266 | 0.04 |
| fifo_vis-nohint-1 | **proved** | 6 | 139 | 2 | 0 | 0 | 62 | 0.01 |
| fifo_vis-nohint-2 | open | 5 | 1635 | 1 | 16 | 15 | 1565 | 0.21 |
| fifo_vis-nohint-3 | **proved** | 6 | 618 | 4 | 0 | 8 | 316 | 0.04 |
| simple_cam_8-nohint-1 | open | 7 | 1816 | 7 | 0 | 6 | 894 | 0.12 |
| simple_cam_8-nohint-2 | open | 5 | 2098 | 5 | 19 | 25 | 1881 | 0.25 |
| simple_cam_8-nohint-3 | open | 7 | 1658 | 6 | 0 | 7 | 683 | 0.09 |

"open" = the flow ended with pieces still open (out of rounds or budget). "llm_timeout" = one LLM request exceeded 300 s twice. No run found a real counterexample.

## Same cells before and after

| cell | before: proved | stuck in decide | mean wall | after: proved | stuck in decide | mean wall |
|---|---|---|---|---|---|---|
| fifo_ref_16 hint | 1/3 | 1 | 910 | 1/3 | 0 | 1324 |
| fifo_vis hint | 2/3 | 1 | 984 | 2/3 | 0 | 1062 |
| fifo_vis no hint | 2/3 | 1 | 588 | 2/3 | 0 | 797 |
| simple_cam_8 no hint | 0/3 | 2 | 909 | 0/3 | 0 | 1857 |
| fifo_ref_64 hint | 0/2 | 2 | 362 | 0/2 | 0 | 2435 |

"Before" is `results/ablation_index_hint` and `results/adaptive_split_large`.

## Findings

* **The decide step no longer gets stuck.** 0 of 14 runs ended in `no valid answer to decide` (7 of 14 before). 44 decide calls, 1 rejected (`the operator list is unchanged`, accepted on the next try); before, most runs had 2-5 rejections.
* **The proof rate did not change** (5/12 on the same cells, 0/2 on fifo_ref_64). The runs now get further and fail later, which is why mean wall went up.
* **Abstraction refine loops are the new main failure.** 6 of 14 runs entered `cegar_refine` (4 of the 12 small-cell runs, vs 3 of 12 before, with 82 refine calls vs 25); none of those 6 proved, while 5 of the 8 runs without a refine loop did. The LLM's abstractions are almost always `abstract_state` on whole FIFO memory slots (`sr_mem_*`, `fv_env_ref_fifo_*`), which the proof needs, so every piece comes back SAT and spurious, and each refine is one more LLM call (fifo_vis-hint-1: 30 calls, 2403 s of LLM time).
* **Long decide prompts time out.** With 32 timed-out pieces the decide prompt is 60-75 KB (refine requests 180-250 KB). One fifo_ref_16 decide took 589 s; the next exceeded 300 s twice and ended the run. 2 runs ended this way.
* **The budget does not cover LLM time,** so 1200 s runs took up to 2098 s and 1800 s runs up to 2461 s.

## Caveats

* n = 3 per cell (2 for fifo_ref_64); Mazu was shared with unrelated jobs.
* Before/after are different days and machine loads; rIC3 times are not directly comparable.
* Logs: rIC3 logs and the fifo_ref_64 `state.json` are gzipped.
