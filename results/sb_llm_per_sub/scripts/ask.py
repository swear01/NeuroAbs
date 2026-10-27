"""ask.py <deepseek|claude> <run dir> <out dir>: one call per sampled SB sub-property with the prompt of experiment B,
the store_en sub-properties first.

The message is fine_choice_llm.build_message on the named SB wrapper of llm_rule_heldout, with every operator pair of
problems/SB/candidates.json in the menu; the system prompt is src/fine_choice_context.txt.  The answer goes through
fine_choice_llm.decide unchanged (a choice with an invalid answer stays at keep).  DeepSeek must be served by
OpenCode Go or Command Code (llm_rule.DEEPSEEK_DIRECT, no provider field); Claude is the clean claude -p of
claude_cli in a new empty directory per call, and its init event must report apiKeySource none.  With --single the
system prompt also says that an ILA operator gets at most one RTL operator, only the store_en sub-properties are
asked, and an answer that still pairs one ILA operator with several RTL operators is recorded with single_errors and
gets no spec (not repaired).  --reverse offers the operator candidates in reverse order.  Writes
<out dir>/decisions.jsonl (resumable) and <out dir>/specs.jsonl in the format of llm_rule_heldout/scripts/batch.py.
"""
import argparse
import json
import os
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "src"))
sys.path.insert(0, os.path.join(REPO, "results", "llm_rule_heldout", "scripts"))
import fine_choice_llm  # noqa: E402
import llm_rule  # noqa: E402
import specs  # noqa: E402

CASE = "SB"
SINGLE = ("\n\nEach ILA operator is paired with at most one RTL operator: among the operator choices that share the "
          "same ILA operator, at most one may be \"uf\"; it is also allowed that none is.")


def deepseek_call():
    import deepseek_chat

    def call(system, message, request_id):
        response, elapsed = deepseek_chat.call_deepseek(system, message, request_id)
        if response.get("model") not in llm_rule.DEEPSEEK_DIRECT or "provider" in response:
            raise RuntimeError("DeepSeek request {:d} was not served by OpenCode Go or Command Code: model {!r}"
                               .format(request_id, response.get("model")))
        response["spent_usd_process"] = deepseek_chat.spent_usd
        return response, elapsed
    return call, deepseek_chat.chat_text


def claude_call(out):
    import time
    import claude_cli

    def call(system, message, request_id):
        started = time.time()
        reply = claude_cli.call_claude(system, message, os.path.join(out, "claude-cwd", "request-{:d}".format(request_id)),
                                       str(uuid.uuid4()), os.path.join(out, "claude-{:d}.jsonl".format(request_id)))
        init = reply["init"]
        if init.get("apiKeySource") != "none":
            raise RuntimeError("claude request {:d} has apiKeySource {!r}".format(request_id, init.get("apiKeySource")))
        result = reply["result"]
        return {"model": reply["models"], "usage": result.get("usage"), "model_usage": result.get("modelUsage"),
                "list_cost_usd": result.get("total_cost_usd"), "text": reply["answer"],
                "init": {k: init.get(k) for k in ("model", "tools", "mcp_servers", "apiKeySource",
                                                  "claude_code_version")}}, time.time() - started
    return call, lambda response: response["text"]


def single_errors(assignment, ufs):
    """The ILA operators that the answer pairs with more than one RTL operator."""
    chosen = {}
    for i, uf in enumerate(ufs):
        if assignment.get("uf{:d}".format(i)) == "uf":
            chosen.setdefault(uf["ila"], []).append(uf["rtl"])
    return {ila: rtls for ila, rtls in chosen.items() if len(rtls) > 1}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backend", choices=["deepseek", "claude"])
    parser.add_argument("run")
    parser.add_argument("out")
    parser.add_argument("--single", action="store_true", help="state in the prompt that an ILA operator gets at most "
                        "one RTL operator; ask only the store_en sub-properties")
    parser.add_argument("--reverse", action="store_true", help="offer the operator candidates in reverse order")
    args = parser.parse_args()
    backend, run, out = args.backend, os.path.abspath(args.run), os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    wrapper = os.path.join(run, "problems", CASE, "wrapper.v")
    with open(wrapper) as f:
        text = f.read()
    candidates = specs.load(CASE, "candidates.json")
    ufs = fine_choice_llm.uf_details(text, candidates[::-1] if args.reverse else candidates)
    units = specs.load(CASE, "units.json")
    subs = specs.load(CASE, "subs-sample.json")
    if args.single:
        subs = [sub for sub in subs if sub["name"].startswith("store_en.")]
        fine_choice_llm.fine_choice_context += SINGLE
    with open(os.path.join(REPO, "Piccolo_verification_done", CASE, "description.txt")) as f:
        description = f.read()
    choices = fine_choice_llm.menu(units, ufs)
    os.makedirs(os.path.join(out, "hier"), exist_ok=True)
    ports = fine_choice_llm.unit_ports([c for c in choices if "path" in c], wrapper, os.path.join(out, "hier"))
    call, extract = deepseek_call() if backend == "deepseek" else claude_call(out)
    os.chdir(out)
    path = os.path.join(out, "decisions.jsonl")
    done = {}
    if os.path.exists(path):
        with open(path) as f:
            done = {r["name"]: r for r in map(json.loads, filter(str.strip, f))}
    order = sorted(range(len(subs)), key=lambda i: not subs[i]["name"].startswith("store_en."))
    for i in order:
        sub = subs[i]
        if sub["name"] in done:
            continue
        result = fine_choice_llm.decide(sub, choices, ports, description, text, ufs, call, extract, i + 1)
        if args.single:
            result["single_errors"] = single_errors(result["assignment"], ufs)
        with open(path, "a") as f:
            f.write(json.dumps(result) + "\n")
        done[sub["name"]] = result
        print(json.dumps({"name": sub["name"], "uf": result["spec"]["uf"], "errors": result["errors"]}), flush=True)
    with open(os.path.join(out, "specs.jsonl"), "w") as f:
        for sub in subs:
            if not done[sub["name"]].get("single_errors"):
                f.write(json.dumps({"name": sub["name"], "spec": done[sub["name"]]["spec"]}) + "\n")


if __name__ == "__main__":
    main()
