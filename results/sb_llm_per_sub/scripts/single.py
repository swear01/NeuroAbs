"""single.py <run dir> <out.json>: the operator pairing of every single-choice answer (ask.py --single) per model,
candidate order and store_en sub-property: h5583, eaddr, rd_val, none or multiple (invalid)."""
import json
import os
import sys

LABEL = {"alu_outputs___1_addr__h5583": "h5583", "eaddr__h5553": "eaddr", "rd_val___1__h6550": "rd_val"}


def main():
    run, out = sys.argv[1:3]
    table = {}
    for model in ("deepseek", "claude"):
        for order, suffix in (("original", ""), ("reverse", "-rev")):
            with open(os.path.join(run, "{:s}-single{:s}".format(model, suffix), "decisions.jsonl")) as f:
                rows = {r["name"]: r for r in map(json.loads, filter(str.strip, f))}
            table["{:s}/{:s}".format(model, order)] = {
                name: "multiple:" + "+".join(LABEL[u["rtl"]] for u in r["spec"]["uf"]) if r["single_errors"]
                else (LABEL[r["spec"]["uf"][0]["rtl"]] if r["spec"]["uf"] else "none")
                for name, r in sorted(rows.items())}
    with open(out, "w") as f:
        json.dump(table, f, indent=1)
    for key, rows in table.items():
        counts = {}
        for v in rows.values():
            k = "multiple" if v.startswith("multiple") else v
            counts[k] = counts.get(k, 0) + 1
        print(key, len(rows), json.dumps(counts))


if __name__ == "__main__":
    main()
