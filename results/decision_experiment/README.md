# Keep-or-X decision experiment on PicoRV32 (rIC3)

Status on 2026-10-24: infrastructure complete; baselines B0 and B1 constructed
and timed with rIC3 for all nine PicoRV32 riscv-formal cases, all `UNSAT`; the
Luna arms A1–A3 have not run because the opencode Go weekly usage limit was
exhausted. B1 is not a Luna arm, so this record contains no claim that a
decision model speeds up proofs.

## Design

All arms share the candidate statements, the CEGAR loop (`src/cegar.py`, Pono
bound 25, 900-second limit per Pono query), the rIC3 portfolio checker and the
timing schedule (one rIC3 run at a time, pinned to the 16 E-cores, nothing else
running).

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

- Mazu, Intel i9-14900K: CPUs 0–15 are 8 hyperthreaded P-cores, CPUs 16–31
  are 16 E-cores; commit of this branch (see the pull request).
- Yosys 0.68+120 from OSS CAD Suite 2026-08-23 (archive SHA-256
  `063d7b4f5663271cf04529ba22266e21baa9e3431b236fe71e1bf589d6d8816a`).
- Pono from `swear01/pono-neuroabs` `a298b9e`.
- rIC3 `master` at `8c6df1b` (2026-10-15), built with rustc 1.93.1 and
  `cargo build --release --locked`, SHA-256
  `90e7141bc92521fdc4cdbbf4310b1d953eee4aec4007c6ddb4fd1625ee696977`, run as
  `ric3 check --ui false model.btor2 portfolio --time-limit 3600` with the
  default `bl_default` portfolio. It exits 0 for every verdict, so the runner
  reads `UNSAT`, `SAT` or `UNKNOWN` from the last output line, kills the process
  group 60 seconds after the cap and reports `TIMEOUT`.
- Not rIC3 1.5.2, the latest release: for `.btor2` input its portfolio has no
  bit-level k-induction, and B0 ADD and SLTI get no verdict within 30 minutes.
  The authors used the rIC3 HWMCC'24 binary, which proves B0 ADD in 26 s;
  master's `bl_default` adds `--simple-path` to its k-induction worker and takes
  about 2 minutes.
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

## Final checker: rIC3 timing (B0, B1)

Each model ran three times, one run at a time, under `taskset -c 16-31`; every
run was `UNSAT`. Times are wall-clock seconds.

| Case | B0 runs | B0 median | B1 runs | B1 median | B1/B0 |
| --- | --- | ---: | --- | ---: | ---: |
| ADD | 122.3, 121.8, 123.2 | 122.3 | 128.6, 125.9, 127.5 | 127.5 | 1.04 |
| ADDI | 138.8, 134.1, 137.7 | 137.7 | 144.4, 146.8, 146.8 | 146.8 | 1.07 |
| AND | 123.0, 121.4, 119.1 | 121.4 | 99.0, 100.7, 99.1 | 99.1 | 0.82 |
| BGE | 210.3, 196.4, 202.0 | 202.0 | 187.8, 192.8, 187.3 | 187.8 | 0.93 |
| ORI | 103.1, 104.0, 103.0 | 103.1 | 107.0, 104.4, 105.2 | 105.2 | 1.02 |
| SH | 179.3, 177.9, 178.6 | 178.6 | 178.0, 181.8, 180.6 | 180.6 | 1.01 |
| SLTI | 156.7, 155.9, 159.6 | 156.7 | 98.9, 101.0, 100.2 | 100.2 | 0.64 |
| SUB | 142.2, 142.9, 135.5 | 142.2 | 151.4, 152.9, 150.5 | 151.4 | 1.06 |
| XOR | 104.0, 106.3, 106.0 | 106.0 | 112.8, 111.7, 112.7 | 112.7 | 1.06 |

- The slowest run of a model is at most 1.07 times its fastest (median 1.02).
  SH B1 has no X left after CEGAR, and its median is 1% above B0.
- All-X helps SLTI (0.64), AND (0.82) and BGE (0.93), and slows ADD, ADDI, SUB
  and XOR by 4–7%. It does not uniformly speed up rIC3.
- An earlier unpinned run of the same 54 jobs gave a slowest-to-fastest ratio
  of up to 1.95 for one model (median 1.62) and B1/B0 medians from 0.55 to
  1.38. In that run the scheduler spread the portfolio over P- and E-cores, and
  the package reached 100 °C and throttled within about a minute. Pinned to
  E-cores, it stayed near 4.4 GHz and 75–78 °C without throttling. Use pinned
  timings only; the unpinned run is kept as `timing-ric3-8c6df1b`.

The riscv-formal checker fires once, at cycle 20, and its cycle counter
saturates at 255. kissat BMC to depth 25 finds no counterexample for ADD B0 or
B1 in about 9 seconds, so BMC depth cannot separate the arms on these cases.

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
`/home/swear01/research-archives/neuroabs-decision-20261022/runs/`; the pinned
timing is `timing-ric3-8c6df1b-ecores/timing.json` (commit `09ab318`). The tool
environment scripts are beside them. B1 is timed with each case's
`final_model` from `B1/arm_summary.json`. Final B1 model SHA-256 prefixes: ADD
`a4c3d5326a30`, ADDI `a01a2c62381f`, AND `1043f18fed01`, BGE `9f2db8ee1aaf`,
ORI `34a8cad27ac0`, SH `c91adb94a5ba`, SLTI `d93e7fbf1762`, SUB `bbfd3b5864cd`,
XOR `aab1ad481bb7`. Full hashes are in each `arm_summary.json`.

## Reproduce

```bash
. /var/tmp/neuroabs-runtime/env-20261024.sh   # YOSYS_BIN, PONO_BIN, RIC3_BIN
R=/var/tmp/neuroabs-runtime/runs/decision-20261022
python src/run_decision_experiment.py construct --case riscv_formal/riscv_formal_add \
  --run-root $R --arm A2 --cegar-timeout 900 --session-id neuroabs-decision-20261022-add-A2
taskset -c 16-31 python src/run_decision_experiment.py time --ric3 "$RIC3_BIN" \
  --repeats 3 --time-limit 3600 --parallel 1 --output $R/timing/add.json \
  --model add-B0=$R/riscv_formal_add/B0/picorv32_input.btor2 \
  --model add-A2=$R/riscv_formal_add/A2/iter_btor/<last>.btor2
```
