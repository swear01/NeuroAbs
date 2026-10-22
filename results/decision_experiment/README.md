# Keep-or-X decision experiment on PicoRV32 (rIC3)

Status on 2026-10-22: infrastructure complete; baselines B0 and B1 constructed
for all nine PicoRV32 riscv-formal cases; the Luna arms A1–A3 have not run
because the opencode Go weekly usage limit was exhausted. No arm has produced a
formal proof, so this record contains no acceleration claim.

## Design

All arms share the candidate statements, the CEGAR loop (`src/cegar.py`, Pono
bound 25, 900-second limit per Pono query), the rIC3 portfolio checker and the
timing schedule (at most two rIC3 runs at once, nothing else running).

| Arm | Candidates | Choice per statement | Backend |
| --- | --- | --- | --- |
| B0 | none | concrete model | — |
| B1 | constant-propagation differences | always X, no LLM | `all-x` |
| A1 | constant-propagation differences | GPT-6 Luna low writes the rewrite with the original prompt | `luna` |
| A2 | constant-propagation differences | Luna low answers keep or X with probabilities | `luna-decision` |
| A3 | constant-propagation differences plus every assignment in the output COI | as A2 | `luna-decision`, `--candidate-scope coi` |

For X, NeuroAbs replaces the complete right-hand side with a fresh input and
runs the Z3 soundness check; the model never writes RTL in A2 or A3.

## Environment

- Mazu, 32 cores; commit of this branch (see the pull request).
- Yosys 0.68+120 from OSS CAD Suite 2026-08-23 (archive SHA-256
  `063d7b4f5663271cf04529ba22266e21baa9e3431b236fe71e1bf589d6d8816a`).
- Pono from `swear01/pono-neuroabs` `a298b9e`.
- rIC3 1.5.2, SHA-256
  `f57d25015d088a76280472f466cb500745fe1d422fec62457270a9041d06182c`, run as
  `rIC3 --engine portfolio --time-limit 3600 model.btor2`. 1.5.2 is the latest
  crates.io release; it ignores `--time-limit` in portfolio mode, so the runner
  kills the process group 60 seconds after the cap and reports `TIMEOUT`.
- Python 3.11.6 with `requirements-reproduce.txt`.

## Baseline construction (B0, B1)

B0 is `picorv32_input.v` passed through each case's `design.ys`. B1 columns:
requests, Z3-sound (`unsat`), checker errors, strict OA, equivalent no-ops,
distinct fresh-input locations before CEGAR, CEGAR refinements, X inputs and
effective locations in the final model, and times in seconds for constant
propagation, rewriting and CEGAR.

| Case | Req. | Sound | Error | Strict | No-op | Locations | Ref. | Final X | Final loc. | Const. s | Rewrite s | CEGAR s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ADD | 232 | 161 | 71 | 159 | 2 | 138 | 2 | 17 | 17 | 9.8 | 63.7 | 622 |
| ADDI | 238 | 163 | 75 | 161 | 2 | 140 | 2 | 17 | 17 | 10.1 | 67.6 | 641 |
| AND | 232 | 161 | 71 | 159 | 2 | 138 | 2 | 17 | 17 | 9.7 | 65.1 | 611 |
| BGE | 200 | 133 | 67 | 131 | 2 | 113 | 2 | 14 | 14 | 10.5 | 50.6 | 707 |
| ORI | 238 | 163 | 75 | 161 | 2 | 140 | 2 | 17 | 17 | 10.8 | 56.7 | 670 |
| SH | 269 | 179 | 90 | 177 | 2 | 152 | 5 | 0 | 0 | 9.9 | 76.2 | 1787 |
| SLTI | 238 | 163 | 75 | 161 | 2 | 140 | 1 | 17 | 17 | 8.2 | 56.5 | 328 |
| SUB | 232 | 161 | 71 | 159 | 2 | 138 | 2 | 17 | 17 | 8.9 | 64.6 | 628 |
| XOR | 232 | 161 | 71 | 159 | 2 | 138 | 2 | 17 | 17 | 8.9 | 50.8 | 600 |

- Every CEGAR run ended with Pono `unknown` at bound 25, which is not a proof,
  and no Pono query timed out. The three B1 runs were constructed concurrently,
  so CEGAR times include contention.
- The two no-ops in every case are upstream `count_cycle <= 'bx;` and
  `count_instr <= 'bx;`, which are already X.
- Errors are statements the SMT checker cannot encode (part-select or
  concatenation targets, `|{...}`, `$signed`, indented `if (...)`). They stay
  unchanged in every arm.
- Location counts are below the sound count because repeated statement text
  maps to one location; see [`docs/notes.md`](../../docs/notes.md).
- In SH, CEGAR restored every input, so the final B1 model has no abstraction.

## ADD pilot: final checker

| Model | rIC3 portfolio (cap 3600 s) | kissat BMC to depth 25 |
| --- | --- | --- |
| B0 | `TIMEOUT`: no verdict after 69 min | no counterexample, `UNKNOWN` at bound, 9.22 s |
| B1 | `TIMEOUT`: no verdict after 69 min | no counterexample, `UNKNOWN` at bound, 8.42 s |

The two rIC3 runs ran together on an otherwise idle machine and were stopped by
hand after 69 minutes, because rIC3 did not stop at its cap. One earlier pair of
sanity runs under heavy load also gave no verdict within an hour. The authors
report 39.32 seconds for concrete rIC3 on this case; that is not reproduced with
rIC3 1.5.2 and this Yosys flow.

The riscv-formal checker fires once, at cycle 20, and its cycle counter
saturates at 255. Bounded exploration past cycle 20 therefore finds no
violation within seconds for both models; what remains hard is the unbounded
proof. BMC depth cannot separate the arms on these cases.

## Luna usage

| Use | Successful calls | HTTP attempts | Input tokens | Output tokens | Reasoning tokens | List price |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Probes | 2 | 5 | 43 | 14 | 0 | $0.00001 |
| A1 (ADD) | 0 | 1 (429) | 0 | 0 | 0 | $0 |
| A2 (ADD) | 0 | 1 (429) | 0 | 0 | 0 | $0 |

List price uses $0.10 per million input tokens and $0.50 per million output
tokens, with reasoning counted as output. The 429 response was
`GoUsageLimitError` with `limitName: weekly` and `Retry-After: 321631`
seconds, which is 2026-10-26 08:00 Asia/Taipei. The probe failures are two
Cloudflare 403 responses caused by the default Python User-Agent and one
deliberate 429 header check.

A3 has been exercised without Luna by using the `all-x` backend with
`--candidate-scope coi` on ADD: 66 constant-propagation signals plus 177 COI
signals give 597 statement requests, of which 438 the checker can encode, and
the generated wrapper passes Yosys.

## Artifacts

Run directories, logs, summaries and timing JSON are retained at
`/home/swear01/research-archives/neuroabs-decision-20261022/runs/`; the tool
environment script is beside them. Final B1 model SHA-256 prefixes: ADD
`a4c3d5326a30`, ADDI `a01a2c62381f`, AND `1043f18fed01`, BGE `9f2db8ee1aaf`,
ORI `34a8cad27ac0`, SH `c91adb94a5ba`, SLTI `d93e7fbf1762`, SUB `bbfd3b5864cd`,
XOR `aab1ad481bb7`. Full hashes are in each `arm_summary.json`.

## Reproduce

```bash
. /var/tmp/neuroabs-runtime/env-20261022.sh   # YOSYS_BIN, PONO_BIN, RIC3_BIN, RIC3_TMP_ROOT
R=/var/tmp/neuroabs-runtime/runs/decision-20261022
python src/run_decision_experiment.py construct --case riscv_formal/riscv_formal_add \
  --run-root $R --arm A2 --cegar-timeout 900 --session-id neuroabs-decision-20261022-add-A2
python src/run_decision_experiment.py time --ric3 "$RIC3_BIN" --repeats 5 \
  --time-limit 3600 --parallel 2 --output $R/timing/add.json \
  --model add-B0=$R/riscv_formal_add/B0/picorv32_input.btor2 \
  --model add-A2=$R/riscv_formal_add/A2/iter_btor/<last>.btor2
```
