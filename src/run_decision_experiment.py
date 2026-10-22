import argparse
import hashlib
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SRC_DIR)

ARMS = {
    'B1': {'backend': 'all-x', 'scope': 'constant'},
    'A1': {'backend': 'luna', 'scope': 'constant'},
    'A2': {'backend': 'luna-decision', 'scope': 'constant'},
    'A3': {'backend': 'luna-decision', 'scope': 'coi'},
}
LUNA_INPUT_PRICE = 0.10
LUNA_OUTPUT_PRICE = 0.50
RIC3_VERDICTS = {20: 'UNSAT', 10: 'SAT', 30: 'UNKNOWN'}


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


def usage_summary(records):
    calls = [r for r in records if r['status'] == 200]
    input_tokens = output_tokens = reasoning_tokens = 0
    for record in calls:
        usage = json.loads(record['response_raw'])['usage']
        input_tokens += usage['input_tokens']
        output_tokens += usage['output_tokens']
        reasoning_tokens += usage['output_tokens_details']['reasoning_tokens']
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


def unqualified(name):
    name = name.strip()
    if name.startswith('\\'):
        name = name[1:]
    return name.split('.')[-1]


def construct_arm(case, run_root, arm, cegar_timeout, session_id):
    arm_dir = prepare_arm_dir(case, run_root, arm)
    _, rtl, top, yosys_script = case_layout(case)
    config = ARMS[arm]
    env = dict(os.environ, LUNA_SESSION_ID=session_id)
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
    summary['generated_inputs'] = len(json.load(open(os.path.join(arm_dir, 'input_line.json'))))
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
    with tempfile.TemporaryDirectory(prefix='ric3-', dir=os.environ['RIC3_TMP_ROOT']) as tmp:
        env = dict(os.environ, RIC3_TMP_DIR=tmp)
        started = time.time()
        with open(log_path, 'w') as log:
            process = subprocess.run([ric3_bin, '--engine', 'portfolio', '--time-limit', str(time_limit), model],
                                     stdout=log, stderr=subprocess.STDOUT, env=env)
        elapsed = time.time() - started
    with open(log_path) as f:
        lines = [line.strip() for line in f if line.strip()]
    printed = next((line for line in reversed(lines) if line in ('UNSAT', 'SAT', 'UNKNOWN')), None)
    verdict = RIC3_VERDICTS.get(process.returncode)
    return {'seconds': elapsed, 'exit_status': process.returncode, 'printed': printed,
            'verdict': verdict if verdict == printed else 'ERROR'}


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
        json.dump({'ric3_bin': ric3_bin, 'time_limit': time_limit, 'parallel': parallel,
                   'repeats': repeats, 'runs': results, 'summary': summary}, f, indent=2)
    return summary


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    construct = sub.add_parser('construct')
    construct.add_argument('--case', required=True)
    construct.add_argument('--run-root', required=True)
    construct.add_argument('--arm', required=True, choices=['B0'] + sorted(ARMS))
    construct.add_argument('--cegar-timeout', type=int, required=True)
    construct.add_argument('--session-id', required=True)
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
            summary = construct_arm(args.case, os.path.abspath(args.run_root), args.arm, args.cegar_timeout, args.session_id)
        print(json.dumps(summary, indent=2))
    else:
        models = [tuple(item.split('=', 1)) for item in args.model]
        print(json.dumps(time_models(models, args.ric3, args.repeats, args.time_limit, args.parallel,
                                     os.path.abspath(args.output)), indent=2))


if __name__ == '__main__':
    main()
