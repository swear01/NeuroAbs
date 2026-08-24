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

This reproduces candidate discovery and LLM abstraction, not the complete
CEGAR loop. `src/cegar.py` invokes the authors' modified Pono with
`--dynamic_coi_up_cex` and `--pivot_input`, then requires its custom
`coi-check-rev.txt` and `pivot_input.txt` outputs. Those interfaces are not in
the public stock Pono repository.

The detached Mazu run was
`neuroabs-i2c-gateway-final-20260823T234146Z`; its log, gateway snapshots,
generated artifacts, hashes, and Yosys validation log are retained at
`/var/tmp/neuroabs-runtime/runs/i2c-gateway-final-20260823T234146Z/`.
