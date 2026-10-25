# Keep-or-X decision experiment on PicoRV32 (rIC3)

Status on 2026-10-25: baselines B0 and B1 and the DeepSeek arms D1–D3 are
constructed and timed with rIC3 for all nine PicoRV32 riscv-formal cases; every
run is `UNSAT`. No decision arm is faster than all-X B1 overall: geometric-mean
rIC3 time relative to B0 is 0.95 for B1, 0.98 for D1, 1.05 for D2 and 0.97 for
D3. D2 used only DeepSeek V4 Flash 1017; part of D1 and D3 was served by an
older fallback model (see [DeepSeek model mix](#deepseek-model-mix)). The Luna
arms A1–A3 have not run because the opencode Go weekly usage limit was
exhausted.

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
| D1 | as A1 | DeepSeek V4 Flash, reasoning effort low, as A1 | `deepseek-generate` |
| D2 | as A2 | DeepSeek V4 Flash, as A2 | `deepseek-decision` |
| D3 | as A3 | DeepSeek V4 Flash, as A3 | `deepseek-decision`, `--candidate-scope coi` |

For X, NeuroAbs replaces the complete right-hand side with a fresh input and
runs the Z3 soundness check; the model never writes RTL in A2, A3, D2 or D3.
DeepSeek is called through the local gateway at `127.0.0.1:35001` as
`deepseek-v4-flash`, which Command Code serves as V4 Flash 1017.

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

## DeepSeek arms (D1–D3)

### Construction

Columns as for B1, plus the X/keep answers and the list price. Sat means the
checker rejected the rewrite as unsound. Times are construction seconds,
including the API calls; all 27 runs ran concurrently on the E-cores. The ADD
D2 pilot ran at commit `e409e8e`, the other runs at `ab5f92b`, which only adds
bounded retries of gateway 5xx responses.

| Arm | Case | Req. | X/keep | Sound | Sat | Error | Strict | No-op | Locations | Ref. | Final loc. | Seconds | Price |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| D1 | ADD | 232 | — | 144 | 17 | 71 | 121 | 23 | 105 | 2 | 13 | 7586 | $1.45 |
| D1 | ADDI | 238 | — | 148 | 14 | 76 | 127 | 21 | 112 | 2 | 12 | 7688 | $1.22 |
| D1 | AND | 232 | — | 148 | 12 | 72 | 126 | 22 | 112 | 1 | 14 | 7943 | $1.25 |
| D1 | BGE | 200 | — | 125 | 8 | 67 | 115 | 10 | 98 | 2 | 14 | 5923 | $0.90 |
| D1 | ORI | 238 | — | 143 | 20 | 75 | 127 | 16 | 111 | 2 | 13 | 7417 | $1.17 |
| D1 | SH | 269 | — | 172 | 7 | 90 | 151 | 21 | 131 | 1 | 15 | 8168 | $1.58 |
| D1 | SLTI | 238 | — | 150 | 12 | 76 | 131 | 19 | 115 | 2 | 13 | 7599 | $1.46 |
| D1 | SUB | 232 | — | 153 | 8 | 71 | 130 | 23 | 114 | 1 | 13 | 7193 | $1.37 |
| D1 | XOR | 232 | — | 149 | 12 | 71 | 134 | 15 | 117 | 2 | 13 | 7669 | $1.45 |
| D2 | ADD | 232 | 152/80 | 120 | 0 | 32 | 118 | 2 | 104 | 2 | 13 | 3323 | $0.55 |
| D2 | ADDI | 238 | 155/83 | 121 | 0 | 34 | 119 | 2 | 107 | 1 | 12 | 2808 | $0.39 |
| D2 | AND | 232 | 144/88 | 115 | 0 | 29 | 113 | 2 | 100 | 2 | 12 | 3167 | $0.44 |
| D2 | BGE | 200 | 145/55 | 114 | 0 | 31 | 112 | 2 | 97 | 1 | 13 | 2698 | $0.38 |
| D2 | ORI | 238 | 165/73 | 126 | 0 | 39 | 124 | 2 | 111 | 2 | 13 | 3407 | $0.48 |
| D2 | SH | 269 | 201/68 | 149 | 0 | 52 | 147 | 2 | 131 | 2 | 15 | 3134 | $0.44 |
| D2 | SLTI | 238 | 158/80 | 121 | 0 | 37 | 119 | 2 | 106 | 2 | 13 | 3108 | $0.44 |
| D2 | SUB | 232 | 145/87 | 117 | 0 | 28 | 115 | 2 | 103 | 2 | 12 | 3020 | $0.43 |
| D2 | XOR | 232 | 151/81 | 121 | 0 | 30 | 119 | 2 | 105 | 2 | 13 | 3261 | $0.49 |
| D3 | ADD | 597 | 393/204 | 286 | 0 | 107 | 284 | 2 | 250 | 4 | 2 | 8696 | $1.35 |
| D3 | ADDI | 597 | 402/195 | 300 | 0 | 102 | 298 | 2 | 268 | 3 | 6 | 7638 | $1.20 |
| D3 | AND | 597 | 401/196 | 292 | 0 | 109 | 290 | 2 | 255 | 3 | 7 | 8923 | $1.37 |
| D3 | BGE | 597 | 414/183 | 311 | 0 | 103 | 309 | 2 | 267 | 3 | 9 | 7839 | $1.30 |
| D3 | ORI | 597 | 407/190 | 300 | 0 | 107 | 298 | 2 | 266 | 3 | 7 | 8373 | $1.31 |
| D3 | SH | 598 | 411/187 | 302 | 0 | 109 | 300 | 2 | 257 | 3 | 10 | 9729 | $1.63 |
| D3 | SLTI | 597 | 405/192 | 300 | 0 | 105 | 298 | 2 | 265 | 3 | 6 | 8088 | $1.23 |
| D3 | SUB | 597 | 387/210 | 286 | 0 | 101 | 284 | 2 | 254 | 3 | 7 | 9359 | $1.52 |
| D3 | XOR | 597 | 405/192 | 295 | 0 | 110 | 293 | 2 | 259 | 3 | 5 | 8382 | $1.27 |

- Every answer of D2 and D3 parsed; X answers that the checker cannot encode
  keep the original statement, as in B1.
- D1 wrote 7–20 unsound rewrites per case, which the checker rejected, and
  10–23 rewrites equivalent to the original. Keep-or-X cannot produce either.
- The final X inputs equal the final locations in every run, and every CEGAR
  run ended with Pono `unknown` at bound 25 without a Pono timeout. CEGAR keeps
  12–15 locations for D1 and D2 against 14–17 for B1 (0 for SH), and 2–10 for
  D3, whose X answers outside the constant scope mostly fail CEGAR.

### rIC3 timing

Medians of three `UNSAT` runs in seconds, timed as in the B0/B1 section; the
B0 and B1 columns repeat that section.

| Case | B0 | B1 | D1 | D2 | D3 | B1/B0 | D1/B0 | D2/B0 | D3/B0 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ADD | 122.3 | 127.5 | 134.2 | 124.8 | 147.8 | 1.04 | 1.10 | 1.02 | 1.21 |
| ADDI | 137.7 | 146.8 | 140.1 | 145.3 | 126.0 | 1.07 | 1.02 | 1.06 | 0.92 |
| AND | 121.4 | 99.1 | 109.1 | 109.1 | 110.3 | 0.82 | 0.90 | 0.90 | 0.91 |
| BGE | 202.0 | 187.8 | 172.4 | 207.4 | 167.2 | 0.93 | 0.85 | 1.03 | 0.83 |
| ORI | 103.1 | 105.2 | 113.3 | 113.6 | 102.5 | 1.02 | 1.10 | 1.10 | 0.99 |
| SH | 178.6 | 180.6 | 174.7 | 260.1 | 204.6 | 1.01 | 0.98 | 1.46 | 1.15 |
| SLTI | 156.7 | 100.2 | 143.9 | 145.7 | 110.9 | 0.64 | 0.92 | 0.93 | 0.71 |
| SUB | 142.2 | 151.4 | 132.7 | 149.2 | 148.9 | 1.06 | 0.93 | 1.05 | 1.05 |
| XOR | 106.0 | 112.7 | 115.1 | 109.7 | 117.7 | 1.06 | 1.09 | 1.04 | 1.11 |

- Geometric mean relative to B0: B1 0.95, D1 0.98, D2 1.05, D3 0.97. Summed
  medians: B0 1270 s, B1 1211 s, D1 1236 s, D2 1365 s, D3 1236 s.
- Each decision arm beats B1 on four cases and loses on five. D2, the only arm
  served entirely by the 1017 model, is the slowest arm and loses SH by 1.44
  times against B1.
- The slowest DeepSeek-model run is at most 1.11 times its fastest (median
  1.03). The largest spread, ADDI D2 (157.1 against 141.1 s), is a first repeat
  timed while the last seven constructions still ran on the P-cores from 02:53
  to 03:11; the other DeepSeek repeats ran with the machine otherwise idle.
- Abstraction effect is small at this scale: most per-case ratios are within
  the 1.07 run-to-run spread, and only SLTI and AND improve by more than 10% in
  any arm, B1 included.

### DeepSeek model mix

From 02:14 on 2026-10-25, Command Code returned 429 and the gateway fell back to
OpenRouter, which serves `deepseek-v4-flash` as `deepseek-v4-flash-0731`
(providers Cohere, DigitalOcean and Parasail). The 0731 answers carry a
median 2527 completion tokens against 310 for 1017.

| Arm | Cases with 0731 answers | 0731 share |
| --- | --- | ---: |
| D1 | ADD 91, ADDI 14, AND 11, ORI 4, SH 119, SLTI 88, SUB 92, XOR 69; BGE none | 488 of 2111 |
| D2 | none | 0 of 2111 |
| D3 | ADD 78, ADDI 23, AND 87, BGE 30, ORI 62, SH 113, SLTI 52, SUB 96, XOR 73 | 614 of 5374 |

`src/deepseek_chat.py` now accepts only answers served as
`deepseek/deepseek-v4-flash` and pauses 600 seconds otherwise. A rerun of the
mixed runs was stopped after 15 calls because the gateway still served 0731
four hours later; those calls are kept as `D1.stopped-fallback-20261025` and
`D3.stopped-fallback-20261025`.

### DeepSeek usage

| Use | Successful calls | HTTP attempts | Input tokens | Cached input | Output tokens | Reasoning tokens | List price |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| D1 | 2111 | 2116 | 14,908,449 | 11,959,936 | 9,075,912 | 9,041,143 | $11.85 |
| D2 | 2111 | 2112 | 7,532,162 | 6,190,080 | 2,996,098 | 2,939,841 | $4.04 |
| D3 | 5374 | 5375 | 20,505,249 | 15,829,120 | 8,902,135 | 8,757,773 | $12.18 |
| D1 stopped at the cost cap | 312 | — | — | — | — | — | $1.78 |

List price uses DeepSeek's peak rates for V4 Flash: $0.30 per million uncached
input tokens, $0.006 per million cached, $1.20 per million output tokens. It
also prices the 0731 answers, for which OpenRouter billed $2.04 in total, and
the 15 calls of the stopped rerun ($0.03). The failed attempts are gateway 503
responses, all retried. Median call time was 8 s for D2 and D3 and 25 s for D1.
Five D1 runs (ADD, SH, SLTI, SUB, XOR) were first started with a $1.50 cap,
stopped when they were projected to exceed it, and restarted from scratch with
a $3 cap; the stopped runs are kept as `D1.aborted-cap-20261025`.

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
timing is `timing-ric3-8c6df1b-ecores/timing.json` (commit `09ab318`), and
the DeepSeek timing is `timing-ric3-8c6df1b-ecores-deepseek-a/timing.json` and
`timing-ric3-8c6df1b-ecores-deepseek-b/timing.json` (commit `ab5f92b`); the
DeepSeek construction scripts and logs are in `deepseek-20261024/`. The tool
environment scripts are beside them. B1 and D1–D3 are timed with each case's `final_model` from the arm's
`arm_summary.json`. Final B1 model SHA-256 prefixes: ADD
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
