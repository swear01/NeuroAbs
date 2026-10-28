# Sourced by the other scripts: tools, run directory and repository paths on mazu.
. /var/tmp/neuroabs-runtime/env-20261024.sh
RUN=/var/tmp/neuroabs-runtime/runs/llm-heldout-20261027
R=${R:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}
H=$R/results/llm_rule_heldout
CPUS=0-3/4-7/8-11
export PYTHONPATH=/home/swear01/NeuroAbs/Pyverilog_NeuroAbs:$R/src
