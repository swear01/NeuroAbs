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
