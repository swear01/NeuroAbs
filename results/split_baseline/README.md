# Split-only baseline for the Piccolo ILA sub-properties (rIC3)

Status on 2026-10-27: the property split of
[`fine_gpr_choices`](../fine_gpr_choices/README.md) is treated as
preprocessing that every arm gets, and the RTL abstraction is measured against
the same sub-properties on the unabstracted model ("split-only").

- ADDI write cases (`xk.rs1=r`, r ≠ 0) are proved only with the abstraction:
  split-only proves 1 of 32 in 300 s (`rs1 = 0`), and none of four in
  1800 s; the structural rule S proves 32 of 32. Without the operator UF, S
  also proves only the `rs1 = 0` case.
- Everywhere both prove a sub-property, S is faster: median 5.1–7.7 times per
  instruction in one run, 6.0 (LUI) and 6.2 (JAL) times in three alternating
  repeats, whose round totals vary by at most 2 %.
- LUI, AUIPC and JAL write cases and the frame cases are within reach of
  split-only (proved, or proved in another core/load setting near the 300 s
  limit); there the abstraction is a speed-up, not the difference between
  proof and no proof.
- DeepSeek on the fine menu is 3.4–6.8 times faster than split-only (median)
  and proves 60 / 64, 62, 63 and 62 / 63; auto CEGAR is not faster than
  split-only (median 0.6–1.0).

## Design

A split-only spec keeps `states`, `case` and `rd_guard` of the S spec of the
same sub-property and drops every choice (`scripts/make_specs.py ... split`):
all units and GPRs are kept, no UF. It is built and checked by the same
`src/fine_batch.py` as the arms of `fine_gpr_choices`, with the same
`units.json`, 300 s per model and no refinement (there is nothing to refine).
Each case runs on the CPU group of its S arm: ADDI on E-cores 24–25 / 26–27,
JAL on E 28–29 / 30–31, LUI and AUIPC on P 12–13 / 14–15.

| Arm | Sub-properties | Spec | Limit | Refinements |
| --- | --- | --- | --- | --- |
| split | ADDI sample (64), LUI, AUIPC, JAL (63 each) | S spec without choices | 300 s | 0 |
| no-uf | the 32 ADDI sample write cases | S spec with `uf: []` | 300 s | up to 10 |
| split-long | ADDI `x12.rs1=1`, `x19.rs1=2`, `x26.rs1=3`, `x2.rs1=4` | as split | 1800 s | 0 |
| rep-split-i / rep-s-i, i = 1..3 | LUI and JAL: `mem`, `x1`, `x5`, `x17` frame and write | split / S spec | 300 s | 0 / up to 10 |

The repeats alternate split and S rounds on one CPU group (`repeat.sh`), so
both see the same machine load. The S, DeepSeek and auto records are those of
`fine_gpr_choices/piccolo/<case>/`, run on 2026-10-26 with the same settings;
the split arms ran 2026-10-26 22:47 to 2026-10-27 02:45 while another session
shared the machine.

## Results

### Split-only

| Case | `UNSAT` | frame | `mem` | write | Time s | rIC3 s | Median s | COI bits |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: |
| ADDI (sample) | 19 / 64 | 17 / 31 | 1 / 1 | 1 / 32 | 18,221 | 17,851 | 314 | 5,163 |
| LUI | 61 / 63 | 29 / 31 | 1 / 1 | 31 / 31 | 8,345 | 8,042 | 108 | 5,163 |
| AUIPC | 63 / 63 | 31 / 31 | 1 / 1 | 31 / 31 | 6,609 | 6,467 | 97 | 5,163 |
| JAL | 53 / 63 | 21 / 31 | 1 / 1 | 31 / 31 | 11,869 | 11,528 | 174 | 5,163 |

Every result that is not `UNSAT` is `TIMEOUT` without a counterexample (deepest
BMC bound 20–65, IC3 frame 10–18). The proved split-only frame cases take
101–308 s, so the frame `TIMEOUT`s are at the edge of the limit: with 300 s on
E-cores under load, ADDI and JAL lose 14 and 10 frame cases that LUI and AUIPC
(P-cores) mostly prove. They are not counted as cases that need the
abstraction.

### Paired with the abstraction arms

Same sub-properties, one run each. "Both" counts the sub-properties both arms
prove; the speed-up is split-only time / arm time on those, including the
Yosys build.

| Case | Arm | `UNSAT` arm / split | Time s arm / split | Both | Median speed-up | Geometric mean | Min |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| ADDI | S | 64 / 19 | 2,627 / 18,221 | 19 | 7.7 | 7.5 | 4.4 |
| ADDI | DeepSeek | 60 / 19 | 3,805 / 18,221 | 19 | 6.8 | 6.6 | 3.6 |
| ADDI | auto | 34 / 19 | 23,893 / 18,221 | 19 | 1.0 | 0.9 | 0.5 |
| LUI | S | 63 / 61 | 934 / 8,345 | 61 | 7.7 | 7.9 | 2.0 |
| LUI | DeepSeek | 62 / 61 | 2,005 / 8,345 | 60 | 4.5 | 4.7 | 1.2 |
| AUIPC | S | 63 / 63 | 1,204 / 6,609 | 63 | 5.1 | 5.1 | 1.8 |
| AUIPC | DeepSeek | 63 / 63 | 1,828 / 6,609 | 63 | 3.4 | 3.4 | 1.1 |
| JAL | S | 63 / 53 | 1,608 / 11,869 | 53 | 6.8 | 6.3 | 2.8 |
| JAL | DeepSeek | 62 / 53 | 2,243 / 11,869 | 53 | 6.1 | 5.9 | 2.4 |

auto on the seven sampled LUI, AUIPC and JAL sub-properties: 7 / 7 `UNSAT` like
split-only, median speed-up 0.8, 0.6 and 1.0. Median final COI: split 5,163
bits, S and DeepSeek 788–1,012, auto 2,189–2,382 (it restores the units).

ADDI by kind (S / split-only): frame 31 / 17, `mem` 1 / 1, write 32 / 1. The
one split-only write proof is `x5.rs1=0` (154 s; S 13 s), where the adder adds
the immediate to the constant zero.

### UF ablation and long limit (ADDI write cases)

| Arm | `UNSAT` / 32 | Time s | COI bits | deepest BMC / IC3 frame of the `TIMEOUT`s |
| --- | ---: | ---: | ---: | --- |
| split-only | 1 | 9,877 | 5,163 | 20–30 / 10 |
| S without UF | 1 (`x5.rs1=0`, 14 s) | 9,568 | 788–884 | 81–130 / 7 |
| S | 32 | 1,727 | 981–1,077 | — |

The four split-only write cases with 1800 s all `TIMEOUT` (1,812–1,814 s, BMC
130, IC3 frame 10). Without the UF, the S abstraction cuts the model to under
900 bits, BMC goes deeper, but IC3 stays at frame 7 and no case with a register
operand is proved: the GPR and unit cuts and the UF are needed together, as
screens B, F, H2 and P of `fine_gpr_choices` suggested on one case.

### Repeated timing (LUI, JAL)

Three rounds, each split-only on the seven sub-properties, then S on the same
seven, CPU group P 12–15 (LUI) and E 28–31 (JAL).

| Case | Round totals split-only s | Round totals S s | `UNSAT` split / S | Per sub-property median speed-up |
| --- | --- | --- | --- | --- |
| LUI | 770, 774, 784 | 108, 109, 108 | 7 / 7 each round | 6.0 (3.6–15.5) |
| JAL | 1,148, 1,143, 1,136 | 185, 187, 186 | 6 / 7 each round | 6.2 (2.8–12.8; `x1.frame` split `TIMEOUT` each round) |

Round totals vary by at most 2 %; the widest spread of one sub-property is
split-only JAL `x1.write` (103–134 s) and LUI `x5.write` (33–40 s).

## Conclusions

1. **The split is preprocessing; the abstraction is the contribution.** On
   the same sub-properties, the RTL abstraction (unit cut, GPR keep/word/havoc,
   Ackermann UF) chosen by the structural rule makes the ADDI write cases
   provable (32 / 32 versus 1 / 32 in 300 s and 0 / 4 in 1800 s) and is about
   6–8 times faster where split-only also proves (LUI, AUIPC, JAL; repeated
   6.0 and 6.2 times).
2. **The UF is necessary for ADDI.** S without the UF proves only the
   `rs1 = 0` write case.
3. **LLM choice beats auto CEGAR, not the structural rule.** DeepSeek is 3.4–6.8
   times faster than split-only and proves almost everything; auto CEGAR is
   no faster than split-only, because it refines back towards the concrete
   model. S is faster than DeepSeek in every case.

## Not done and risks

- Only the ADDI sample (64 of 1,024 sub-properties) has a split-only run; the
  full ADDI proof was not repeated without abstraction.
- The frame `TIMEOUT`s depend on the core type and load at the 300 s limit;
  no frame case was run with a longer limit.
- The repeats cover 14 sub-properties of LUI and JAL; ADDI and AUIPC have one
  run each.
- The split arms ran about half a day after the S, DeepSeek and auto arms,
  with a different machine load; the repeats, which alternate split and S,
  give the same speed-ups.

## Reproduction

The scripts in [`scripts/`](scripts) ran in the run directory
`/var/tmp/neuroabs-runtime/runs/split-baseline-20261026` with the `units.json`
of `/var/tmp/neuroabs-runtime/runs/fine-gpr-20261026`; each sources
`/var/tmp/neuroabs-runtime/env-20261024.sh`. `make_specs.py` derives the
split and no-uf specs from `fine_gpr_choices/piccolo/<case>/specs-structural*.jsonl`
(for no-uf with name part `rs1=`); the split-long and rep specs are the named
lines of the split and S specs. `arm.sh` runs one arm with `src/fine_batch.py`,
`queue.sh`, `long.sh` and `repeat.sh` are the order of the runs, `compare.py
<split> <arm>...` gives the paired tables and `repeats.py piccolo/<case>` the
repeat table. Records (one line per sub-property) are in
`piccolo/<case>/arm-*.jsonl`, specs in `piccolo/<case>/specs-*.jsonl`.
