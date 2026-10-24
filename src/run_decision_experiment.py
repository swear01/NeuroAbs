import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from deepseek_prices import usage_cost

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SRC_DIR)

ARMS = {
    'B1': {'backend': 'all-x', 'scope': 'constant'},
    'A1': {'backend': 'luna', 'scope': 'constant'},
    'A2': {'backend': 'luna-decision', 'scope': 'constant'},
    'A3': {'backend': 'luna-decision', 'scope': 'coi'},
    'D1': {'backend': 'deepseek-generate', 'scope': 'constant'},
    'D2': {'backend': 'deepseek-decision', 'scope': 'constant'},
    'D3': {'backend': 'deepseek-decision', 'scope': 'coi'},
}
LUNA_INPUT_PRICE = 0.10
LUNA_OUTPUT_PRICE = 0.50
RIC3_KILL_GRACE = 60


def sha256(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def run_logged(command, cwd, log_path, env=None):
    started = time.time()
    with open(log_path, 'w') as log:
        process = subprocess.run(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, env=env)
    return process.returncode, time.time() - started


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def case_layout(case):
    return os.path.join(PROJECT_ROOT, case), 'picorv32_input.v', 'picorv32', 'design.ys'


def prepare_arm_dir(case, run_root, arm):
    case_dir, _, _, _ = case_layout(case)
    arm_dir = os.path.join(run_root, os.path.basename(case), arm)
    if os.path.exists(arm_dir):
        raise FileExistsError(arm_dir)
    shutil.copytree(case_dir, arm_dir)
    return arm_dir


def build_concrete(case, run_root):
    arm_dir = prepare_arm_dir(case, run_root, 'B0')
    _, rtl, _, yosys_script = case_layout(case)
    code = (
        'import sys, os; sys.path.insert(0, {src!r}); os.chdir({cwd!r}); '
        'from cegar import run_yosys_init; '
        'print(run_yosys_init({ys!r}, {rtl!r}))'
    ).format(src=SRC_DIR, cwd=arm_dir, ys=os.path.join(arm_dir, yosys_script), rtl=os.path.join(arm_dir, rtl))
    returncode, elapsed = run_logged([sys.executable, '-c', code], arm_dir, os.path.join(arm_dir, 'concrete_yosys.log'))
    model = os.path.join(arm_dir, rtl.replace('.v', '.btor2'))
    summary = {
        'arm': 'B0',
        'case': case,
        'yosys_returncode': returncode,
        'yosys_seconds': elapsed,
        'final_model': model if returncode == 0 else None,
        'final_model_sha256': sha256(model) if returncode == 0 else None,
    }
    with open(os.path.join(arm_dir, 'arm_summary.json'), 'w') as f:
        json.dump(summary, f, indent=2)
    return summary


def final_iteration_model(iter_dir):
    best = None
    for name in os.listdir(iter_dir):
        match = re.fullmatch(r'(\d+)\.btor2', name)
        if match and (best is None or int(match.group(1)) > best[0]):
            best = (int(match.group(1)), name)
    if best is None:
        return None, None
    return best[0], os.path.join(iter_dir, best[1])


def effective_locations(verilog_path):
    locations = []
    with open(verilog_path) as f:
        for number, line in enumerate(f, 1):
            if re.search(r'\binput\d+\b', line) and 'input wire' not in line and not re.fullmatch(r'\s*input\d+,\s*', line):
                locations.append(number)
    return locations


def remaining_inputs(verilog_path):
    names = set()
    with open(verilog_path) as f:
        for line in f:
            if 'input wire' in line or re.fullmatch(r'\s*input\d+,\s*', line):
                continue
            names.update(re.findall(r'\binput\d+\b', line))
    return names


def successful_responses(records):
    responses = []
    for record in records:
        if record['status'] != 200:
            continue
        try:
            responses.append((record, json.loads(record['response_raw'])))
        except json.JSONDecodeError:
            continue
    return responses


def usage_summary(records):
    responses = successful_responses(records)
    calls = [record for record, _ in responses]
    input_tokens = output_tokens = reasoning_tokens = 0
    for _, response in responses:
        usage = response.get('usage') or {}
        input_tokens += usage.get('input_tokens', 0)
        output_tokens += usage.get('output_tokens', 0)
        reasoning_tokens += (usage.get('output_tokens_details') or {}).get('reasoning_tokens', 0)
    return {
        'successful_calls': len(calls),
        'http_attempts': len(records),
        'rate_limited_attempts': sum(r['status'] == 429 for r in records),
        'failed_attempts': sum(r['status'] != 200 for r in records),
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'reasoning_tokens': reasoning_tokens,
        'estimated_list_price_usd': input_tokens / 1e6 * LUNA_INPUT_PRICE + output_tokens / 1e6 * LUNA_OUTPUT_PRICE,
    }


def deepseek_usage_summary(records):
    responses = successful_responses(records)
    calls = [record for record, _ in responses]
    usages = [response.get('usage') or {} for _, response in responses]
    return {
        'successful_calls': len(calls),
        'http_attempts': len(records),
        'rate_limited_attempts': sum(r['status'] == 429 for r in records),
        'failed_attempts': sum(r['status'] != 200 for r in records),
        'models': sorted({response.get('model') for _, response in responses} - {None}),
        'prompt_tokens': sum(u.get('prompt_tokens', 0) for u in usages),
        'cached_tokens': sum((u.get('prompt_tokens_details') or {}).get('cached_tokens', 0) or 0 for u in usages),
        'completion_tokens': sum(u.get('completion_tokens', 0) for u in usages),
        'reasoning_tokens': sum((u.get('completion_tokens_details') or {}).get('reasoning_tokens', 0) or 0
                                for u in usages),
        'call_seconds_median': statistics.median(r['elapsed_seconds'] for r in calls) if calls else None,
        'estimated_peak_list_price_usd': sum(usage_cost(u) for u in usages),
    }


def unqualified(name):
    name = name.strip()
    if name.startswith('\\'):
        name = name[1:]
    return name.split('.')[-1]


def construct_arm(case, run_root, arm, cegar_timeout, session_id, budget_usd):
    arm_dir = prepare_arm_dir(case, run_root, arm)
    _, rtl, top, yosys_script = case_layout(case)
    config = ARMS[arm]
    env = dict(os.environ, LUNA_SESSION_ID=session_id)
    if budget_usd is not None:
        env['LLM_BUDGET_USD'] = str(budget_usd)
    main_command = [
        sys.executable, '-u', os.path.join(SRC_DIR, 'main.py'),
        '-t', top, '--constant-template', 'picorv32', '--use_register', '-f', 'RTL',
        '--api-backend', config['backend'], '--candidate-scope', config['scope'],
        '-d', os.path.join(arm_dir, 'description.txt'), os.path.join(arm_dir, rtl),
    ]
    main_code, main_seconds = run_logged(main_command, arm_dir, os.path.join(arm_dir, 'main.log'), env)
    summary = {'arm': arm, 'case': case, 'session_id': session_id, 'main_command': main_command,
               'main_returncode': main_code, 'construction_seconds': main_seconds}
    records = read_jsonl(os.path.join(arm_dir, 'rewrite_records.jsonl'))
    summary['requests'] = len(records)
    summary['decisions'] = {
        'x': sum(r.get('decision') is not None and r['decision']['answer'] == 'x' for r in records),
        'keep': sum(r.get('decision') is not None and r['decision']['answer'] == 'keep' for r in records),
        'invalid': sum(r['check'] == 'invalid' for r in records),
    }
    summary['checks'] = {
        result: sum(r['check'] == result for r in records) for result in ('unsat', 'sat', 'error', 'keep', 'invalid')
    }
    summary['luna'] = usage_summary(read_jsonl(os.path.join(arm_dir, 'luna_calls.jsonl')))
    summary['deepseek'] = deepseek_usage_summary(read_jsonl(os.path.join(arm_dir, 'deepseek_calls.jsonl')))
    for name in ('time_constant_prop.txt', 'time_candidate_scope.txt', 'time.txt'):
        path = os.path.join(arm_dir, name)
        if os.path.exists(path):
            with open(path) as f:
                summary[name] = f.read()
    if main_code != 0:
        summary['failure'] = 'main.py failed'
        return write_summary(arm_dir, summary)

    if os.path.exists(os.path.join(arm_dir, 'abstract_result.txt')):
        strict_code, _ = run_logged([
            sys.executable, os.path.join(SRC_DIR, 'strict_oa.py'), '--project', PROJECT_ROOT,
            '--rtl', os.path.join(arm_dir, rtl.replace('.v', '_noassert.v')), '--top', top,
            '--results', os.path.join(arm_dir, 'abstract_result.txt'),
            '--output', os.path.join(arm_dir, 'strict_oa_report.json'),
        ], arm_dir, os.path.join(arm_dir, 'strict_oa.log'))
        summary['strict_oa_returncode'] = strict_code
        if strict_code == 0:
            with open(os.path.join(arm_dir, 'strict_oa_report.json')) as f:
                summary['strict_oa'] = json.load(f)['summary']

    wrapper = os.path.join(arm_dir, 'wrapper_abstract_llm_new.v')
    with open(os.path.join(arm_dir, 'input_line.json')) as f:
        summary['generated_inputs'] = len(json.load(f))
    summary['initial_effective_locations'] = len(effective_locations(wrapper))
    cegar_command = [
        sys.executable, os.path.join(SRC_DIR, 'cegar.py'), '--timeout', str(cegar_timeout),
        '-f', 'iter_btor', '-y', os.path.join(arm_dir, yosys_script), wrapper,
    ]
    cegar_code, cegar_seconds = run_logged(cegar_command, arm_dir, os.path.join(arm_dir, 'cegar.log'))
    summary.update({'cegar_command': cegar_command, 'cegar_returncode': cegar_code, 'cegar_seconds': cegar_seconds})
    with open(os.path.join(arm_dir, 'cegar.log')) as f:
        cegar_log = f.read()
    summary['cegar_pono_unknown'] = 'Pono returned unknown' in cegar_log
    summary['cegar_pono_timeouts'] = cegar_log.count('Pono timed out')
    summary['cegar_property_fail'] = 'The property fail' in cegar_log
    iteration, model = final_iteration_model(os.path.join(arm_dir, 'iter_btor')) if os.path.isdir(os.path.join(arm_dir, 'iter_btor')) else (None, None)
    summary['cegar_refinements'] = iteration
    if cegar_code != 0 or model is None or summary['cegar_property_fail']:
        summary['failure'] = 'CEGAR did not produce a final model'
        return write_summary(arm_dir, summary)
    final_verilog = model.replace('.btor2', '.v')
    summary['final_model'] = model
    summary['final_model_sha256'] = sha256(model)
    summary['final_effective_locations'] = len(effective_locations(final_verilog))
    final_inputs = remaining_inputs(final_verilog)
    summary['final_inputs'] = len(final_inputs)
    with open(os.path.join(arm_dir, 'input_signal.json')) as f:
        input_signal = json.load(f)
    with open(os.path.join(arm_dir, 'candidate_signals_constant.txt')) as f:
        constant_names = {unqualified(line) for line in f if line.strip()}
    outside = sorted({input_signal[name] for name in final_inputs if unqualified(input_signal[name]) not in constant_names})
    summary['final_x_signals_outside_constant_scope'] = outside
    summary['final_x_inputs_outside_constant_scope'] = sum(
        unqualified(input_signal[name]) not in constant_names for name in final_inputs
    )
    return write_summary(arm_dir, summary)


def write_summary(arm_dir, summary):
    with open(os.path.join(arm_dir, 'arm_summary.json'), 'w') as f:
        json.dump(summary, f, indent=2)
    return summary


def run_ric3(ric3_bin, model, time_limit, log_path):
    started = time.time()
    with open(log_path, 'w') as log:
        process = subprocess.Popen([ric3_bin, 'check', '--ui', 'false', model, 'portfolio', '--time-limit', str(time_limit)],
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            process.wait(timeout=time_limit + RIC3_KILL_GRACE)
            timed_out = False
        except subprocess.TimeoutExpired:
            timed_out = True
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
    elapsed = time.time() - started
    if timed_out:
        return {'seconds': elapsed, 'exit_status': None, 'printed': None, 'verdict': 'TIMEOUT'}
    with open(log_path) as f:
        lines = [line.strip() for line in f if line.strip()]
    printed = lines[-1] if lines and lines[-1] in ('UNSAT', 'SAT', 'UNKNOWN') else None
    verdict = printed if process.returncode == 0 and printed else 'ERROR'
    return {'seconds': elapsed, 'exit_status': process.returncode, 'printed': printed, 'verdict': verdict}


def time_models(models, ric3_bin, repeats, time_limit, parallel, output):
    jobs = [(label, model, rep) for rep in range(1, repeats + 1) for label, model in models]
    log_dir = os.path.join(os.path.dirname(output), 'ric3_logs')
    os.makedirs(log_dir, exist_ok=True)

    def execute(job):
        label, model, rep = job
        result = run_ric3(ric3_bin, model, time_limit, os.path.join(log_dir, '{:s}.{:d}.log'.format(label, rep)))
        result.update({'label': label, 'model': model, 'repeat': rep})
        print(json.dumps(result), flush=True)
        return result

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        results = list(pool.map(execute, jobs))
    summary = {}
    for label, model in models:
        runs = [r for r in results if r['label'] == label]
        summary[label] = {
            'model': model,
            'model_sha256': sha256(model),
            'verdicts': sorted({r['verdict'] for r in runs}),
            'median_seconds': statistics.median(r['seconds'] for r in runs),
            'seconds': [r['seconds'] for r in runs],
        }
    with open(output, 'w') as f:
        json.dump({'ric3_bin': ric3_bin, 'cpu_affinity': sorted(os.sched_getaffinity(0)),
                   'time_limit': time_limit, 'parallel': parallel,
                   'repeats': repeats, 'runs': results, 'summary': summary}, f, indent=2)
    return summary


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    construct = sub.add_parser('construct')
    construct.add_argument('--case', required=True)
    construct.add_argument('--run-root', required=True)
    construct.add_argument('--arm', required=True, choices=['B0'] + sorted(ARMS))
    construct.add_argument('--cegar-timeout', type=int, help='required for every arm except B0')
    construct.add_argument('--session-id', help='required for every arm except B0')
    construct.add_argument('--budget-usd', type=float, help='stop DeepSeek calls once this list price is spent')
    timing = sub.add_parser('time')
    timing.add_argument('--model', action='append', required=True, help='label=path')
    timing.add_argument('--ric3', required=True)
    timing.add_argument('--repeats', type=int, required=True)
    timing.add_argument('--time-limit', type=int, required=True)
    timing.add_argument('--parallel', type=int, required=True)
    timing.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.command == 'construct':
        if args.arm == 'B0':
            summary = build_concrete(args.case, os.path.abspath(args.run_root))
        else:
            if args.cegar_timeout is None or args.session_id is None:
                parser.error('--cegar-timeout and --session-id are required for arm {:s}'.format(args.arm))
            summary = construct_arm(args.case, os.path.abspath(args.run_root), args.arm, args.cegar_timeout, args.session_id,
                                    args.budget_usd)
        print(json.dumps(summary, indent=2))
    else:
        models = []
        for item in args.model:
            label, separator, path = item.partition('=')
            if not separator or not label or not path:
                parser.error('--model expects label=path, got {!r}'.format(item))
            if label in dict(models):
                parser.error('duplicate --model label {!r}'.format(label))
            models.append((label, path))
        print(json.dumps(time_models(models, args.ric3, args.repeats, args.time_limit, args.parallel,
                                     os.path.abspath(args.output)), indent=2))


if __name__ == '__main__':
    main()
