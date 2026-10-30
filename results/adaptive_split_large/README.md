# Adaptive split flow on larger instances (Experiment B)

simple_cam_16 and fifo_ref_64, index hint on, DeepSeek `deepseek/deepseek-v4.1-flash`, rIC3 4d63899 on Mazu (32 cores), `--budget 1800`, 8 parallel pieces, 1 run each (fifo_ref_64 twice). Run after both fixes in `src/case_study.py` (300 s LLM timeout with one retry; `budget_exhausted` TypeError). Same soundness checks as before: SAT-coverage of every split, class-A operators only, vacuity check on the concrete model.

| run | wall (s) | rc | LLM calls | pieces | result | Mazu load (start / end) |
|---|---|---|---|---|---|---|
| simple_cam_16 | 210 | 0 | 2 | 60 (32 leaves) | PROVED, all leaves UNSAT, `unresolved: none` | 4.1 / 12.7 |
| fifo_ref_64 run 1 | 309 | 1 | 6 | 80 | UNRESOLVED: `no valid answer to decide after 3 attempts` | 11.2 / 24 |
| fifo_ref_64 run 2 | 414 | 1 | 7 | 80 | UNRESOLVED: same failure (36 split, 24 timeout, 16 open, 4 proved) | 23.7 / 6.1 |

## Questions

* **Does the LLM ever choose `abstract` or `both`?** No. Across all three runs the only operation was `resplit`; on fifo_ref_64 it resplit on the `fv_env_ref_fifo_head` index bits, which looks reasonable. With 2 calls on simple_cam_16 there was no decision that needed an abstraction.
* **Does abstraction help?** Not measurable: never used. Control instead: `split-only` on the same simple_cam_16 leaves (120 s cap, no LLM, no abstraction) proves every leaf (UNSAT, at most 8 s each), and the vacuity check passes. So simple_cam_16 needs only the index split. The abstraction question stays open for fifo_ref_64.
* **Why does fifo_ref_64 fail?** Not by hardness alone. Both runs end in `decide` being rejected 3 times: the LLM proposes N new pieces without counting the 16 pieces the tool's own `auto` index expansion already made (limit MAX_NEW=32 per round), or its piece list does not match the pending pieces. This is a method/prompt limitation, not a rIC3 timeout.
* **Would operator 8 (k symbolic slots) have been needed?** Reasoned, not tested. For simple_cam_16 no: the index split is enough. For fifo_ref_64 it might avoid enumerating 64 slots (24 pieces timed out at the 20 s cap), but the run never reached a point where this could be tried, so it is a hypothesis.

## Limitations

* n=1 per instance (2 for fifo_ref_64); no variance estimate.
* Mazu was shared with other users' jobs. The fifo_ref_64 run 1 control and vacuity check ran at load 130, so its 120 s control timeouts on every leaf are contaminated and are not reported as evidence; run 2 has no control or vacuity run (it failed before them).
* fifo_ref_64 was not solved, so nothing here says whether abstraction would solve it.
* LLM latency matters: simple_cam_16 spent 135 s of its 210 s in the LLM ($0.034).
