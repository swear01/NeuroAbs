"""table.py <summary.json> <training all.json>: the Markdown tables of the README (training, test per case, totals)."""
import json
import sys

ARMS = ["split", "auto", "S", "deepseek-fb4", "claude-fb2"]
LABEL = {"split": "split (COI)", "auto": "auto", "S": "S", "deepseek-fb4": "DeepSeek fb4", "claude-fb2": "Claude fb2"}
CASE = {"ADD_Flatten": "ADD", "BNE_new": "BNE"}


def status_text(status):
    return "、".join("{:s} {:d}".format(k, v) for k, v in sorted(status.items(), key=lambda x: (-x[1], x[0])))


def main():
    with open(sys.argv[1]) as f:
        summary = json.load(f)
    with open(sys.argv[2]) as f:
        training = json.load(f)
    print("### 訓練（ADDI 16 個 sub-property）\n")
    print("| 名次 | 規則 | UNSAT | rejected | 最終 COI bits | 時間 s | refinement | 狀態 |")
    print("| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |")
    for i, arm in enumerate(training["ranking"], 1):
        t = training["arms"][arm]
        status = {}
        for r in t["subs"]:
            status[r["status"]] = status.get(r["status"], 0) + 1
        print("| {:d} | `{:s}` | {:d} | {:d} | {:,d} | {:,.0f} | {:d} | {:s} |".format(
            i, arm, t["unsat"], t["rejected"], t["final_coi_state_bits"], t["seconds"], t["refinements"],
            status_text(status)))
    print("\n### 測試：每個指令 20 個 sub-property\n")
    print("每格：UNSAT 數／refinement 次數／最終 COI bits 總和（千）。\n")
    print("| 指令 | " + " | ".join(LABEL[a] for a in ARMS) + " |")
    print("| --- | " + " | ".join("---" for _ in ARMS) + " |")
    totals = {a: {"unsat": 0, "refinements": 0, "coi_bits": 0, "coi_bits_unsat": 0, "seconds": 0, "n": 0} for a in ARMS}
    for case, arms in summary.items():
        cells = []
        for a in ARMS:
            v = arms[a]
            cells.append("{:d}／{:d}／{:.1f}".format(v["unsat"], v["refinements"], v["coi_bits"] / 1000))
            for k in totals[a]:
                totals[a][k] += v[k]
        print("| {:s} | {:s} |".format(CASE.get(case, case), " | ".join(cells)))
    print("\n### 合計（{:d} 個指令）\n".format(len(summary)))
    print("| Arm | UNSAT | refinement | 最終 COI bits | 只算 UNSAT 的 COI bits | 時間 s（單次，不做速度結論） |")
    print("| --- | ---: | ---: | ---: | ---: | ---: |")
    for a in ARMS:
        t = totals[a]
        print("| {:s} | {:d} / {:d} | {:,d} | {:,d} | {:,d} | {:,d} |".format(
            LABEL[a], t["unsat"], t["n"], t["refinements"], t["coi_bits"], t["coi_bits_unsat"], t["seconds"]))
    print("\n### 未證出的 sub-property\n")
    for case, arms in summary.items():
        for a in ARMS:
            if arms[a]["unproved"]:
                print("- {:s} {:s}：{:s}".format(CASE.get(case, case), LABEL[a], "、".join(
                    "`{:s}` {:s}".format(s, st) for s, st in arms[a]["unproved"].items())))


if __name__ == "__main__":
    main()
