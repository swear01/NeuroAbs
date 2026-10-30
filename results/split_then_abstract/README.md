# Split on the source of hardness, then abstract: hand-made check (Phase 1 of issue #23)

No LLM. Script: `run.py` (imports `src/case_study.py` unchanged: piece = case condition in the assertion, coverage by Yosys `sat -prove`, class-A ops via Yosys `abstract`). Run on Mazu 2026-10-30 in `/var/tmp/neuroabs-runtime/split-abs-20261030/`; rIC3 master 4d63899 `portfolio`, 300 s cap, at most 4 runs at once. Raw CSVs and logs are in `raw/`.

**Mazu was heavily loaded by an unrelated job (load average 12-100, 32 cores).** Absolute times are inflated and noisy; only variants run in the same batch under similar load are compared. `load1` in the newer CSVs is the load average when the piece finished. Every variant of every experiment finished UNSAT; no rIC3 run hit the cap and **no SAT occurred except the deliberately over-aggressive variant c**.

## 1. fifo_vis, piece c6 (both FIFOs non-empty, flags equal, data differ)

c6 = `!rst & !srEmpty & !rbEmpty & (srFull==rbFull) & (srDataOut!=rbDataOut)`. Splits are coverage-checked (SAT, passed).

| Variant | Pieces | Verdicts | Per-piece time (mean / max) | Sum of times | Spurious CEX | Batch / load |
|---|---|---|---|---|---|---|
| w: whole c6, no split | 1 | UNSAT | 137.3 s | 137.3 s | - | rerun3, load ~26 (earlier batch rerun2: 144.5 s at load ~32; the old known value is 92.3 s) |
| a: split on `rb_tail`, no abstraction | 16 | 16 UNSAT | 5.3 / 11 s | 85 s | - | rerun3, load ~37, 1 job |
| a (again) | 16 | 16 UNSAT | 8.9 / 12 s | 142 s | - | rerun2, load ~55 |
| a (first pass) | 16 | 16 UNSAT | 6.7 / 9 s | 106 s | - | first pass, 4 at a time |
| b: a + other 15 `rb_mem_j` freed (`abstract_state`) | 16 | 16 UNSAT | 8.7 / 14 s | 140 s | - | rerun2 (same batch as a: 8.9 s), load ~56 |
| b (first pass) | 16 | 16 UNSAT | 6.6 / 10 s | 106 s | - | first pass (same batch as a: 6.7 s) |
| f: a + other `rb_mem_j` cut with `abstract_value` | 16 | 16 UNSAT | 6.7 / 9 s | 107 s | - | rerun3 (same batch as a: 5.3 s), load ~31 |
| c: b + all 16 `sr_mem_j` freed | 16 | 16 **SAT** at 0.0-0.2 s | - | 2 s | **yes, 16/16** (replay on the concrete model: not real) | first pass |
| d: split on `sr_tail`, no abstraction | 16 | 16 UNSAT | 59 / 132 s (first pass 77 / 150 s) | 944 s | - | rerun, d and e together, 2 jobs each |
| e: d + `sr_mem_j` for j > s freed | 16 | 16 UNSAT | 61 / 130 s (first pass 62 / 115 s) | 983 s | - | same batch as d |

Reading:
- **Split on rb's read pointer works as a split**: one 137 s proof becomes 16 proofs of 5-14 s each (each piece ran with a rIC3 portfolio on its own; wall time 12-15 s per piece). Note the sum of piece times (85-142 s) is about the same as the whole proof, so the gain is parallelism and per-piece cap behavior, not less total work.
- **Freeing rb's other 15 slots is sound for this piece but gives no speed-up** (b vs a: 8.7 vs 8.9 s, 6.6 vs 6.7 s; f vs a: 6.7 vs 5.3 s, within noise). The freed slots are not needed for the invariant (it only relates `rb.mem[tail]` to the shift-register contents), so the explicit abstraction is valid but rIC3 did not get faster.
- **sr cannot be treated the same way**. Freeing all of sr's memory (c) is spurious in every piece: the sr side has to hold the value that is later compared. Splitting on sr's pointer (d) is worse than splitting on rb's (59 s vs 5-9 s per piece) because the matching rb slot varies. Freeing the sr slots above the tail (e) is sound by construction (data only moves upward in the shift register, so slots above `sr_tail` cannot reach slot `sr_tail`) and was confirmed UNSAT, but it also did not speed up (61 vs 59 s).

## 2. lrg_arb (`llmm-lrg_arb_lrg_16_ebmc`), both arbitrary requesters fixed

Piece = `chosen & arbitrary_requester==i & another_arbitrary_requester==j`; 8 sample pairs (adjacent (0,1), (1,0), (3,4), (7,8); far (0,15), (15,0), (2,11), (12,5)). These are samples, not a cover.

| Variant | Pieces | Verdicts | Time per piece | Spurious CEX |
|---|---|---|---|---|
| so: split only | 8 | 8 UNSAT | 0.1-0.2 s | - |
| free: also the other 14 `ranks_k` freed (`abstract_state`) | 8 | 8 UNSAT | 0.1-0.2 s | none |
| freev: same with `abstract_value` | 8 | 8 UNSAT | 0.1-0.2 s | none |

Fixing both indices already makes each piece trivial (0.1-0.2 s versus ~2 s per piece when only the grant/request cases were split in the case study, and 281 s for the whole property). Freeing the other 14 ranks is sound and changes nothing visible.

## Verdict

- **Split on the symbolic index/slot: holds.** Both designs go from a hard invariant over all slots to pieces that rIC3 proves quickly (fifo c6: 137 s -> 5-14 s per piece; lrg_arb: ~2 s -> 0.1-0.2 s per piece).
- **Split-then-abstract (freeing what the piece no longer references): sound, but no measurable gain in either design.** No spurious counterexample appeared for the references that really are dead, so the hypothesis "the dropped state is no longer needed" is correct; the hypothesis "dropping it makes rIC3 faster" is not supported here.
  - fifo_vis: the invariant needs the sr contents (all of them, as shown by the 16/16 spurious in c) plus the one rb slot at `rb_tail`; the other 15 rb slots are not needed but also do not slow rIC3 down.
  - lrg_arb: the invariant needs only the ordering/distinctness of the two selected ranks. The rank update (`x<cp: x; x==cp: 15; x>cp: x-1`) is injective on 0..15, so distinctness is preserved whatever the other ranks and `chosen_priority` are; this is why the other 14 ranks are not needed and also why the piece is already trivial.
- Caveat on the operator, relevant to Phase 2: Yosys `abstract -state/-value -enable __one` adds state rather than removing it (lrg p0_1: 24 states split-only, 52 with `abstract_state`, 38 with `abstract_value`; fifo c6_t3: 53 vs 68, input count unchanged). So the abstraction as implemented does not shrink the model; a real cut (register output replaced by a fresh input, register deleted) would be needed to test "fewer state bits". That test was not done here.
- Phase 2 consequence: for these two designs the split is the lever; adding the abstraction round costs LLM time (about 50 s per round in the case studies) for no gain. Only worth it if a design is found where rIC3 times out on the split pieces and the dropped state is large.

## Files

`run.py`, `raw/first_pass/` (fifo a b c d e), `raw/rerun_de/` (fifo d e repeat), `raw/rerun2_wab/` (fifo w a b), `raw/rerun3_waf/` (fifo w a f), `raw/lrg/` (so, free, freev). Each directory has `results_*.csv` and the run logs with per-piece rows.
