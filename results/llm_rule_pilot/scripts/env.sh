# Sourced by the other scripts: tools, run directory and repository paths.
. /var/tmp/neuroabs-runtime/env-20261024.sh
RUN=/var/tmp/neuroabs-runtime/runs/llm-rule-20261027
R=${R:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}
P=$R/results/fine_gpr_choices/piccolo
export PYTHONPATH=/home/swear01/NeuroAbs/Pyverilog_NeuroAbs:$R/src
