# Sourced by the other scripts: tools of this host, run directory (local disk of each host) and repository paths.
if [ "$(hostname)" = zeus ]; then . /var/tmp/neuroabs-tools/env-20261024.sh; else . /var/tmp/neuroabs-runtime/env-20261024.sh; fi
RUN=/var/tmp/neuroabs-runtime/runs/llm-heldout-20261027
R=${R:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}
H=$R/results/llm_rule_heldout
CPUS=0,1,20,21/2,3,22,23/4,5,24,25/6,7,26,27/8,9,28,29/10,11,30,31/12,13,32,33/14,15,34,35/16,17,36,37
export PYTHONPATH=/home/swear01/NeuroAbs/Pyverilog_NeuroAbs:$R/src
