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

## Muse Contributor 1.2 preliminary reproduction

This run used commit `9d4f6912232974938e635a9b81a985dc0fdfff32`, the
`meta` backend, and `muse-spark-1.2-contributor` on Mazu. Muse completed all
184 statement requests in 7154.236821 seconds. All 184 soundness implication
checks were `unsat`; none were `sat`.

The generated wrapper is 30,817 bytes with SHA-256
`9b4a8430a4eca9720e794a5cccf3ff6a9b55584f90f36c03b576795e5bc5ac43`.
Modern Pono returned `unknown` through bound 25, so CEGAR completed with zero
refinements. Its final `iter/0.btor2` is 53,908 bytes with SHA-256
`46efa51efec968aefb24cedb2e314ec6f85e852c3439839000f1187b84eb08c2`.

The final checker is rIC3/Kissat BMC with the repository's 23,600-second
runtime cap. At the 2026-08-26 00:26 Asia/Taipei snapshot, it had completed
depth 4093 without finding a counterexample and was still solving depth 4094.
For the deadline report, if no later depth completes before the cap, the
provisional result is: **timeout after 23,600 seconds; no counterexample found
through depth 4093; depth 4094 unresolved**. This is bounded evidence, not an
unbounded proof of the property, and must be replaced with the final checker
output after the run ends.

### Preliminary comparison and conclusion

| Run | LLM abstraction time | Soundness checks | Final BMC |
| --- | ---: | ---: | --- |
| DeepSeek V4 Flash | 6177.197376 s | 184/184 `unsat` | No same-cap result yet |
| Muse Contributor 1.2 | 7154.236821 s | 184/184 `unsat` | Ongoing; provisional cap at depth 4093 |

Muse therefore reproduces the abstraction, soundness, and CEGAR stages. It
does not yet demonstrate a speedup: its abstraction stage was 977.039445
seconds (15.8%) slower than the earlier DeepSeek run, and there is no
same-machine, same-cap final-checker baseline yet.

The next required experiment is to run the same rIC3/Kissat command on the
DeepSeek abstract model and the concrete model on Mazu with the same
23,600-second cap. Report checker-only time or maximum completed depth at the
cap separately from end-to-end time, which includes LLM abstraction,
soundness checking, and CEGAR.
