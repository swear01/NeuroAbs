# I2C `i2c_assert1` initial reproduction

This result was produced on Mazu from commit
`58904a7d00402417205209ec1fc9ef58e7ff03fc` on 2026-08-24 (Asia/Taipei).

## Environment

- Python 3.11.6
- Yosys 0.68+120 (`a34d3baae`)
- OSS CAD Suite 2026-08-23
- DeepSeek model: `deepseek-v4-flash`, thinking disabled
- Local gateway: `http://127.0.0.1:35001/v1`

## Command

```bash
python -u src/main.py -t tst_bench_top --constant-template i2c \
  --api-backend deepseek -f RTL \
  -d i2c/i2c_assert1/description.txt \
  i2c/i2c_assert1/tst_bench_top.v
```

## Result

The constant-propagation stage completed in 0.245707 seconds. Yosys reported
one removed named RTL wire in the normal model and 63 in the constrained
model. Their set difference contains 62 candidate signals, recorded in
[`candidate_signals.txt`](candidate_signals.txt). Pyverilog localized 37 of
those signals to source statements.

The LLM stage completed all 184 statement requests in 6177.197376 seconds.
All 184 implication checks were `unsat`; none were `sat`. It produced
`wrapper_abstract_llm_new.v`, `statement.json`, and `input_line.json`. During
the run window, the gateway reported 186 additional `command-code` attempts,
184 additional successes, and no route switch. The run log contains no HTTP
402, traceback, or assertion error.

The generated JSON files parse successfully. Yosys 0.68+120 successfully read
the generated wrapper and completed `hierarchy -check -top tst_bench_top`.
The wrapper SHA-256 is
`198d11250f52c679803c94451a1e4bb9b0fbd425cefa072551524b4ceac9606e`.

This run reproduced candidate discovery and LLM abstraction, not the complete
CEGAR loop. The later public `swear01/pono-neuroabs` port supplies the default
`--dynamic_coi_up_cex`/`coi-check-rev.txt` interface on modern Pono. The
non-default `--pivot_input` branch remains unported.

The detached Mazu run was
`neuroabs-i2c-gateway-final-20260823T234146Z`; its log, gateway snapshots,
generated artifacts, hashes, and Yosys validation log are retained at
`/var/tmp/neuroabs-runtime/runs/i2c-gateway-final-20260823T234146Z/`.

## Modern Pono CEGAR follow-up

On 2026-08-25, the same generated wrapper was passed to `src/cegar.py` with
the public `swear01/pono-neuroabs` Dynamic COI port and Yosys 0.68+120. Modern
Yosys first required `chformal -lower` before reset simulation so that `$check`
cells remained as formal assertions but were accepted by `sim`.

Pono found no counterexample through bound 25 and printed `unknown`, so the
default CEGAR loop completed with zero refinement steps. Its timing report
labels this as one total iteration because it records `iteration + 1`. The run
produced:

- `0.btor2`: 46,673 bytes, SHA-256
  `ec8f40ec4672ef50b0f403ed2de9f99638217bf49580e964da7407b5cde7182b`
- `0_bx.btor2`: 48,897 bytes, SHA-256
  `2852a4daf30acec5f15289e271f76b581f89699bb669a1feefeee9ffcabe6bfc`

A separate satisfiable smoke test used Pono's `samples/counter.btor` with the
same NeuroAbs flags. It returned `sat` and wrote 21 deterministic Dynamic COI
lines, SHA-256
`a17c746fc50d67f81edbfa38c698b04839f55588fe6207400257548682230d54`.
This confirms the ported file interface is exercised when a counterexample
exists. The non-default pivot-input path was not needed.

The retained Mazu artifacts are under
`/home/swear01/neuroabs-runs/i2c-modern-coi-v2/` and
`/home/swear01/pono-dynamic-coi-sat.03GNm1/`.

## Muse Contributor 1.2 reproduction

This run used commit `9d4f6912232974938e635a9b81a985dc0fdfff32`, the
`meta` backend, and `muse-spark-1.2-contributor` on Mazu. Muse completed all
184 statement requests in 7154.236821 seconds. All 184 soundness implication
checks were `unsat`; none were `sat`.

The generated wrapper is 30,817 bytes with SHA-256
`9b4a8430a4eca9720e794a5cccf3ff6a9b55584f90f36c03b576795e5bc5ac43`.
Modern Pono returned `unknown` through bound 25, so CEGAR completed with zero
refinements. Its final `iter/0.btor2` is 53,908 bytes with SHA-256
`46efa51efec968aefb24cedb2e314ec6f85e852c3439839000f1187b84eb08c2`.

### Formal proof

The paper's I2C experiment belongs to RQ2, so the final checker must construct
a formal proof rather than only increase a BMC depth. The concrete model and
both generated abstract models were therefore checked on Mazu with:

```bash
rIC3 --engine portfolio --time-limit 3600 path/to/model.btor2
```

All three models returned `UNSAT`, with word-level k-induction
(`-e wl-kind --step 1 --rseed 16`) winning the portfolio. rIC3 uses exit status
20 for this successful safe result.

| Model | First proof | 10-run median | 10-run mean | Result |
| --- | ---: | ---: | ---: | --- |
| Concrete, without NeuroAbs | 0.10 s | 0.100 s | 0.094 s | 10/10 `UNSAT` |
| Muse Contributor 1.2 abstraction | 0.14 s | 0.105 s | 0.100 s | 10/10 `UNSAT` |
| DeepSeek V4 Flash abstraction | 0.15 s | 0.110 s | 0.112 s | 10/10 `UNSAT` |

The concrete model is the tracked `i2c/i2c_assert1/problem_2.btor2`, 27,709
bytes with SHA-256
`275d611e7f17fa0ec29b40559027fa4187dc8103e7093626acff90e136e134bf`.
The repeat measurements are recorded in
[`formal-proof-repeats.tsv`](formal-proof-repeats.tsv).

At roughly one tenth of a second, the differences are below a credible timing
resolution. This case therefore demonstrates successful abstraction and full
formal proof, but **does not demonstrate a checker speedup**. The paper's RQ2
result is an aggregate comparison under a 3600-second cap: AVR improves from
607.03 to 334.56 seconds on average, while rIC3 improves only marginally from
18.71 to 16.94 seconds because it is already fast on these cases. See the
[official RQ2 discussion](https://arxiv.org/html/2608.17304#S4.SS4).

Muse also does not improve end-to-end runtime in this reproduction. Its LLM
abstraction took 7154.236821 seconds, 977.039445 seconds (15.8%) longer than
DeepSeek's 6177.197376 seconds. These model and hardware choices differ from
the paper's GPT-4o-mini/Xeon setup, so the result validates the public flow but
does not reproduce the paper's aggregate acceleration claim.

### Corrected BMC side result

An earlier checker run mistakenly used rIC3/Kissat BMC, which corresponds to
the paper's RQ3 experiment for cases where formal proof does not conclude. It
was stopped after 21213.37 seconds once the correct RQ2 procedure was
identified. Buffered output then showed no counterexample through completed
depth 5139. The final CSV sample records depth 5139 at 21208.584501 seconds;
its SHA-256 is
`a20f181e8596bc023f5a62b6ae6ce7a1ff1e5771983781c71d0c263e438e76a2`.

This BMC run is retained only as bounded side evidence. It neither proves the
property nor replaces the `UNSAT` portfolio proof above. The paper likewise
omits I2C and PicoRV32 from RQ3 because their cases concluded with formal proofs
in RQ2; see the [official BMC table note](https://arxiv.org/html/2608.17304#S4.SS5).
