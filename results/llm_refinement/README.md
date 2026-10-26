# LLM choice of the CEGAR refinement step (rIC3)

Status on 2026-10-26: the refinement step of the choice-level CEGAR from
[`flute_piccolo_choices`](../flute_piccolo_choices/README.md) is a pluggable
strategy. Four strategies are compared on the twelve Piccolo ILA properties,
from the all-cut start, with rIC3 deciding every model.

- DeepSeek V4 Flash picks a unit that the property needs in all 108 of its
  refinement steps (12 cases, 3 runs each) and reaches the coarsest assignment
  without a known counterexample (csr cut, dcache cut; 4,136 COI state bits) in
  every run, after three refinements.
- None of the automatic strategies reaches it in any case. Refining the unit
  with most free values (`one`, the PR #14 heuristic) and refining every unit
  (`all`) end at B0 (5,131 bits; one `one` run at 4,721); refining the smallest
  candidate whose BMC check up to the counterexample depth has no counterexample
  (`bmc`) ends at csr cut (4,542 bits), because the D-cache removes the first,
  depth-8, counterexample but is not needed.
- Time before the final model, median over the cases: `all` 66 s, LLM 111 s
  (80 s without the 31 s of DeepSeek latency), `bmc` 175 s, `one` 181 s. `all`
  is fastest but ends at the full design.
- The final models still get no verdict. In 1800 s, the LLM's final model
  reaches the kissat BMC bounds sooner than B0 and the `bmc` model (ADDI bound
  50 against 40; BEQ 65 against 30; [final models](#final-models)), as in PR
  #14, but no model is proved and IC3 is not deeper.
- The comparison is easy for the LLM: the assertion names the GPR array and the
  instruction memory interface, and the two needed units are the GPR file and
  the I-cache. Every Piccolo case has the same units and the same needed units.

## Strategies

`src/choice_abstraction.py cegar --refine {one,all,bmc,llm}`. On `SAT`, the
witness is replayed on the abstract model and its dynamic cone of influence is
traced back to the free values `choice__<unit>__<n>`, with the cycle in which
each is read (`btor_witness.free_values`). The units with free values in the
cone are the candidates; each strategy moves units one level towards keep.

| Strategy | Choice | Cost recorded as selection time |
| --- | --- | --- |
| `one` | candidate with most free values in the cone | none |
| `all` | every candidate | none |
| `bmc` | refine each candidate alone, `ric3 check <model> bmc --end k` with k the counterexample depth; the smallest model with no counterexample up to k, else the one whose first counterexample is deepest, then the smallest | every BMC run, and the builds of the candidates not chosen |
| `llm` | DeepSeek names one candidate | Yosys pass naming the free values, and the LLM latency |

The `bmc` strategy is the automatic counterpart of the LLM: it checks every
candidate instead of guessing.

### LLM prompt

System prompt: [`src/refine_context.txt`](../../src/refine_context.txt). It
explains the levels and the refinement loop, says that a unit can be in the cone
without causing the failure, and asks for strict JSON
`{"refine": <unit>, "probabilities": {<candidate>: p}, "reason": <sentence>}`.
The user message (`choice_refine.build_message`) holds:

- the case description and the assertion assignments, as in PR #14;
- the COI state bits of the current model and the counterexample length;
- every unit with instance, module, COI state bits in B0 and level; for each
  coarsened unit, the next level, the number of free values in the cone, and up
  to eight of the nets they drive with the cycles in which they are read (from a
  separate Yosys pass that runs the same cuts, `opt_clean`, and selects the
  wire on each `$anyseq` output);
- the earlier refinements: counterexample length, free values per unit and
  refined units.

It contains no screen results or other refinement outcomes. Model `deepseek-flash`
(served `deepseek/deepseek-v4.1-flash`), reasoning effort low, through the local
gateway. An invalid answer stops the run; none occurred. Every prompt and
answer is in `piccolo/<case>/llm-<n>/refine-iter<k>.json`. An example message,
for ADDI iteration 0 (assertion lines shortened):

```
The current abstract model has 2706 state bits in the cone of influence of the property.
The counterexample has 9 cycles, 0 to 8; the property fails in cycle 8.

The units:
- id: csr_regfile
  instance: RTL.csr_regfile (module mkCSR_RegFile)
  state bits in the cone of influence of the original design: 480
  level: cut; refining moves it to keep
  unconstrained values in the counterexample: 10
  signals they drive: RTL.csr_regfile$interrupt_pending (cycles 2, 5, 6, 7); RTL.csr_regfile$nmi_pending (cycles 2, 5, 6, 7); ...
- id: gpr_regfile_regfile
  ...
  level: cut; refining moves it to havoc
  unconstrained values in the counterexample: 4
  signals they drive: RTL.gpr_regfile.regfile$D_OUT_1 (cycles 5, 6); RTL.gpr_regfile.regfile$D_OUT_3 (cycles 5, 6)
- id: near_mem_dcache
  ...
  unconstrained values in the counterexample: 12
- id: near_mem_icache
  ...
  unconstrained values in the counterexample: 11
  signals they drive: RTL.near_mem$imem_exc (cycles 5, 6); RTL.near_mem$imem_valid (cycles 5, 6); RTL.near_mem.icache$word64 (cycles 5, 6); RTL__DOT__near_mem$imem_pc (cycles 5, 6); ...

Candidate units: csr_regfile, gpr_regfile_regfile, near_mem_dcache, near_mem_icache

Earlier refinements: none.
```

Answer: `near_mem_icache` (0.74), "The ADDI property depends on the fetched
instruction and PC, and near_mem_icache supplies unconstrained imem_pc and
instruction-word values ...".

### Shared models

`--models DIR` stores each assignment's model, build time, rIC3 verdict and
witness once (`choice_abstraction.abstract_model`, `portfolio_verdict`,
`bmc_verdict`). The arms of a case share one directory, so every arm sees the
same counterexample for the same assignment and the same measured times; a
reused result keeps the time measured when it was computed. The three LLM runs
of a case therefore get the same first message and differ only in the LLM's
answers.

## Setup

- Cases: the twelve Piccolo cases of PR #14 (`scripts/cases.txt`), ILA property
  (`normalassert`). Units as in PR #14, identical in every case
  ([`piccolo-units.json`](piccolo-units.json)): `csr_regfile` (keep, cut),
  `gpr_regfile_regfile` (keep, havoc, cut), `near_mem_dcache` and
  `near_mem_icache` (keep, cut).
- Start: every unit at its coarsest level. rIC3 portfolio, `--time-limit 300`
  per model, at most 8 refinements ([`scripts/arms.sh`](scripts/arms.sh)). Two
  queues of six cases on E-cores 16–19 and 20–23, nothing else on them. Arm
  order per case: `one`, `all`, `bmc`, `llm` ×3.
- Ground truth ([`scripts/screen.py`](scripts/screen.py), one P-core per case,
  untimed): each unit coarsened alone, `ric3 ... bmc --end 20`, 900 s; a unit is
  needed at keep if a coarser level has a counterexample up to depth 20. Then the
  coarsest safe level of every unit together. In all twelve cases: gpr havoc and
  icache cut have a counterexample at depth 11; csr cut and dcache cut have none
  up to depth 20; together (csr cut, dcache cut) have no counterexample up to
  depth 20 in ten cases; in ADD_Flatten and ADDI BMC reaches depth 18 without one
  before the time limit (recorded as inconclusive). PR #14 found no counterexample for this model in 3600 s of the
  portfolio. The ADDI screen was first run with 600 s, at which dcache cut timed
  out and was counted as needed; it was rerun with 900 s
  (`piccolo/ADDI/screen.600s.jsonl`).
- Step judgement ([`scripts/evaluate.py`](scripts/evaluate.py)): a step that
  refines unit u is *needed* if u's level is coarser than its ground-truth
  level, and *removing* if the model with only u refined has no counterexample
  up to the counterexample depth (rIC3 BMC, separate models directory).

## Results

### All cases

| Arm | Runs | Final = optimal | Refinements | Steps on needed units | Steps removing the counterexample | Final COI bits | Time before final model, median (s) | of which LLM (s) |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| `one` | 12 | 0 | 4–5 | 36/59 | 24/59 | 5,131 (one run 4,721) | 181 | — |
| `all` | 12 | 0 | 2 | 36/60 | 36/60 | 5,131 | 66 | — |
| `bmc` | 12 | 0 | 4 | 36/48 | 24/48 | 4,542 | 175 | — |
| `llm` | 36 | 36 | 3 | 108/108 | 70/108 | 4,136 | 111 | 31 |

"Time before final model" is build + rIC3 + replay + selection of every
iteration that ended in a counterexample; every final model then runs into the
300 s limit (`TIMEOUT`). The `bmc` selection itself takes 13–33 s per step on
Piccolo (`selection_seconds` in `cegar.json`). DeepSeek latency per call was
3–105 s, median 8 s.

### Per case

Time before the final model (s); for the LLM, the three runs with the LLM
latency in parentheses. Steps: `✗` = unit not needed, `*` = refining it alone
removes the counterexample up to its depth.

| Case | `one` | `all` | `bmc` | `llm` (3 runs) | Steps `one` | Steps `bmc` | Steps `llm` |
| --- | ---: | ---: | ---: | --- | --- | --- | --- |
| ADD_Flatten | 195 | 70 | 185 | 96 (25), 89 (17), 100 (29) | icache* → csr✗ → dcache✗ → gpr → gpr* | dcache✗* → gpr → icache → gpr* | icache* → gpr → gpr* |
| ADDI | 184 | 62 | 182 | 111 (44), 115 (48), 107 (40) | dcache✗* → csr✗ → icache → gpr → gpr* | dcache✗* → gpr → icache → gpr* | icache* → gpr → gpr* |
| ANDI | 169 | 63 | 152 | 101 (31), 85 (14), 100 (30) | icache* → csr✗ → dcache✗ → gpr → gpr* | dcache✗* → gpr → icache → gpr* | icache* → gpr → gpr* |
| AUIPC | 170 | 62 | 139 | 114 (51), 84 (21), 112 (48) | icache* → csr✗ → dcache✗ → gpr → gpr* | dcache✗* → gpr → icache → gpr* | icache* → gpr → gpr* |
| BEQ | 178 | 63 | 151 | 89 (21), 95 (27), 85 (17) | icache* → csr✗ → dcache✗ → gpr → gpr* | dcache✗* → gpr → icache → gpr* | icache* → gpr → gpr* |
| BNE_new | 174 | 59 | 153 | 120 (54), 91 (26), 95 (29) | icache* → csr✗ → dcache✗ → gpr → gpr* | dcache✗* → gpr → icache → gpr* | icache* → gpr → gpr* |
| JAL | 158 | 61 | 168 | 109 (40), 114 (44), 156 (86) | csr✗ → icache* → dcache✗ → gpr → gpr* | dcache✗* → gpr → icache → gpr* | icache* → gpr → gpr* |
| LUI | 113 | 75 | 158 | 112 (41), 103 (32), 89 (18) | csr✗ → icache* → gpr → gpr* | dcache✗* → gpr → icache → gpr* | icache* → gpr → gpr* |
| OR | 266 | 89 | 222 | 112 (16), 131 (35), 115 (19) | icache* → csr✗ → dcache✗ → gpr → gpr* | dcache✗* → gpr → icache → gpr* | icache* → gpr → gpr* |
| SLTI | 249 | 99 | 202 | 150 (61), 106 (17), 115 (27) | csr✗ → icache* → dcache✗ → gpr → gpr* | dcache✗* → gpr → icache → gpr* | icache* → gpr → gpr* |
| SUB | 241 | 92 | 230 | 212 (138), 116 (29), 113 (39) | csr✗ → icache* → dcache✗ → gpr → gpr* | dcache✗* → gpr → icache → gpr* | gpr → gpr → icache* (runs 1, 3); icache* → gpr → gpr* (run 2) |
| XOR | 250 | 97 | 221 | 131 (46), 116 (31), 119 (34) | csr✗ → icache* → dcache✗ → gpr → gpr* | dcache✗* → gpr → icache → gpr* | icache* → gpr → gpr* |

`all` refines csr, gpr, dcache and icache in iteration 0 (two of them not
needed) and gpr again in iteration 1, in every case.

Two observations:

- The free-value count does not point at the cause. In iteration 0 the CSR file
  or a cache has the most free values (CSR 10, D-cache 12, I-cache 11, GPR 4 on
  ADDI), and after the I-cache is restored the CSR file still has 14–16 against
  the GPR file's 4–5.
- The BMC check is local: on the all-cut model both caches remove the depth-8
  counterexample, and the D-cache model is smaller, so `bmc` restores a cache
  that is not needed. Later, no single candidate removes the depth-11
  counterexample (the GPR file and I-cache are both needed), and the tie-break
  by depth and size picks arbitrarily. Every `bmc` run ends one wrong unit
  above the optimum.

### Final models

The 300 s runs do not separate the final models (each BMC worker reaches the
same bound 10–30 on all of them). The three distinct final models were run for
1800 s on four E-cores each ([`scripts/final.sh`](scripts/final.sh); one run,
ADDI on 16–19 and BEQ on 20–23 in parallel), deepest bound per rIC3 worker:

| Case | Model (arm) | COI bits | Verdict | bmc_kissat_65 | bmc_kissat_10 (minutes to 40) | bmc | IC3 frame | kind |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| ADDI | csr cut, dcache cut (`llm`) | 4,136 | UNKNOWN | 65 (16.3 min) | 50 (14.0) | 13 | 7 | 11 |
| ADDI | csr cut (`bmc`) | 4,542 | UNKNOWN | 65 (26.0 min) | 40 (17.8) | 14 | 10 | 10 |
| ADDI | B0 (`one`, `all`) | 5,131 | UNKNOWN | 65 (28.5 min) | 40 (26.5) | 13 | 10 | 11 |
| BEQ | csr cut, dcache cut (`llm`) | 4,136 | UNKNOWN | 65 (21.8 min) | 40 (20.2) | 17 | 7 | 11 |
| BEQ | csr cut (`bmc`) | 4,542 | UNKNOWN | – | 30 | 17 | 10 | 11 |
| BEQ | B0 (`one`, `all`) | 5,131 | UNKNOWN | – | 30 | 15 | 10 | 11 |

`bmc_kissat_dyn` reached no bound beyond 0 on any model. The LLM's model gets
through the kissat BMC steps fastest: on ADDI it reaches bound 40 after 14 min
against 18 and 27 min, and on BEQ it is the only model to reach bounds 40 and
65. The IC3 and k-induction workers are not deeper on it (IC3 frame 7 against
10). This is one run per model, on four cores.

For comparison, PR #14 on 16 E-cores for 3600 s: ADDI B0 deepest bound 115,
csr cut + dcache cut 142, IC3 frame 10 on both.

### Flute ADD ILA (screening)

P-cores 8–10, 300 s per model, one run per arm, all-cut start; five units
including `stageF_branch_predictor` ([`scripts/flute-arms.sh`](scripts/flute-arms.sh)).
There is no ground truth: PR #14 found no counterexample for any single-unit
abstraction within 600 s, and a real counterexample cannot reach `__IEND__`
before depth 283, so every counterexample below is spurious.

| Arm | Refinements | Steps (counterexample depth) | Final (csr, gpr, dcache, icache, bp) | COI bits | Time before final model (s) |
| --- | ---: | --- | --- | ---: | ---: |
| `llm` | 4 | gpr (11) → gpr (12) → icache (11) → icache (13) | cut, keep, cut, keep, cut | 73,016 | 254 |
| `one` | 4 | csr (11) → icache (12) → bp (13) → dcache (523) | keep, cut, havoc, havoc, havoc | 5,311 | 427 |
| `bmc` | 3 | dcache (11) → bp (13) → bp (524) | cut, cut, havoc, cut, keep | 32,905 | 906 |
| `all` | 1 | all five (11) | keep, havoc, havoc, havoc, havoc | 5,311 | 16 |

Every final model times out at 300 s, so this does not show which is better.
The `one` and `all` final models are coarser than P1 of PR #14 (cache and BTB
memories havoc, GPR keep), which has a spurious counterexample at depth 518
after 1310 s, so a longer limit would refine them further. The LLM keeps the
GPR file and the I-cache as on Piccolo, and its final model holds the 68,782
I-cache bits. The `bmc` strategy pays 614 s in one step for BMC to depth 524
on four candidates.

## Conclusions

- At the refinement decision point the LLM is better than both automatic
  strategies on Piccolo ILA: it is right in every step and run, and it is the
  only strategy that ends at the coarsest assignment. Free-value counting
  (`one`) and the per-candidate BMC check (`bmc`) each make two wrong steps per
  case; refining everything is fast but discards the abstraction.
- It is also cheaper than the BMC check: 111 s against 175 s before the final
  model (80 s if LLM latency is ignored), and US$0.006 per run.
- It does not make verification succeed. Every final model, the LLM's
  included, has no verdict within the limits; the better refinement only buys
  deeper BMC bounds, and only on a model 19% smaller than B0.
- The evidence is narrow: one design, four units, and the same two needed units
  in every case, which the assertion text names directly. The LLM's three runs
  also see the same counterexamples. A design where the needed unit is not
  visible in the property would be a stronger test.

## Cost and reproduction

DeepSeek: 115 calls in this study (including a smoke test and Flute), US$0.25 at
peak-hour list price. The API key is held by the gateway and appears in no
request, log or artifact.

Scripts in [`scripts/`](scripts) with the run directory
`/var/tmp/neuroabs-runtime/runs/llm-refine-20261026` (`. /var/tmp/neuroabs-runtime/env-20261024.sh`
first): `prep.sh` (units), `screen-all.sh`/`screen.py` (ground truth),
`arms.sh` (CEGAR arms), `evaluate.py` (step judgement), `collect.py` (tables),
`final.sh`/`final-summary.py` (final models), `flute-arms.sh`,
`copy-results.sh`. Per case: `piccolo/<case>/` holds `ground_truth.json`,
`screen.jsonl`, `evaluation.json` and, per arm, `cegar.json` and the LLM's
`refine-iter<k>.json`. Paths inside the JSON point to the run directory.
