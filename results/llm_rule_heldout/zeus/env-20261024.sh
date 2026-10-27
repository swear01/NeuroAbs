export OSS_CAD_SUITE=/var/tmp/neuroabs-tools/2026-10-22/oss-cad-suite
export YOSYS_BIN="$OSS_CAD_SUITE/bin/yosys"
export VIRTUAL_ENV=/var/tmp/neuroabs-tools/venv-20261022
export PATH="$VIRTUAL_ENV/bin:$OSS_CAD_SUITE/bin:$PATH"
export LD_LIBRARY_PATH="$OSS_CAD_SUITE/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export RIC3_BIN=/var/tmp/neuroabs-tools/ric3-master-8c6df1b/ric3
