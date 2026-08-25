# NeuroAbs

This repository contains Python scripts for NeuroAbs RTL abstraction and
benchmark data.

## Citation

If you use NeuroAbs in your research, please cite our
[ICCAD 2026 paper](https://iccad.com/2026):

```bibtex
@inproceedings{yan2026neuroabs,
  title={NeuroAbs: A Neuro-Symbolic RTL Abstraction Framework for Property Checking Acceleration},
  author={Yan, Zhiyuan and Zhou, Xiaofeng and Zheng, Ziyue and Yang, Ziyi and Che, Wenbin and Zhang, Wei and Lyu, Yangdi and Zhang, Hongce},
  booktitle={Proceedings of the 2026 IEEE/ACM International Conference on Computer-Aided Design (ICCAD)},
  year={2026},
  url={https://iccad.com/2026}
}
```

## Layout

- `src/`: Python scripts and command-line entry points.
- `Flute_verification_done/`: Flute benchmarks.
- `Piccolo_verification_done/`: Piccolo benchmarks.
- `i2c/`: I2C benchmarks.
- `riscv_formal/`: Picorv32/riscv-formal benchmarks.
- `*.ys`: Yosys scripts used by the benchmark flows.

The benchmark directories keep the inputs and scripts needed to reproduce the
flows. Keep `description.txt` files because they describe the target property.
Generated artifacts such as extra `.txt` files, `input_line.json`,
`statement.json`, `.smt2` files, and `iter*` directories are intentionally not
tracked.

## Requirements

Use Python 3 and make sure the following tools and packages are available:

- Yosys
- Pono, for BTOR2/word-level CEGAR refinement
- rIC3, for portfolio formal proofs and optional kissat BMC exploration. A
  standalone `kissat` executable is not required with `--bmc-kissat`.
- z3, used by the Python abstraction scripts
- LLM API credentials/configuration

ABC and `.sby`/SymbiYosys are not required for the final experiments described
below. Some older logs and scripts in the repository use `gen_aiger.ys` and
ABC/BMC3, but the reproducible paths in this README use BTOR2 models with rIC3
portfolio proof or `rIC3 --engine bmc --bmc-kissat`.

This project uses the patched PyVerilog fork in `Pyverilog_NeuroAbs`.
It is part of this repository as a git submodule; use this fork rather than
upstream PyVerilog. After cloning the repository, initialize the submodule
and install the pinned reproduction dependencies before running the Python
scripts:

```bash
git submodule update --init --recursive
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-reproduce.txt
```

The Python scripts default to local tool paths used during development. For a
portable setup, override them with environment variables:

```bash
export YOSYS_BIN=/path/to/yosys
export PONO_BIN=/path/to/pono-neuroabs/build/pono
export RIC3_BIN=/path/to/rIC3
export RIC3_TMP_DIR=$PWD/.tmp/rIC3
export PYTHONPATH=$PWD/Pyverilog_NeuroAbs:$PWD/src:$PYTHONPATH
mkdir -p "$RIC3_TMP_DIR"
```

Make sure `RIC3_BIN` points to the executable itself. Modern rIC3 does not
accept the obsolete `-v 3` arguments found in the original artifact commands.

Yosys can be installed from a standard Yosys build or from oss-cad-suite.

Full CEGAR uses the public modern-Pono port of the Dynamic COI output expected
by `src/cegar.py`. Build it as follows:

```bash
git clone https://github.com/swear01/pono-neuroabs.git
cd pono-neuroabs
./contrib/setup-smt-switch.sh
./contrib/setup-btor2tools.sh
./configure.sh
cmake --build build --target pono-bin -j
export PONO_BIN=$PWD/build/pono
```

The default word-level CEGAR path only needs `--dynamic_coi_up_cex`. The old
`--pivot_input` extension is not ported because `src/cegar.py` does not enable
its `unsat_core` branch by default.

`src/main.py` calls an LLM through one of the API wrappers. The Mazu
reproduction uses DeepSeek V4 Flash with thinking disabled through the local
DeepSeek gateway:

```bash
curl http://127.0.0.1:35001/healthz
```

The client always targets `http://127.0.0.1:35001/v1`; gateway credentials
and upstream routing stay outside this repository.

## Common Commands

Generate an RTL abstraction wrapper:

```bash
python3 src/main.py -t <top_module> -d <description.txt> -f <prefix> <rtl_file.v>
```

The RTL file passed to `src/main.py` should be the original wrapper, such as
`wrapper.v`, `tst_bench_top.v`, or `picorv32_input.v`. The script compares it
against the corresponding constant-constrained file, such as
`wrapper_constant.v`, `tst_bench_top_constant.v`, or
`picorv32_input_constant.v`. It also creates a `*_noassert.v` copy for the
PyVerilog line-number analysis because PyVerilog does not parse the assertion
blocks used in these wrappers. Generated `problem_*.v` files are Yosys
intermediate outputs, not flow inputs.

`src/main.py` chooses a constant-propagation Yosys template automatically from
the benchmark path/top module. Use `--constant-template {flute,piccolo,i2c,picorv32}`
to override auto-detection. The Picorv32/register-aware flow is also selected
when `--use_register` is used with `--constant-template picorv32`.

Choose the LLM wrapper with `--api-backend`; the default is `gpt`.

For Muse Spark 1.2 Contributor, export `META_API_KEY` and use
`--api-backend meta`. This backend calls Meta Model API directly with model
`muse-spark-1.2-contributor`. Contributor prompts and completions may be used
by Meta to improve its models, so use it only with public benchmark inputs.

Run a formal proof with the same 3600-second cap used in the paper's RQ2:

```bash
"$RIC3_BIN" --engine portfolio --time-limit 3600 path/to/model.btor2
```

rIC3 returns status 20 for an `UNSAT`/safe proof. This is a successful proof
result even though generic process supervisors display the nonzero status.

Use BMC only for the paper's RQ3-style bounded exploration when formal proof
does not conclude:

```bash
python3 src/run_checker.py "$RIC3_BIN --engine bmc --bmc-kissat path/to/model.btor2"
```

`src/run_checker.py` records long-running BMC depths with a 23,600-second cap.
Set `RIC3_TMP_DIR` to a directory you own before running rIC3; otherwise a stale
shared `/tmp/rIC3` directory can make rIC3 fail during ABC/kissat preprocessing.
If ABC preprocessing itself fails after the temporary directory is writable,
rerun with `--no-abc`.

Run CEGAR:

```bash
python3 src/cegar.py -f <iter_output_dir> -y <yosys_script.ys> <wrapper_abstract_llm_new.v>
```

Pass the abstracted wrapper RTL to CEGAR. The script writes refined wrappers
under the directory given by `-f` and converts those wrappers with a temporary
Yosys script, leaving the original Yosys script unchanged. Use `gen_btor.ys` for
Flute/Piccolo/I2C cases and `gen_btor.ys` for Picorv32/riscv-formal cases; both
routes produce BTOR2 models, and `cegar.py` uses Pono with dynamic COI to decide
which abstracted inputs to refine.

## Examples

### Full Pipeline Examples

The correct experiment order is:

1. Run `src/main.py` on the original RTL input. The original input has a matching
   `*_constant.v`, and `main.py` writes or refreshes the matching
   `*_noassert.v`, `wrapper_abstract_llm_new.v`, `statement.json`, and
   `input_line.json`.
2. Run `src/cegar.py` on `wrapper_abstract_llm_new.v` using the case's BTOR2
   Yosys script.
3. Run rIC3 portfolio formal proof on the final BTOR2 produced by CEGAR.
4. Only when formal proof does not conclude, run kissat BMC to compare bounded
   exploration depth.

Set tool paths once from the repository root:

```bash
export YOSYS_BIN=/path/to/yosys
export PONO_BIN=/path/to/pono-neuroabs/build/pono
export RIC3_BIN=/path/to/rIC3
export RIC3_TMP_DIR=$PWD/.tmp/rIC3
export PYTHONPATH=$PWD/Pyverilog_NeuroAbs:$PWD/src:$PYTHONPATH
mkdir -p "$RIC3_TMP_DIR"
```

Flute example:

```bash
python3 -u src/main.py -t wrapper --constant-template flute \
  -f RTL -d Flute_verification_done/BGE/description.txt \
  Flute_verification_done/BGE/wrapper.v

python3 src/cegar.py --timeout 30 \
  -f readme_iter_btor \
  -y Flute_verification_done/BGE/gen_btor.ys \
  Flute_verification_done/BGE/wrapper_abstract_llm_new.v

"$RIC3_BIN" --engine portfolio --time-limit 3600 \
  Flute_verification_done/BGE/readme_iter_btor/1.btor2

# If the formal proof does not conclude:
python3 src/run_checker.py "$RIC3_BIN --bmc-kissat --engine bmc \
  Flute_verification_done/BGE/readme_iter_btor/1.btor2"
```

Piccolo example:

```bash
python3 -u src/main.py -t wrapper --constant-template piccolo \
   -f RTL \
  -d Piccolo_verification_done/ANDI/description.txt \
  Piccolo_verification_done/ANDI/wrapper.v

python3 src/cegar.py --timeout 30 \
  -f readme_iter_btor \
  -y Piccolo_verification_done/ANDI/gen_btor.ys \
  Piccolo_verification_done/ANDI/wrapper_abstract_llm_new.v

"$RIC3_BIN" --engine portfolio --time-limit 3600 \
  Piccolo_verification_done/ANDI/readme_iter_btor/3.btor2

# If the formal proof does not conclude:
python3 src/run_checker.py "$RIC3_BIN --bmc-kissat --engine bmc \
  Piccolo_verification_done/ANDI/readme_iter_btor/3.btor2"
```

I2C example:

```bash
python3 -u src/main.py -t tst_bench_top --constant-template i2c \
  --api-backend deepseek \
   -f RTL \
  -d i2c/i2c_assert1/description.txt \
  i2c/i2c_assert1/tst_bench_top.v

python3 src/cegar.py --timeout 60 \
  -f readme_iter_btor \
  -y i2c/i2c_assert1/gen_btor.ys \
  i2c/i2c_assert1/wrapper_abstract_llm_new.v

"$RIC3_BIN" --engine portfolio --time-limit 3600 \
  i2c/i2c_assert1/readme_iter_btor/0.btor2
```

Picorv32/riscv-formal example:

```bash
python3 -u src/main.py -t picorv32 --constant-template picorv32 \
  --use_register  -f RTL \
  -d riscv_formal/riscv_formal_add/description.txt \
  riscv_formal/riscv_formal_add/picorv32_input.v

python3 src/cegar.py --timeout 30 \
  -f readme_iter_btor \
  -y riscv_formal/riscv_formal_add/design.ys \
  riscv_formal/riscv_formal_add/wrapper_abstract_llm_new.v

"$RIC3_BIN" --engine portfolio --time-limit 3600 \
  riscv_formal/riscv_formal_add/readme_iter_btor/1.btor2
```

The public tree does not currently contain the generated
`wrapper_abstract_llm_new.v`, `statement.json`, or `input_line.json` files.
Run `main.py` to create them before attempting CEGAR.

### Mazu initial reproduction

The verified Mazu setup keeps the repository under `/home/swear01/NeuroAbs`
and the large tool/runtime files on Mazu-local storage:

```bash
cd /home/swear01/NeuroAbs
git submodule update --init --recursive

export OSS_CAD_SUITE=/var/tmp/neuroabs-tools/2026-08-23/oss-cad-suite
export YOSYS_BIN="$OSS_CAD_SUITE/bin/yosys"
export VIRTUAL_ENV=/var/tmp/neuroabs-runtime/venv
export PATH="$VIRTUAL_ENV/bin:$OSS_CAD_SUITE/bin:$PATH"
export LD_LIBRARY_PATH="$OSS_CAD_SUITE/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

uv venv --python "$OSS_CAD_SUITE/py3bin/python3.11" "$VIRTUAL_ENV"
uv pip install --python "$VIRTUAL_ENV/bin/python" -r requirements-reproduce.txt
python -m unittest tests/test_deepseek_backend.py
python -u src/main.py -t tst_bench_top --constant-template i2c \
  --api-backend deepseek -f RTL \
  -d i2c/i2c_assert1/description.txt \
  i2c/i2c_assert1/tst_bench_top.v
```

`deepseek-gateway` must be active on `127.0.0.1:35001` for the last command.
The OSS CAD Suite archive used here is release `2026-08-23`, SHA-256
`063d7b4f5663271cf04529ba22266e21baa9e3431b236fe71e1bf589d6d8816a`.

The first Mazu run and its candidate-signal artifact are recorded in
[`results/i2c_assert1/`](results/i2c_assert1/README.md).

## Runtime Notes

`src/main.py` first parses the RTL, runs constant propagation, extracts
candidate signals, and then calls the configured LLM to generate abstracted
RTL. A full run can take a long time and consumes LLM API quota.
Candidate extraction compares named wires removed by Yosys `OPT_CLEAN` in the
constant-constrained model against those removed in the normal model.

For CEGAR debugging, set `CEGAR_VERBOSE=1` to print every refined signal. The
Pono/BTOR2 backend uses bound 25 in `src/cegar.py`; use
`src/cegar.py --timeout <seconds>` to cap each Pono query.

Pono may return `unknown` on a refined BTOR2 model. In that case the script
stops cleanly and writes the CEGAR timing seen so far. This bounded CEGAR query
is not a property proof; run rIC3 portfolio proof on the last refined BTOR2.
Use BMC depth exploration only if that proof does not conclude.

`iter_btor` directories are generated by `src/cegar.py` or related
Yosys/checker flows. They are not tracked in git. Generate them locally before
checking a specific `iter_btor/*.btor2` file.

`src/run_checker.py` prints checker output as it runs. If the checker output
contains `bmc depth:`, the script also writes a `bmc_depth_*.csv` report; this
CSV is a generated artifact and is not tracked.

If `rIC3` reports a permission error under `/tmp/rIC3`, set `RIC3_TMP_DIR` to a
directory owned by the current user and rerun the checker.
