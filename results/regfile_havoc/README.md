# Register-file havoc on PicoRV32 riscv-formal checks

The question: the `rvfi_insn_check` property relates the checked
instruction's `rvfi_rs1_rdata`/`rvfi_rs2_rdata` to its `rvfi_rd_wdata`, not to
what the register file holds. If every `cpuregs` read returns an unconstrained
value, do the nine checks stay UNSAT? And how much faster is rIC3 once the
1024 register-file bits are gone?

They all stay UNSAT. k = 0 (no tracked address) proves all nine cases on both
bases. rIC3 medians drop to 0.38–0.69 of B0 (geometric mean 0.56).

## Method

`src/regfile_havoc.py build` copies an arm directory's top-level sources,
rewrites the PicoRV32 Verilog and runs the case's `design.ys` through the same
`cegar.run_yosys_init` call that B0 uses.

- H0: B0 `picorv32_input.v` with havoc.
- H1: the B1 final model's Verilog (`iter_btor/<n>.v` next to `final_model`,
  i.e. all-X + CEGAR) with the same havoc.

With `ENABLE_REGS_DUALPORT=1` and `PICORV32_REGS` undefined, the active reads
are the three combinational read-port statements. Each one is rewritten from
`cpuregs[decoded_rsN]` to `$anyseq`. That is the expression riscv-formal's own
`RISCV_FORMAL_BLACKBOX_REGS` branch uses, and it gives each port a separate
fresh value on every cycle:

```verilog
cpuregs_rs1 = decoded_rs1 ? $anyseq : 0;
cpuregs_rs2 = decoded_rs2 ? $anyseq : 0;
cpuregs_rs1 = decoded_rs  ? $anyseq : 0;   // single-port branch, inactive here
```

The x0 mux stays, so x0 still reads 0. The writes are left in place, and Yosys
drops the array because nothing reads it. The script refuses to run if any
other `cpuregs` read is active. The `dbg_reg_x*` wires sit under
`` `ifdef DEBUGREGS ``, which is defined neither in `picorv32_input.v` nor in
`defines.sv`; no `dbg_reg` node appears in the B0 BTOR2.

`--k 1` (tracking one `$anyconst` address with a shadow register that the real
write port updates) is implemented. It was only smoke-built for ADD, because
k = 0 already proves every case.

Reproduce: `results/regfile_havoc/build.sh`, then
`results/regfile_havoc/timing-chain.sh H0 H1`. The table comes from
`python results/regfile_havoc/make_table.py <H0 timing.json> <H1 timing.json>`.

## Soundness

Replacing a read value with a fresh input over-approximates the design. Take any
B0 trace. In each cycle, choose the `$anyseq` value equal to
`cpuregs[decoded_rsN]`. The H0 trace then matches the B0 trace on every
remaining signal, because after the rewrite nothing else reads `cpuregs`
(checked by the script). So every B0 behaviour is an H0 behaviour, and UNSAT on
H0 implies UNSAT on B0. The same argument applied to B1 gives H1 ⊇ B1 ⊇ B0.

`src/check.py` `check_implies` agrees for all three rewritten statements
(`check_implies_run.py`, `check_implies.log`). The original read is modelled as
an opaque 32-bit `cpuregs_read_*` operand, because the statement parser has no
array semantics. `cpuregs_rsN = rs ? cpuregs_read : 32'h0` ⇒
`cpuregs_rsN = rs ? 'bx : 32'h0` is `unsat` (sound). The negative control
`... : 32'h1` is `sat`. The rewrite is strict: H0 lets a read return a value
that was never written.

## Model size

`python src/regfile_havoc.py stats`, identical for all nine cases
(`stats-k0.txt`). "Register bits" counts states that have a `next` function;
`$anyseq`/`$anyconst` states have none. This is why B0 shows 2585 here rather
than the 2980 total state bits.

| Model | Registers | Register bits | `cpuregs` bits | COI registers | COI register bits | BTOR2 nodes (ADD) | COI nodes (ADD) |
|---|---|---|---|---|---|---|---|
| B0 | 209 | 2585 | 1024 | 197 | 2312 | 3956 | 3444 |
| H0 | 175 | 1551 | 0 | 163 | 1278 | 3685 | 3173 |
| H1 | 175 | 1551 | 0 | 163 | 1278 | 3727 | 3199 |

Havoc removes 1034 register bits: the 32 × 32 `cpuregs` registers and 2
unnamed registers (10 bits in total) that Yosys also drops. H1 has more COI inputs
than H0 (93–95 vs 79) because of B1's X inputs. SH's B1 has no X left after
CEGAR, so SH H1 matches H0 in size.

## rIC3 timing

`run_decision_experiment.py time`, `taskset -c 16-31` (E-cores, nothing else
running on them), parallel 1, 3 repeats, 3600 s cap. The B0/B1 medians are the
pinned E-core medians from
[`../decision_experiment/README.md`](../decision_experiment/README.md).

| Case | H0 runs (s) | H0 median | H0 verdict | H0/B0 | H0/B1 | H1 runs (s) | H1 median | H1 verdict | H1/B0 | H1/B1 |
|---|---|---|---|---|---|---|---|---|---|---|
| ADD | 73.3, 73.1, 72.8 | 73.1 | UNSAT | 0.60 | 0.57 | 70.0, 70.0, 68.4 | 70.0 | UNSAT | 0.57 | 0.55 |
| ADDI | 83.1, 83.4, 84.2 | 83.4 | UNSAT | 0.61 | 0.57 | 91.4, 89.8, 90.6 | 90.6 | UNSAT | 0.66 | 0.62 |
| AND | 60.9, 59.1, 59.0 | 59.1 | UNSAT | 0.49 | 0.60 | 59.6, 59.0, 59.8 | 59.6 | UNSAT | 0.49 | 0.60 |
| BGE | 103.2, 101.0, 105.2 | 103.2 | UNSAT | 0.51 | 0.55 | 115.9, 117.7, 119.2 | 117.7 | UNSAT | 0.58 | 0.63 |
| ORI | 65.7, 66.8, 66.0 | 66.0 | UNSAT | 0.64 | 0.63 | 61.5, 62.6, 62.0 | 62.0 | UNSAT | 0.60 | 0.59 |
| SH | 122.8, 119.6, 119.7 | 119.7 | UNSAT | 0.67 | 0.66 | 122.4, 123.3, 121.3 | 122.4 | UNSAT | 0.69 | 0.68 |
| SLTI | 59.9, 58.8, 59.8 | 59.8 | UNSAT | 0.38 | 0.60 | 60.5, 59.4, 59.1 | 59.4 | UNSAT | 0.38 | 0.59 |
| SUB | 94.3, 92.1, 93.7 | 93.7 | UNSAT | 0.66 | 0.62 | 83.7, 81.6, 84.1 | 83.7 | UNSAT | 0.59 | 0.55 |
| XOR | 63.8, 61.6, 63.3 | 63.3 | UNSAT | 0.60 | 0.56 | 59.4, 60.0, 59.4 | 59.4 | UNSAT | 0.56 | 0.53 |

- Geometric means: H0/B0 0.56, H0/B1 0.59, H1/B0 0.56, H1/B1 0.59. Summed
  medians: H0 721 s vs B0 1270 s.
- All-X on top of the havoc adds nothing: per-case H1/H0 ranges from 0.89 (SUB)
  to 1.14 (BGE), with a geometric mean of 1.00. Removing the register file is
  worth more than every B1 rewrite combined.
- The slowest run of a model is at most 1.04 times its fastest.
- The winning portfolio worker is the same for B0 and H0:
  `kind --step 1 --simple-path`.

## Verdicts

H0 and H1 are UNSAT on all nine cases. No case was SAT, so no counterexample
needed checking. The smallest k that proves every case is 0.

## Environment

- Same machine, Yosys, Python and rIC3 as
  [`../decision_experiment/README.md`](../decision_experiment/README.md):
  rIC3 `master` `8c6df1b`, SHA-256
  `90e7141bc92521fdc4cdbbf4310b1d953eee4aec4007c6ddb4fd1625ee696977`,
  `ric3 check --ui false model.btor2 portfolio --time-limit 3600`.
- Timing ran at base commit `7a5b4c3` plus the then-untracked
  `src/regfile_havoc.py` (`commit.txt`/`status.txt` in each timing directory).
- Outputs live in `/var/tmp/neuroabs-runtime/runs/regfile-havoc-20261025/`:
  `riscv_formal_<case>/{H0,H1}/` (RTL, BTOR2, Yosys log, `havoc_summary.json`),
  `timing-ric3-8c6df1b-{H0,H1}/` (timing.json, rIC3 logs) and `check_implies/`.
  `k1-smoke/` holds the k = 1 ADD build, which was not timed.
- H0 BTOR2 SHA-256 prefixes: ADD `e2b38b6987b9`, ADDI `ebb397ba4d19`,
  AND `e6b03434bcfb`, BGE `9faa88944dff`, ORI `e04e1376ff3e`, SH `835873a1c2b3`,
  SLTI `a034ae09b934`, SUB `60e2cb5e598e`, XOR `c8378cd93deb`.
- H1 BTOR2 SHA-256 prefixes: ADD `e1517ebdf70d`, ADDI `54cef1610e9c`,
  AND `fa5d28e6e109`, BGE `eeeaceee9d3e`, ORI `1a8aac1d0818`, SH `00549e4b0a43`,
  SLTI `14a018ae0a67`, SUB `d92804e511f3`, XOR `0125ab14fd7a`.
