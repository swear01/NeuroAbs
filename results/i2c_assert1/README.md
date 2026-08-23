# I2C `i2c_assert1` initial reproduction

This result was produced on Mazu from commit
`9cc42960abdff6e4d9336d0dbd1e8e4b07f43ab9` on 2026-08-24 (Asia/Taipei).

## Environment

- Python 3.11.6
- Yosys 0.68+120 (`a34d3baae`)
- OSS CAD Suite 2026-08-23
- DeepSeek model: `deepseek-v4-flash`, thinking disabled

## Command

```bash
python -u src/main.py -t tst_bench_top --constant-template i2c \
  --api-backend deepseek -f RTL \
  -d i2c/i2c_assert1/description.txt \
  i2c/i2c_assert1/tst_bench_top.v
```

## Result

The constant-propagation stage completed in 0.290156 seconds. Yosys reported
one removed named RTL wire in the normal model and 63 in the constrained
model. Their set difference contains 62 candidate signals, recorded in
[`candidate_signals.txt`](candidate_signals.txt). Pyverilog localized 37 of
those signals to source statements.

The run reached the first real LLM abstraction request, then stopped because
the DeepSeek API returned HTTP 402 `Insufficient Balance`. No alternative
model or synthetic response was used, so this is a partial reproduction: the
candidate-discovery stage is reproduced, while LLM abstraction and downstream
CEGAR remain pending API credit and the unavailable public Pono fork described
in the root README.

The detached Mazu run was
`neuroabs-i2c-assert1-20260823T205421Z`; its local log is retained at
`/var/tmp/neuroabs-runtime/runs/i2c-assert1-20260823T205421Z/run.log`.
