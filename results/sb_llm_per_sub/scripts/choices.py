"""choices.py <run dir> <out.json>: the UF pairing, GPR and unit choices of each model on each SB sub-property, against S.

S is the spec of llm_rule_heldout on zeus (<run dir>/zeus-specs/S.jsonl).  A GPR is keep, word or havoc (not in
keep_gprs or word_gprs); the comparison uses the full 32-entry level list.
"""
import json
import os
import sys

NUM_GPRS = 32
LABEL = {"alu_outputs___1_addr__h5583": "h5583", "eaddr__h5553": "eaddr", "rd_val___1__h6550": "rd_val"}


def read(path):
    with open(path) as f:
        return {r["name"]: r for r in map(json.loads, filter(str.strip, f))}


def gprs(spec):
    keep = set(range(NUM_GPRS)) if spec.get("keep_gprs", "all") == "all" else set(spec["keep_gprs"])
    word = set(spec.get("word_gprs", []))
    return ["keep" if j in keep else "word" if j in word else "havoc" for j in range(NUM_GPRS)]


def units(spec):
    return {k: v for k, v in sorted(spec.get("units", {}).items()) if v != "keep"}


def main():
    run, out = sys.argv[1:3]
    s = {k: v["spec"] for k, v in read(os.path.join(run, "zeus-specs", "S.jsonl")).items()}
    table = {}
    for model in ("deepseek", "claude"):
        decisions = read(os.path.join(run, model, "decisions.jsonl"))
        rows = {}
        for name, d in decisions.items():
            spec = d["spec"]
            ufs = [LABEL[u["rtl"]] for u in spec["uf"]]
            g, sg = gprs(spec), gprs(s[name])
            rows[name] = {"uf": "+".join(ufs) if ufs else "none", "gpr_same_as_S": g == sg,
                          "gpr_keep": [j for j in range(NUM_GPRS) if g[j] == "keep"],
                          "gpr_word": [j for j in range(NUM_GPRS) if g[j] == "word"],
                          "units": units(spec), "units_same_as_S": units(spec) == units(s[name]),
                          "parse_errors": d["errors"]}
        table[model] = rows
    with open(out, "w") as f:
        json.dump(table, f, indent=1)
    for model, rows in table.items():
        for state in ("store_en", "pc"):
            sel = {k: v for k, v in rows.items() if k.startswith(state + ".")}
            if not sel:
                continue
            counts = {}
            for v in sel.values():
                counts[v["uf"]] = counts.get(v["uf"], 0) + 1
            print(json.dumps({"model": model, "state": state, "n": len(sel), "uf": counts,
                              "gpr_same_as_S": sum(v["gpr_same_as_S"] for v in sel.values()),
                              "units_same_as_S": sum(v["units_same_as_S"] for v in sel.values()),
                              "with_parse_errors": sum(bool(v["parse_errors"]) for v in sel.values())}))


if __name__ == "__main__":
    main()
