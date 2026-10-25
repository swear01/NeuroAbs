# Unit-level abstraction choices on Flute and Piccolo (rIC3)

Status on 2026-10-25: the NeuroAbs Flute and Piccolo ILA wrappers are rebuilt
with Yosys 0.68 and checked with rIC3 master. A menu of sound abstraction
choices (one per module instance) is offered to DeepSeek V4 Flash, and every
assignment is checked with rIC3 under CEGAR.

- Piccolo sanity, 12 cases: every arm proves every case. Cutting all four
  units, with no LLM, gives the shortest time to verdict (geometric mean 0.44 of
  B0 including the Yosys build); the DeepSeek choice gives 0.67 because it
  always keeps the GPR file. No case needs a refinement.
- Piccolo ADDI ILA: no model gets a verdict within one hour, B0 included.
  DeepSeek chooses three of the four units right. After one CEGAR refinement it
  reaches the coarsest assignment with no counterexample within 600 s, which
  CEGAR from the all-cut start misses: that start refines two wrong units and
  ends at B0. In one hour that model reaches BMC bound 142, B0 115.
- Flute: B0 gets no verdict within one hour for ADD ILA or ADD sanity. The
  instruction end `__IEND__` cannot be reached before cycle 283 even in an
  over-approximation, so all but one of the Flute ILA bounds reported in the
  paper end before the first check of the property.

## Benchmarks

`Flute_verification_done/<CASE>/wrapper.v` and
`Piccolo_verification_done/<CASE>/wrapper.v` hold two assertions:
`normalassert`, the ILA refinement map at `__IEND__` (31 GPRs, pc and memory
request signals against the ILA state), and `sanitycheck`, the
`post_value_holder` checks. The ILA property removes `sanitycheck`, as the
authors' `gen_btor.ys`; the sanity property removes `normalassert`.
`scripts/build_b0.sh` builds the concrete model B0 for both:

```
read_verilog -formal wrapper.v; hierarchy -check -top wrapper; proc
chformal -assume -early; select wrapper/<removed>; chformal -remove; select *
memory; flatten; setundef -undriven -expose; chformal -lower
sim -clock clk -reset rst -rstlen 1 -n 1 -w wrapper; write_btor -s
```

`chformal -lower` is needed by Yosys 0.68, which otherwise rejects the `$check`
cells. Sizes are in [`b0_sizes.txt`](b0_sizes.txt) (all states, then states in
the cone of influence). Piccolo ADDI ILA has 5,131 COI state bits, the size of
the authors' `problem.btor2`. Flute ADD ILA has 171,649, almost all in the
instruction and data caches.

### Paper numbers

From the authors' `detail-result.xlsx`: Piccolo sanity proofs with rIC3 take
9–15 s (LLMAbs 6–14 s). The ILA properties have only bounds after 23,600 s:
Piccolo 73–180 (LLMAbs 92–200); Flute 112–150 (LLMAbs 198–324) for ILA and
115–130 (LLMAbs 198–225) for sanity. No Flute property is proved.

### When Flute can first check the property

`normalassert` only constrains states with `__IEND__` set. To test whether the
bounds reach that point, the assertion in the ILA wrapper is replaced by
`assert property ( !__IEND__ )` and the model is built as for the ILA property
([`scripts/iend-run.sh`](scripts/iend-run.sh), CPUs 4–7, 7200 s):

- Piccolo ADDI B0: rIC3 finds a trace to `__IEND__` at depth 11, in 60 s.
- Flute ADD P1 (every cache and BTB memory read is free; an over-approximation
  of B0): BMC proves `!__IEND__` up to depth 282, and IC3 finds a trace at depth
  524 after 993 s.

Every trace of the original Flute design is a trace of P1, so B0 cannot reach
`__IEND__` before depth 283. The Flute ILA baseline bounds (112–150) and every
LLMAbs ILA bound except XOR (324) are below that depth. The IC3 trace need not
be the shortest, so the shortest P1 trace has length 283–524, and B0's first
`__IEND__` may be later still. The sanity bounds were not analysed this way.

## Choice menu

`src/choice_abstraction.py units` lists the units: module instances under
`RTL` with at least 64 state bits in the COI of the property. An instance whose
own bits are below 10% of its subtree is replaced by its children. Each unit has
ordered levels, all realized with Yosys `cutpoint` and so all sound:

| Level | Meaning |
| --- | --- |
| keep | unchanged |
| havoc | every read of the unit's memories is a free value in every cycle (only units with memories) |
| cut | every output of the instance is a free value in every cycle |

| Unit | Flute ADD COI bits | Piccolo ADDI COI bits | Levels |
| --- | --- | --- | --- |
| `csr_regfile` | 480 | 480 | keep, cut |
| `gpr_regfile_regfile` | 1,024 | 1,024 | keep, havoc, cut |
| `near_mem_dcache` | 68,782 | 410 | keep, havoc, cut (Piccolo: keep, cut) |
| `near_mem_icache` | 68,782 | 378 | keep, havoc, cut (Piccolo: keep, cut) |
| `stageF_branch_predictor` | 29,280 | — | keep, havoc, cut |

The free values are renamed `choice__<unit>__<n>`.

### LLM decision

`src/choice_llm.py` sends `src/choice_context.txt` as the system prompt. The
user message holds the case description, the assertion assignments
(`variable_map_assert*` for ILA, `post_value_holder*` for sanity) and a table
of the units: path, module, COI bits, memories, up to 40 outputs and levels.
The model returns strict JSON with an answer and probabilities per unit. It
runs through the local gateway as `deepseek-flash` (served
`deepseek/deepseek-v4.1-flash`), reasoning effort low, one call per case.
Decisions are in `choice/<case>-<prop>/llm-decision.json`.

### CEGAR

`src/choice_abstraction.py cegar` builds the model for an assignment and runs
`ric3 check --cex <model> portfolio --time-limit <T>`. On `SAT`,
`src/btor_witness.py` replays the witness on the abstract model and takes its
dynamic cone of influence (the taken branch of each `ite`, one controlling
operand of a 1-bit `and`/`or`) back to the free values. Their
`choice__<unit>__<n>` names give the units in the counterexample.
`--refine all` moves every such unit one level towards keep; `--refine one`
moves only the unit with the most free values in the counterexample. When the
time limit is reached rIC3 panics instead of printing `UNKNOWN`
(`lib.rs:147`); that is recorded as `TIMEOUT`.

## Environment

As in [`decision_experiment`](../decision_experiment/README.md): Mazu
(i9-14900K), Yosys 0.68+120 (OSS CAD Suite 2026-08-23), rIC3 master `8c6df1b`
with the default portfolio. Timed runs are pinned to the 16 E-cores (CPUs
16–31) with nothing else on them; screens marked "P-cores" ran on CPUs 8–15
alongside the timed runs and are not timing results.

## Results

### Piccolo sanity

B0: three repeats, median rIC3 time, plus the 1 s Yosys build. Arms: `cegar
--refine one --time-limit 600`, three repeats, median of Yosys build plus rIC3
time (two Yosys passes, about 4.5 s). All runs are `UNSAT` with no refinement.
LB, SB and SH are `SAT` on B0 and are not in the paper; they are left out.

| Case | B0 rIC3 | Cut all: total | rIC3 | COI bits | DeepSeek: total | rIC3 | COI bits |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ADD_Flatten | 16.1 | 9.1 | 3.9 | 3,831 | 14.3 | 10.1 | 5,261 |
| ADDI | 16.2 | 7.6 | 2.9 | 3,831 | 8.4 | 3.9 | 4,855 |
| ANDI | 15.1 | 8.4 | 3.7 | 3,831 | 13.9 | 9.9 | 5,261 |
| AUIPC | 15.0 | 7.9 | 3.3 | 3,831 | 13.6 | 9.4 | 5,261 |
| BEQ | 21.1 | 8.2 | 3.8 | 3,831 | 11.5 | 7.3 | 4,855 |
| BNE_new | 22.2 | 7.1 | 2.8 | 3,831 | 13.0 | 9.3 | 5,261 |
| JAL | 15.3 | 7.5 | 2.9 | 3,831 | 13.0 | 8.9 | 5,261 |
| LUI | 15.4 | 7.3 | 2.7 | 3,831 | 13.9 | 9.8 | 5,261 |
| OR | 15.0 | 8.0 | 3.1 | 3,831 | 11.6 | 7.3 | 4,855 |
| SLTI | 16.9 | 7.6 | 2.9 | 3,831 | 12.7 | 8.5 | 4,855 |
| SUB | 16.6 | 8.0 | 3.2 | 3,831 | 8.4 | 4.0 | 4,855 |
| XOR | 19.1 | 7.9 | 3.1 | 3,831 | 12.0 | 7.6 | 4,855 |

Geometric mean relative to B0 (rIC3 + build): cut all 0.44, DeepSeek 0.67;
rIC3 time only: 0.19 and 0.45. DeepSeek cuts the CSR file and the D-cache in
every case, keeps the GPR file in every case, and keeps the I-cache in six of
twelve. None of the four units is needed by the sanity property, so the choice
is trivial here and the LLM only adds state.

### Piccolo ADDI ILA

B0 on the E-cores: no verdict within 3600 s. The deepest bound is 115
(`bmc_kissat_dyn`); IC3 reaches frame 10.

Single-unit screen (P-cores, 600 s; `choice/piccolo-ADDI-ila/single.jsonl`):

| Unit, level | rIC3 | COI bits | DeepSeek |
| --- | --- | ---: | --- |
| csr cut | no counterexample in 600 s | 4,542 | cut (0.98) |
| gpr havoc | `SAT`, depth 11 | 4,107 | keep (0.99) |
| gpr cut | `SAT`, depth 12 | 4,107 | keep |
| dcache cut | no counterexample in 600 s | 4,721 | cut (0.95) |
| icache cut | `SAT`, depth 11 | 4,689 | cut (0.85) |

CEGAR with `--refine one` (P-cores, 600 s per model):

| Start | Iterations (units in the counterexample → refined) | Final | COI bits |
| --- | --- | --- | ---: |
| all cut | 0: icache 6, csr 4, dcache 3, gpr 1 → icache; 1: csr 4, gpr 3, dcache 2 → csr; 2: dcache 4, gpr 3 → dcache; 3: gpr → havoc; 4: gpr → keep | B0, `TIMEOUT` | 5,131 |
| DeepSeek | 0: icache 7, csr 4, dcache 4 → icache | csr cut, dcache cut, `TIMEOUT` | 4,136 |

The dynamic cone overcounts: in iteration 1 restoring only the GPR file
removes every short counterexample (the csr cut, dcache cut model has none in
3600 s), but more CSR outputs lie on the counterexample's path. The DeepSeek start avoids the two wrong
refinements. `--refine all` from the all-cut start refines every unit in
iteration 0 and also ends at B0.

On the E-cores for 3600 s (one repeat each), the bound reached by each rIC3
BMC worker, the paper's metric:

| Model | COI bits | `bmc_kissat_dyn` | `bmc_kissat_65` | `bmc_kissat_10` | `bmc` | IC3 frame | `kind` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B0 | 5,131 | 115 | 65 | 90 | 23 | 10 | 13 |
| DeepSeek after one refinement (csr cut, dcache cut) | 4,136 | 142 | 130 | 110 | 28 | 10 | 12 |

Every BMC worker goes deeper on the abstract model (deepest bound 115 → 142),
which matches the direction of the paper (94 → 107 in 23,600 s), but neither
model has a verdict and IC3 stays at frame 10 on both.

### Flute ADD

E-cores, 3600 s, one repeat:

| Model | ILA | sanity |
| --- | --- | --- |
| B0 | `TIMEOUT`; deepest bound 195 (`bmc`), IC3 frame 279 | `TIMEOUT`; deepest bound 130, IC3 frame 353 |
| P1: cache and BTB memories havoc | `SAT` at depth 518, 1310 s | `SAT`, 63 s |
| P2: caches and branch predictor cut | `SAT`, 10 s | `SAT`, 12 s |

The P1 and P2 counterexamples are in over-approximations and need not exist in
B0. DeepSeek's ILA choice is csr cut, gpr keep, dcache cut, icache cut,
branch predictor keep.

Single-unit screen for Flute ADD ILA (P-cores, 600 s;
`choice/flute-ADD-ila/single.jsonl`): all nine models (csr cut; gpr, dcache,
icache and branch predictor at havoc and at cut) time out without a
counterexample, including gpr havoc, which fails at depth 11 on Piccolo. While
either cache is kept the property cannot be checked before the cache
initialization finishes, so 600 s cannot tell a needed unit from an unneeded
one, and the CEGAR comparison was not run on Flute.

## Conclusions

- On these wrappers the menu makes a single choice matter: the GPR file. For
  sanity nothing is needed and cutting everything is best; for ILA the GPR file
  is needed and the rest can be cut, but the remaining model is still out of
  reach for rIC3 within an hour; it only buys deeper BMC bounds.
- When the coarsest start is wrong, the refinement step is a decision of its
  own. The witness-based heuristic picks the wrong unit twice on Piccolo ADDI
  ILA, and the DeepSeek start helps only because it skips those steps.
- Flute bounds below 283 say nothing about the ILA property.

## Reproduction

The scripts in [`scripts/`](scripts) are the commands that produced these
results, with the run directory
`/var/tmp/neuroabs-runtime/runs/flute-piccolo-20261025`. Timing JSON is in
[`timing/`](timing).
