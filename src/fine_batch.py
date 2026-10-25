"""Run fine_choice CEGAR on many sub-property specs in parallel, one CPU group per run.

Results are appended to results.jsonl in the work directory; specs that already
have a result are skipped, so an interrupted batch can be resumed.
"""
import argparse
import json
import os
import queue
import subprocess
import sys
import threading

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def summary(name, workdir):
    with open(os.path.join(workdir, "cegar.json")) as f:
        result = json.load(f)
    return {
        "name": name,
        "status": result["status"],
        "refinements": result["refinements"],
        "total_seconds": result["total_seconds"],
        "build_seconds": sum(r["build_seconds"] for r in result["history"]),
        "ric3_seconds": sum(r["ric3_seconds"] for r in result["history"]),
        "replay_seconds": sum(r.get("replay_seconds", 0) for r in result["history"]),
        "final_coi_state_bits": result["history"][-1]["coi_state_bits"],
        "final_spec": result["final_spec"],
        "iterations": [{k: r.get(k) for k in ("ric3", "ric3_seconds", "cex_depth", "coi_state_bits",
                                                 "counterexample_units")} for r in result["history"]],
    }


def run(job, cpus, args, lock):
    name, spec = job["name"], job["spec"]
    workdir = os.path.join(args.workdir, name)
    os.makedirs(workdir, exist_ok=True)
    with open(os.path.join(workdir, "spec.json"), "w") as f:
        json.dump(spec, f)
    env = dict(os.environ, RIC3_TMP_DIR=os.path.join(args.workdir, ".ric3tmp", name))
    os.makedirs(env["RIC3_TMP_DIR"], exist_ok=True)
    with open(os.path.join(workdir, "out.log"), "w") as log:
        code = subprocess.call(["taskset", "-c", cpus, sys.executable, os.path.join(SCRIPT_DIR, "fine_choice.py"),
                                "cegar", "--wrapper", args.wrapper, "--units", args.units,
                                "--spec", os.path.join(workdir, "spec.json"), "--workdir", workdir,
                                "--time-limit", str(args.time_limit), "--max-iterations", str(args.max_iterations)],
                               stdout=log, stderr=subprocess.STDOUT, env=env)
    record = summary(name, workdir) if code == 0 else {"name": name, "status": "ERROR", "exit": code}
    with lock:
        with open(os.path.join(args.workdir, "results.jsonl"), "a") as f:
            f.write(json.dumps(record) + "\n")
        print(json.dumps({k: record.get(k) for k in ("name", "status", "refinements", "total_seconds")}), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wrapper", required=True)
    parser.add_argument("--units", required=True)
    parser.add_argument("--specs", required=True, help="JSONL of {name, spec}")
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--cpus", required=True, help="CPU groups for taskset, separated by '/', e.g. 24-25/26-27")
    parser.add_argument("--time-limit", type=int, required=True)
    parser.add_argument("--max-iterations", type=int, required=True)
    args = parser.parse_args(argv)
    args.workdir = os.path.abspath(args.workdir)
    args.wrapper = os.path.abspath(args.wrapper)
    args.units = os.path.abspath(args.units)
    os.makedirs(args.workdir, exist_ok=True)
    done = set()
    results = os.path.join(args.workdir, "results.jsonl")
    if os.path.exists(results):
        with open(results) as f:
            done = {json.loads(line)["name"] for line in f if line.strip()}
    jobs = queue.Queue()
    with open(args.specs) as f:
        for line in f:
            if line.strip() and json.loads(line)["name"] not in done:
                jobs.put(json.loads(line))
    lock = threading.Lock()

    def worker(cpus):
        while True:
            try:
                job = jobs.get_nowait()
            except queue.Empty:
                return
            run(job, cpus, args, lock)

    threads = [threading.Thread(target=worker, args=(cpus,)) for cpus in args.cpus.split("/")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return 0


if __name__ == "__main__":
    sys.exit(main())
