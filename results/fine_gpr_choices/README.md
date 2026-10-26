# Sub-properties and register-level choices on the Piccolo ILA property (rIC3)

Status: the Piccolo ADDI, LUI, AUIPC and JAL ILA properties are proved with
rIC3 after splitting each into sub-properties and choosing per sub-property
among unit cut, GPR keep/word/havoc and an Ackermann UF on the adder. B0 and
the coarse menu of PR #14 time out on all of them. The split is preprocessing;
[`split_baseline`](../split_baseline/README.md) measures the abstraction
against the same sub-properties on the unabstracted model. DeepSeek on the
fine menu is much faster than all-cut CEGAR, but a simple structural rule (no
LLM) is as good or better everywhere.

## Why the coarse menu is not enough

In [`flute_piccolo_choices`](../flute_piccolo_choices/README.md) the menu has
one choice per module instance (keep, havoc, cut). On Piccolo ADDI ILA no
assignment of that menu has a verdict within one hour; the GPR file must be
kept and the property compares all 31 GPRs. The ILA wrapper ties the two
models together with recorders: `__auxvarN__recorder` is a free constant that
an assumption equates with the RTL register `arr_j` when the instruction is in
stage 3 (`post_value_holder`), and at `__START__` an assumption sets the ILA
state `xj` to that recorder (`variable_map_assume`). The ILA executes the
instruction at `__START__`; at `__IEND__` the assertion compares the ILA
state with the RTL registers.

## Design

All options are rewrites of the wrapper or Yosys cut points, built by
`src/fine_choice.py`, checked with the rIC3 portfolio and refined with the
witness replay of PR #14 (`src/btor_witness.py`).

### Property split

`normalassert` is the conjunction of the `variable_map_assert` conjuncts. A
sub-property keeps some of them and may be restricted to a case, a condition
on the fields of the instruction that the ILA executes, latched at
`__START__` into an observer register `__split_inst__` (an observer adds no
behavior). The assertion of a sub-property with case `c` is `!c || p`.

`fine_choice.py split` lists the sub-properties for a wrapper:

| Sub-property | States | Case |
| --- | --- | --- |
| `mem` | `pc`, `load_en`, `store_en`, `x0` | every instruction |
| `xk.frame`, k = 1..31 | `xk` | `rd != k` |
| `xk.rs1=r`, r = 0..31 (ADDI, ANDI, SLTI) | `xk` | `rd == k && rs1 == r` |
| `xk.write` (LUI, AUIPC, JAL) | `xk` | `rd == k` |

The source fields split on are those that the ILA module reads (`inst[19:15]`
for rs1, `inst[24:20]` for rs2). For every k the cases `rd != k` and
`rd == k && rs1 == r` for r = 0..31 cover every instruction, and every conjunct
of the original assertion is in some sub-property, so the original property
holds when every sub-property holds. ADDI has 1 + 31 + 31 × 32 = 1,024
sub-properties; LUI, AUIPC and JAL have 1 + 31 + 31 = 63.

### Choices per sub-property

| Choice | Levels | Meaning |
| --- | --- | --- |
| unit (`csr_regfile`, `near_mem_dcache`, `near_mem_icache`) | keep, cut | as in PR #14: every output of the instance is a free value in every cycle |
| `gprj`, j = 0..31 | keep, word, havoc | havoc: the register file word `arr[j]` and the ILA state `xj` are free values in every cycle, and every assumption that refers only to removed GPRs (through `xj`, `arr_j` or the recorder of `arr_j`) is dropped; word: the word and the ILA state stay, the assumptions about `xj` are dropped |
| `uf0` | keep, uf | the ILA operator and the RTL operator that compute the instruction result are abstracted by one uninterpreted function (below) |

The GPR file unit of PR #14 is replaced by the 32 `gprj` choices. Word cuts
are Yosys `cutpoint`s of the mapped memory word wires after `memory`, and of
the ILA registers after `flatten`. The free values are named
`choice__gpr_wj__n`, `choice__ila_xj__n`, `choice__uf0__n`, so that the
witness replay attributes a counterexample to its choices.

Soundness: a cut point replaces a driver by a free value, which includes the
original value. Dropping an assumption removes a constraint. Both keep every
behavior of the concrete model, so a proof of a sub-property on the abstract
model is a proof on the concrete model.

### Operator abstraction by an uninterpreted function

`uf0` pairs an ILA node such as ADDI's `n110 = n107 + n109` with the RTL ALU
node `rd_val___1__h6550 = rs1_val_bypassed__h3337 + _theResult___snd__h7382`.
Both results become free values in every cycle. At `__START__`, the wrapper
latches both operand pairs and both results (the tracked instruction executes
in stage 1 exactly at `__START__`, because `s2_enter` requires `monitor_s1`,
which requires `__START__`). A new assumption requires equal results when the
latched operands are equal (Ackermann's constraint), guarded by a flag set at
`__START__` and cleared by `rst`.

Soundness: in a concrete trace the free results take the true values, so
every latched result is the operator applied to the latched operands and the
assumption holds. `rst` is a free input of the BTOR2 model and a trace can
contain several `__START__`s; the latches are rewritten at each one, so the
argument holds for every `__START__`. A first version that gave the RTL result
the ILA value directly when the operands matched was correct but did not
help (screen H below); a version that used a free constant for the ILA value
would have been unsound with several `__START__`s and was not run.

Why it helps: the recorder that the ILA reads at `__START__` is only equated
with the RTL register two cycles later. With the adder in place, IC3 must
learn a relation of the form `rd_val - imm == arr_r` in the future, which in
clauses over bits needs the carry chain. With the uninterpreted function, every
lemma needed is an equality between latched words.

The pairs are chosen by hand per instruction and must have the same operator
(checked by `operator_args`): ADDI `n110` / `rd_val___1__h6550`, ANDI `n110` /
`_theResult_____1_fst__h6597`, AUIPC `n14` / `rd_val__h5537`, JAL `n20` /
`alu_outputs___1_val1__h5386`. SLTI has none, because the RTL computes the
comparison as a conditional expression.

### Arms

| Arm | Choice per sub-property | Refinement |
| --- | --- | --- |
| B0 | concrete model, whole property | — |
| coarse DeepSeek (PR #14) | module-level menu, whole property | one refinement → csr cut, dcache cut |
| auto | every unit cut, every GPR havoc, `uf0` uf | CEGAR, refine one: the choice with most free values in the counterexample |
| S | structural rule, no LLM: keep the GPRs that the sub-property compares or that its case names as rs1; the compared rd of a write case at word level; every unit cut; `uf0` uf | as auto |
| DeepSeek | DeepSeek V4 Flash, one call per sub-property | as auto |

A `TIMEOUT` of a model is final: it gives no counterexample to refine.

`src/fine_choice_llm.py` sends `src/fine_choice_context.txt` as the system
prompt. The message holds the case description, the 36 choices (three units, 32 GPRs, one operator pair) with levels,
the unit outputs and the operator pair, then the sub-property's assertion and
case; the shared part comes first, so that the gateway caches it. The answer
is the strict JSON of `choice_llm.py`. Calls go through the local gateway as
`deepseek-flash` (served `deepseek/deepseek-v4.1-flash`), reasoning effort
low.

## Environment

As in PR #14: Mazu (i9-14900K), Yosys 0.68+120, rIC3 master `8c6df1b`, default
portfolio, `--cex`; a time-limit panic is recorded as `TIMEOUT`. Every model
here is run with `taskset` on two logical CPUs: P-cores 12–13 or 14–15
(screens, and parts p and e2 of the full proof) or E-cores 24–25, 26–27, 28–29
or 30–31 (sample arms, part e1). Up to four such runs share the machine with
another session, so times are comparable within a table, not with the 16-core
times of PR #14. "Build" is the two Yosys passes; "time" is build + rIC3 +
witness replay. LLM time is listed separately.

## Results: Piccolo ADDI ILA

### Screens

300 s limit, one run, P-cores unless noted. `csr`/`dc`/`ic`: CSR file,
D-cache, I-cache; "keep {5,6}" means only those GPRs are kept, all others
havoc. Raw records: `piccolo/ADDI/screen-*.json`.

| Id | Sub-property | Abstraction | Verdict | rIC3 s | COI bits | deepest BMC / IC3 frame |
| --- | --- | --- | --- | ---: | ---: | --- |
| P | `x5.frame` | none | `UNSAT` | 143 | 5,163 | 20 / 10 |
| P | `mem` | none | `UNSAT` | 122 | 5,131 | 30 / 11 |
| P | `x5.rs1=6` | none | `TIMEOUT` | 306 | 5,163 | 65 / 10 |
| P | `x5.rs1=6` | `uf0` only | `TIMEOUT` | 306 | 5,356 | 40 / 10 |
| A | `x5.frame` | keep {5}, csr dc cut | `UNSAT` | 20 | 1,194 | 21 / 10 |
| C | `x5.rs1=0` | keep {5}, csr dc cut | `UNSAT` | 13 | 1,194 | 18 / 10 |
| B | `x5.rs1=6` | keep {5,6}, csr dc cut | `TIMEOUT` | 302 | 1,291 | 130 / 10 |
| F | `x5.rs1=6` | as B, 1500 s | `TIMEOUT` | 1502 | 1,291 | 297 / 10 |
| D | `x5.rs1=5` | keep {5}, csr dc cut | `TIMEOUT` | 302 | 1,194 | 73 / 10 |
| E | `x5.rs1=6` and `imm == 0` (diagnostic) | as B | `UNSAT` | 98 | 1,291 | 65 / 15 |
| H | `x5.rs1=6` | as B, first UF version | `TIMEOUT` | 302 | 1,387 | 81 / 10 |
| H2 | `x5.rs1=6` | as B, `uf0` | `UNSAT` | 51 | 1,484 | 26 / 10 |
| M | `x5.rs1=6` | as H2, one E-core | `UNSAT` | 113 | 1,484 | 26 / 10 |
| K | `x5.rs1=5` | keep {5}, csr dc cut, `uf0` | `UNSAT` | 88 | 1,387 | 65 / 10 |
| L | `x31.rs1=1` | keep {1,31}, csr dc cut, `uf0` | `UNSAT` | 62 | 1,484 | 30 / 10 |
| I | `x5` with `rd == 5`, any rs1 | all GPRs, csr dc cut, `uf0` | `TIMEOUT` | 303 | 4,361 | 65 / 10 |
| N | x1..x31, each required when it is rd, `rs1 == 6` | as I | `TIMEOUT` | 303 | 4,361 | 65 / 10 |
| N2 | as N | keep {6}, others word, csr dc cut, `uf0` | `TIMEOUT` | 303 | 4,299 | 65 / 10 |
| J | whole property | all GPRs, csr dc cut, `uf0` | `TIMEOUT` | 328 | 4,329 | 20 / 10 |
| Q | whole property | as J, 1800 s, P-cores 12–15 | `TIMEOUT` | 1806 | 4,329 | 140 / 10 |
| G2 | `mem` | keep none, csr dc cut, CEGAR | `UNSAT` after 3 refinements (csr, dc, x0) | 331 | 2,124 | — |

What the screens show:

- The case split alone removes the frame part of the difficulty: `x5.frame`
  and `mem` are proved on the unabstracted model in about two minutes,
  although B0 (the whole property) has no verdict in an hour (PR #14).
- Write cases with a register operand stay out of reach whatever GPRs are
  removed, even for 1500 s (F), and are proved as soon as `imm == 0` (E) or
  `rs1 == 0` (C): the adder relation is the obstacle. The UF option removes
  it (H2, K, L), but only together with the GPR reduction: on the full model
  `uf0` alone times out (P).
- The rs1 split is needed: one write case for all rs1 (I), or one per rs1 for
  all rd (N, N2), time out, also with the word level, because each compared
  GPR conjunct references its recorder. The whole property with `uf0`, CSR
  and D-cache cut times out also after 1800 s (Q, BMC 140, IC3 frame 10):
  the UF needs the split.

### Sample: auto, structural rule and DeepSeek

64 sub-properties: `mem`, the 31 frame cases and 32 write cases
`x((7r + 4) mod 31 + 1).rs1=r`, r = 0..31. 300 s per model, at most 10
refinements, E-cores.

| Arm | `UNSAT` | `TIMEOUT` | Refinements | Time s | Build s | rIC3 s | Median s | Median final COI bits | LLM |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| auto | 34 | 30 | 315 | 23,893 | 3,614 | 20,193 | 316 | 2,350 | — |
| S (structural) | 64 | 0 | 1 | 2,627 | 601 | 2,026 | 40 | 1,012 | — |
| DeepSeek | 60 | 4 | 1 | 3,805 | 647 | 3,158 | 39 | 981 | 64 calls, 2,465 s, $0.47 |

By kind:

| Arm | frame (31) | `mem` | write (32) |
| --- | --- | --- | --- |
| auto | 31 `UNSAT`, 123 refinements, 6,989 s | `UNSAT`, 4 refinements, 208 s | 2 `UNSAT`, 30 `TIMEOUT`, 188 refinements, 16,696 s |
| S | 31 `UNSAT`, 0 refinements, 854 s | `UNSAT`, 1 refinement (I-cache), 47 s | 32 `UNSAT`, 0 refinements, 1,727 s |
| DeepSeek | 31 `UNSAT`, 0 refinements, 956 s | `UNSAT`, 1 refinement (I-cache), 57 s | 28 `UNSAT`, 4 `TIMEOUT`, 0 refinements, 2,791 s |

- auto restores the I-cache, the CSR file and the D-cache in every frame case
  (the dynamic cone counts their free values first), then the compared GPR.
  In 30 of 32 write cases, once the units are back, the UF has the most free
  values in the counterexample and is refined away; the model with the adder
  then times out (deepest BMC bound 40–65, IC3 frame 10). Its two proofs are
  `rs1 = 0` cases.
- DeepSeek cuts all three units in every sub-property, keeps the compared GPR
  in frame cases and x0 in `mem`, and keeps the rs1 register in write cases.
  55 of 64 answers equal the structural rule. Five keep rd at keep instead of
  word (all `UNSAT`). Four keep the adder (`uf0` keep); all four time out
  (BMC 65–69, IC3 frame 7), and a `TIMEOUT` gives no counterexample to
  refine.
- Both choose the I-cache cut for `mem`; one refinement restores it.

### Full proof of ADDI

Every sub-property is checked: the 64 of the sample with the structural rule
(above) and the other 960 write cases with the same rule (`xk.rs1=r`: keep
{r}, rd at word level, every unit cut, `uf0`), 300 s limit, CEGAR on
(`piccolo/ADDI/arm-full-*.jsonl`).

| Part | Sub-properties | CPUs | `UNSAT` | Refinements | Time s | Build s | rIC3 s | Median s | Max s |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| sample (S) | 64 | E 24–27 | 64 | 1 | 2,627 | 601 | 2,026 | 40 | 72 |
| p: rd 1–8 | 247 | P 12–15 | 247 | 0 | 9,416 | 1,420 | 7,996 | 38 | 78 |
| e1: rd 9–20 | 372 | E 28–31 | 372 | 0 | 17,246 | 3,295 | 13,952 | 46 | 81 |
| e2: rd 21–31 | 341 | P 12–15 | 341 | 0 | 10,423 | 1,488 | 8,935 | 31 | 48 |
| total | 1,024 | | 1,024 | 1 | 39,712 | | | | |

All 1,024 sub-properties are `UNSAT`, so the Piccolo ADDI ILA property holds.
The whole proof took 11.0 hours of two-CPU runs, with at most four in
parallel (wall time 2 h 52 min, 03:53–06:45, while the sample arms ran
alongside). B0 and the coarse DeepSeek model of PR #14 have no verdict in one
hour on 16 E-cores.

## Results: Piccolo LUI, AUIPC and JAL

These instructions have no register operand, so the split is `mem`, 31 frame
cases `xk.frame` and 31 write cases `xk.write` (`rd == k`): 63
sub-properties that together are the whole property. Every arm below is
therefore a full proof attempt. The structural rule keeps the compared GPR in
a frame case, x0 in `mem`, no GPR in a write case (rd at word level), cuts
every unit and turns on the operator pair (AUIPC `n14` / `rd_val__h5537`, JAL
`n20` / `alu_outputs___1_val1__h5386`; LUI has none). 300 s per model, at most
10 refinements. B0 is 1800 s on E-cores 24–25.

Screens (P-cores, units kept, only the named GPR kept): LUI `x5.write`
`UNSAT` 45 s; AUIPC `x5.write` with `uf0` `UNSAT` 68 s; JAL `x5.write`
`UNSAT` 42 s, with `uf0` 58 s.

| Case | Arm | CPUs | `UNSAT` / 63 | Not proved | Refinements | Time s | Build s | rIC3 s | Median s | Median final COI bits | LLM |
| --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| LUI | B0 | E 24–25 | — | `TIMEOUT` 1810 s, BMC 119 / IC3 10, 5,131 bits | — | 1,810 | | | | 5,131 | — |
| LUI | S | P 12–15 | 63 | — | 1 | 934 | 331 | 603 | 15 | 788 | — |
| LUI | DeepSeek | E 28–31 | 62 | `x30.frame`: max_iterations | 11 | 2,005 | 745 | 1,257 | 24 | 788 | 63 calls, 1,747 s, $0.35 |
| AUIPC | B0 | E 24–25 | — | `TIMEOUT` 1811 s, BMC 118 / IC3 10, 5,131 bits | — | 1,811 | | | | 5,131 | — |
| AUIPC | S | P 12–15 | 63 | — | 1 | 1,204 | 335 | 868 | 18 | 981 | — |
| AUIPC | DeepSeek | E 28–31 | 63 | — | 1 | 1,828 | 613 | 1,216 | 28 | 981 | 63 calls, 2,138 s, $0.43 |
| JAL | B0 | E 24–25 | — | `TIMEOUT` 1807 s, BMC 65 / IC3 10, 5,131 bits | — | 1,807 | | | | 5,131 | — |
| JAL | S | E 28–31 | 63 | — | 1 | 1,608 | 517 | 1,091 | 25 | 981 | — |
| JAL | DeepSeek | E 28–31 | 62 | `x15.frame`: max_iterations | 11 | 2,243 | 674 | 1,566 | 27 | 981 | 63 calls, 2,475 s, $0.49 |

So the LUI, AUIPC and JAL ILA properties hold (structural arm, all 63
`UNSAT`; for AUIPC also the DeepSeek arm). B0 has no verdict in 1800 s for
any of them.

- DeepSeek differs from the structural rule in 6 (LUI), 11 (AUIPC) and 7
  (JAL) sub-properties. Most differences are harmless: rd kept instead of
  word, or the AUIPC/JAL operator pair kept (AUIPC and JAL add a constant to
  the pc, which IC3 handles without the UF). All of those are `UNSAT`.
- The two failures are the same mistake: in a frame case DeepSeek put the
  compared GPR at word level. That drops the assumption that equates the
  ILA and RTL register at the start, so the counterexample is real for the
  abstract model; but the refinement first restores the units whose free
  values appear in it and stops after 10 refinements before promoting the
  GPR (`final_spec` in `arm-llm.jsonl`).

Auto on seven sub-properties per case (`mem`, `x1`, `x5`, `x17` frame and
write; E-cores 24–27), compared with S and DeepSeek on the same seven:

| Case | auto: `UNSAT`, refinements, time s | S | DeepSeek |
| --- | --- | --- | --- |
| LUI | 7, 26, 1,073 | 7, 1, 124 | 7, 1, 209 |
| AUIPC | 7, 25, 1,034 | 7, 1, 152 | 7, 1, 234 |
| JAL | 7, 28, 1,118 | 7, 1, 225 | 7, 1, 222 |

Without an adder in the obstacle path, auto also proves every sampled
sub-property, but it restores the CSR file, I-cache and mostly the D-cache in
each (final COI 1,779–2,382 bits) and is 5–9 times slower than S.

ANDI and SLTI were only screened: ANDI `x5.rs1=6` is `UNSAT` in 209 s with
the units kept, 128 s with its operator pair (`n110` /
`_theResult_____1_fst__h6597`). SLTI has no operator pair (the RTL computes
the comparison as a conditional expression). Their 1,024-sub-property full
proofs were not run.

## Conclusions

1. **The split and the finer options together make the Piccolo ILA
   properties provable.** With the property split, GPR keep/word/havoc and
   the UF on the adder, ADDI is proved (1,024 / 1,024 sub-properties, 11.0
   CPU-pair hours), and LUI, AUIPC and JAL are proved (63 / 63 each, 15–27
   min of two-CPU runs). B0 and the coarse menu of PR #14 have no verdict in
   30–60 min. Each part is needed for ADDI: without the split even the UF
   times out (Q, 1806 s); without the UF the write cases time out (B, F);
   without the rs1 split the write cases time out (I, N, N2). The split
   alone is not enough for ADDI but is for LUI, AUIPC and JAL, where the
   abstraction is a 5–8 times speed-up
   ([`split_baseline`](../split_baseline/README.md)).
2. **On the fine menu, DeepSeek beats the automatic strategy, but not the
   structural rule.** On the ADDI sample, auto proves 34 / 64 (it refines
   the UF away, and the adder model times out); DeepSeek 60 / 64 with 1
   refinement in 3,805 s versus auto's 315 refinements in 23,893 s. On LUI,
   AUIPC and JAL samples DeepSeek is 4.4–5.1 times faster than auto. But the
   structural rule, a three-line function of the sub-property, is equal to
   most DeepSeek answers (55 / 64, 57, 52, 56 / 63), proves everything, and
   is faster in every case (ADDI sample 2,627 vs 3,805 s). DeepSeek's
   deviations either do not matter or fail (4 ADDI write cases with the
   adder kept, 2 frame cases with the compared GPR at word level). The split
   and the menu make the right choice obvious from the sub-property text; the
   claim "the LLM makes verification faster" is supported against auto CEGAR
   and against the split alone, not against a simple structural heuristic.

## Not done and risks

- Flute was not tried. R-type cases (ADD, SUB, ...) would need rs1 × rs2
  splits (1 + 31 + 31 × 32 × 32 = 31,776 sub-properties per instruction) or a different abstraction.
- ANDI and SLTI full proofs were not run; SLTI has no UF pair, so its write
  cases are untested beyond the screen design.
- Times mix P- and E-core two-CPU runs and share the machine with another
  session, so they are comparable only within a row group.
- The refinement attributes free values per choice; it never promotes a
  word-level GPR while some unit has free values in the counterexample (the
  two DeepSeek failures), and it refines the UF away in ADDI write cases.
- Soundness of the split rests on the coverage argument in "Property split"
  (`ila_split` and its test); the UF on the argument of "Operator
  abstraction". The negated check on the UF model is SAT at depth 11.

## Reproduction

The scripts in [`scripts/`](scripts) produced these results, with the run
directory `/var/tmp/neuroabs-runtime/runs/fine-gpr-20261026`; each sources
`/var/tmp/neuroabs-runtime/env-20261024.sh`. `screen.sh` runs one
screen, `arm.sh <case> <arm> <specs> <cpus> <limit> <iterations>` one arm
with `src/fine_batch.py`, `llm.sh` the DeepSeek choices with
`src/fine_choice_llm.py`, `b0.sh` the B0 run; the `queue-*.sh` files are
the order of the runs. After the runs, the scripts were changed to write the
`.done` markers only on success (a failure writes `.failed`, which stops the
queues waiting on it) and `after.sh` to ignore its own and its ancestors'
command lines; the recorded results have no duplicate or `ERROR` record, so
these changes do not affect them; `summarize.py` and `depths.py` give the table numbers
and the deepest BMC bound / IC3 frame of a log. Per-case records are in `piccolo/<case>/`:
`arm-*.jsonl` (one line per sub-property: verdict, refinements, times, final
COI bits, final spec), `llm-decisions.jsonl` (answers, probabilities, usage,
without the prompts), `screen-*.json`, `specs-*.jsonl` and `b0.json`.

