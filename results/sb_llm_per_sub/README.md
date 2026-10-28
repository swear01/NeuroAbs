# SB 上讓 LLM 逐題挑抽象（rIC3）

2026-10-28 的狀態：Piccolo SB `store_en` 的關鍵是把 store 位址加法器 `alu_outputs___1_addr__h5583`（而不是 load 位址的 `eaddr__h5553`）跟 ILA 的位址加法 `n110` 配成 UF（[`semantic_candidates`](../semantic_candidates/README.md)）。本實驗讓 LLM 對每個 sub-property 各作答一次（實驗 B 的 prompt，`src/fine_choice_llm.py`），問兩件事：挑不挑得對，以及挑對之後證不證得出來。預先登記見 [`PREREG.md`](PREREG.md)，第 7 節是加上單選重問和順序對照的修正。

結論（store_en 10 題，mazu，每格是 `UNSAT` / 10）：

| Arm | 選單順序：原順序（`h5583` 排第一） | 反順序（`eaddr` 排第一） |
| --- | --- | --- |
| Claude Opus 逐題，實驗 B 的 prompt（多選） | 1（9 題 ERROR） | — |
| DeepSeek 逐題，實驗 B 的 prompt（多選） | 0（8 題 ERROR，2 題 max_iterations） | — |
| **Claude Opus 逐題，單選 prompt** | **9** | **9** |
| DeepSeek 逐題，單選 prompt | 4 | 4 |
| S（`fine_choice.structural`） | 1 | 1（順序不影響 S） |
| Claude 規則 fb2（留出題實驗挑出的規則） | 10 | 1 |

- 單選 prompt 下，Claude Opus 在兩種順序都有 9/10 題挑 `h5583`（原順序 8 題、反順序 9 題），並且 9/10 題證得出來。**每一次挑 `h5583`，結果都是 0 次 refinement 的 `UNSAT`**（兩個模型合計 23 次，每題 29–287 s）。
- 留出題實驗裡 fb2 的 10/10，來自選單的順序。fb2 給 `h5583` 和 `eaddr` 相同分數（`op_score` +5），平手時取選單上排前面的那個。順序反過來後，它在 9 題改挑 `eaddr`，而這 9 題的 spec 和 S **完全相同**（同一個 `batch.py` key），所以結果也和 S 一樣是 TIMEOUT。
- 實驗 B 的 prompt 沒有說每個 ILA 運算子只能配一個 RTL 運算子，兩個模型常把三個候選全部設成 `uf`。`fine_choice.uf_rewrite` 處理同一個 ILA 節點的第二個 pair 時，會丟 `ValueError: n110 is not a binary operator on two signals`，所以那些是 ERROR，不是證不出來。依 PREREG 不修補答案，`fine_choice.py` 也不改：改成接受一對多，等於改變選單的語意。

## 題目與設定

- 題目、units、具名 wrapper、20 個抽樣 sub-property 都與 [`llm_rule_heldout`](../llm_rule_heldout/PREREG.md) 相同（`problems/SB/`，wrapper sha256 `70c79dfa…1013`）。主要題目是 `store_en` 10 題；`pc` 10 題只跑了第一輪（多選）。
- 選單：3 個 unit（keep／cut）、`gpr0`..`gpr31`（keep／word／havoc），以及 `candidates.json` 的全部 3 個運算子候選：`h5583`、`eaddr`、`rd_val___1__h6550`，三個都配 ILA `n110`。prompt 不提示哪個是對的。
- rIC3：mazu，CPU 組 `12,13/14,15`（P-core，各是一個實體核心的兩個 hyper-thread），同時 2 個 run。開跑前確認沒有其他程序綁在 12–15。`src/fine_batch.py` CEGAR，每個模型 300 s，最多 10 次 refinement；rIC3 master `8c6df1b`（binary sha256 與 zeus 相同）。同一 sub-property 上 abstraction 相同的 spec 只跑一次，各 arm 共用結果。
- S 和 fb2 用留出題實驗在 zeus 上產生的 spec（`data/zeus/`）。反順序的 spec 由 `scripts/order.py` 產生（`data/order/`）。

## LLM 的選擇

### 第一輪：實驗 B 的 prompt（每個模型 20 次呼叫）

store_en 10 題的 UF 選擇（`data/choices.json`）：

| | 只有 `h5583` | `h5583` 加其他 | `eaddr`+`rd_val` | 只有 `rd_val` | 沒有 UF |
| --- | --- | --- | --- | --- | --- |
| Claude Opus | 1 | 9（三個全選） | 0 | 0 | 0 |
| DeepSeek | 0 | 7（3 題 +`rd_val`，4 題三個全選） | 1 | 2 | 0 |

- GPR：兩個模型 10/10 題都和 S 相同（keep rs1、rs2，其餘 havoc）。unit：DeepSeek 有 9/10 題和 S 相同（全部 cut）；Claude 只有 1/10，其餘大多保留 `csr_regfile`。
- pc 10 題：Claude 10 題三個全選，DeepSeek 8 題三個全選、2 題只有 `rd_val`。
- Claude 的機率輸出裡，`h5583` 在 8/10 題是三個候選中 `uf` 機率最低的（0.6–0.7，另外兩個是 0.75–0.9）。第一輪的 Claude 並沒有把 `h5583` 認成唯一的正確答案。

### 第二輪：單選 prompt，兩種順序（每個模型 20 次呼叫）

system prompt 只多加一句：每個 ILA 運算子最多配一個 RTL 運算子，也可以都不配。40 個回答都是合法的單選，沒有一題多選（`data/single.json`）：

| | `h5583` | `eaddr` | `rd_val` | 不配 |
| --- | --- | --- | --- | --- |
| Claude 原順序 | 8 | 2（rs1=0.rs2=0、rs1=29.rs2=3） | 0 | 0 |
| Claude 反順序 | 9 | 0 | 0 | 1（rs1=15.rs2=12） |
| DeepSeek 原順序 | 3 | 4 | 1 | 2 |
| DeepSeek 反順序 | 3 | 4 | 0 | 3 |

同一題在兩種順序下選一樣的：Claude 7/10，DeepSeek 3/10（rs1=1.rs2=28、rs1=15.rs2=11 都是 `h5583`，rs1=19.rs2=29 都是 `eaddr`）。

## rIC3 結果（mazu，store_en）

`data/runs/summary-store_en.jsonl` 是每個 arm、每題最後一筆紀錄；`data/runs/store_en/results.jsonl` 是全部紀錄（ERROR 的 run 每次開新 batch 都會由 `fine_batch` 重跑，每次都是同一個 `ValueError`）。

| Arm | `UNSAT` | 其他 | refinement 總數 | 最終 COI bits 總和（`UNSAT` 的） | 時間總和 |
| --- | --- | --- | --- | --- | --- |
| Claude 多選 | 1 | ERROR 9 | 0 | 1,627（1,627） | 117 s |
| DeepSeek 多選 | 0 | ERROR 8、max_iterations 2 | 20 | 6,316（0） | 1,126 s |
| Claude 單選，原順序 | 9 | TIMEOUT 1 | 14 | 17,458（14,687） | 2,027 s |
| Claude 單選，反順序 | 9 | TIMEOUT 1 | 0 | 16,120（14,244） | 1,195 s |
| DeepSeek 單選，原順序 | 4 | TIMEOUT 5、max_iterations 1 | 36 | 18,925（6,363） | 3,853 s |
| DeepSeek 單選，反順序 | 4 | TIMEOUT 6 | 24 | 16,361（3,989） | 3,083 s |
| S | 1 | TIMEOUT 9 | 62 | 24,734（2,350） | 5,532 s |
| fb2 | 10 | — | 0 | 10,327（10,327） | 758 s |
| fb2，反順序 | 1 | TIMEOUT 9 | 56 | 23,139（755） | 5,062 s |

每題依選擇分類：

- 挑 `h5583`（單選或第一輪只選它）：Claude 18 次、DeepSeek 6 次，全部 `UNSAT`、0 次 refinement，每題 29–287 s，最終 COI 1,045–2,004 bits。DeepSeek 的 rs1=1.rs2=28 用了 287 s，因為它保留的 unit 不同（1,890 bits）。
- 挑 `eaddr`：rs1=0.rs2=0 是 `UNSAT`（6 次 refinement，2,350 bits；兩個運算元都是 x0，S 在這題也證得出來）。其餘都在 4–9 次 refinement 後 TIMEOUT，和 S 相同（多數 spec 就是 S 的 spec）。
- 不配 UF：rs1=0.rs2=0 是 `UNSAT`（0 次 refinement、755 bits，與 fb2 的 spec 相同）。其餘 TIMEOUT，0 次 refinement：沒有反例可以拿來 refine。
- `rd_val`：max_iterations（10 次 refinement，3,158 bits）。

pc 10 題（第一輪 spec，以及 S、fb2）：S 10/10（各 1 次 refinement）、fb2 10/10（0 次）、DeepSeek 多選 2/10（只有 `rd_val` 的 2 題 `UNSAT`，其餘 8 題 ERROR）、Claude 多選 0/10（10 題 ERROR）。第二輪只問 store_en，所以 pc 沒有新的 spec 要跑。fb2 反順序在 pc 上改挑 `eaddr`，這組沒有跑。

### 與 zeus 的對照

只在 mazu 這幾個 arm 之間比較，不比較 zeus 的時間。留出題實驗在 zeus 上的 store_en `UNSAT` 數：S 1/10、fb2 10/10，mazu 相同。S 每題的狀態也相同；只有 rs1=19.rs2=29 的 refinement 次數不同（zeus 7 次，mazu 8 次），兩邊都是 TIMEOUT。

## 花費與 LLM 呼叫

- DeepSeek：60 次呼叫（20 次多選，加上兩種順序各 20 次單選），US$0.61（上限 $1）。全部由 `deepseek-v4.1-flash`（OpenCode Go）服務，沒有 `provider` 欄位。
- Claude：60 次 `claude -p --model opus`，用個人 claude.ai 帳號。stream-json 的 init 事件全部是 `apiKeySource: none`、`claude-opus-5-5`，沒有工具，也沒有 MCP。`total_cost_usd` 標價合計 US$3.60，只是標價，沒有實際的 API 花費。沒有讀取或使用任何 API key。
- 回答、完整的 stream-json 紀錄和 DeepSeek 的請求／回應都在 `data/<arm>/`。

## 限制

- 每個模型、每題、每種順序只問一次，沒有重複抽樣，看不出 Claude 9/10 的變異範圍。
- 單選 prompt 是在看過第一輪結果之後加的（PREREG 第 7 節），不是原本預先登記的實驗。不過它只多一句「最多配一個」，沒有提示是哪一個。
- 實驗 B 的 case 說明寫「imm is inst[31:20]」（I-type 的 imm），`eaddr` 的運算元名字又含 `BITS_31_TO_20`。這可能把模型引向 `eaddr`，本實驗沒有修改。
- mazu 每個 run 只有一個實體核心（2 個 hyper-thread），zeus 是兩個實體核心加上它們的 hyper-thread。時間只描述，不做加速結論，也沒有重複計時。
- 只有 SB 一個指令；SH 是同一題型，但沒有測。
- 第一次在 mazu 跑 S 時，chain 順序錯了，先跑了 S。那批 run 在跑完前被我停掉，結果全部刪除後依正確順序重跑；表裡沒有那批的數字。

## 重現

```
results/sb_llm_per_sub/scripts/ask.py <deepseek|claude> <heldout run dir> <out> [--single] [--reverse]
results/sb_llm_per_sub/scripts/order.py <heldout run dir> <S|rule.py> <out.jsonl>
results/sb_llm_per_sub/scripts/run.sh <store_en|pc> <arm>...
results/sb_llm_per_sub/scripts/choices.py <run dir> <out.json>
results/sb_llm_per_sub/scripts/single.py <run dir> <out.json>
results/sb_llm_per_sub/scripts/summarize.py <run dir> <state> <out.jsonl>
```

run dir：mazu `/var/tmp/neuroabs-runtime/runs/sb-llm-per-sub-20261028`（模型、witness 與 rIC3 log 留在本機，不 commit）。
