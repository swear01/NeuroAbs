# 預先登記：SB 上讓 LLM 逐題挑抽象（實驗 B 的 prompt）

登記日期 2026-10-28。本檔在**任何 LLM 呼叫之前** commit 並 push。登記後內容不改；若必須改，在文末另開「變更」一節，寫明原因與時間，舊文字保留。

問題：在 Piccolo SB 上，讓 LLM 對每個 sub-property 各挑一次抽象（實驗 B 的做法，`src/fine_choice_llm.py`），它會不會在 `store_en` 上把 UF 配到 store 位址加法器 `alu_outputs___1_addr__h5583`（正確，見 [`semantic_candidates`](../semantic_candidates/README.md)），而不是 load 位址的 `eaddr__h5553`？配了之後 rIC3 證得出幾題？

背景：留出題實驗（[`llm_rule_heldout`](../llm_rule_heldout/PREREG.md)，zeus）在 SB `store_en` 10 題上：split 0、S 1、auto 1、DeepSeek 規則 fb4 1、Claude 規則 fb2 10。那些是 LLM 寫的「規則」；本實驗是 LLM 直接逐題作答。

## 1. 題目

- 指令 SB，題目與 `llm_rule_heldout` 完全相同：`results/llm_rule_heldout/problems/SB/` 的 20 個抽樣 sub-property（`subs-sample.json`：`pc` 10 題、`store_en` 10 題）、units（`units.json`）、具名 wrapper（`/var/tmp/neuroabs-runtime/runs/llm-heldout-20261027/problems/SB/wrapper.v`，sha256 `70c79dfa86f1d8ee68bf4addb650d866dde7bc312fd1e48cbea1d6a248e41013`，與 `wrapper.v.sha256` 相同）。
- 主要題目是 `store_en` 10 題：`store_en.rs1=0.rs2=0`、`rs1=1.rs2=28`、`rs1=1.rs2=30`、`rs1=2.rs2=2`、`rs1=15.rs2=11`、`rs1=15.rs2=12`、`rs1=17.rs2=26`、`rs1=19.rs2=29`、`rs1=29.rs2=3`、`rs1=30.rs2=0`。

## 2. Prompt

- 原樣沿用實驗 B：system 是 `src/fine_choice_context.txt`，user 是 `fine_choice_llm.build_message`（property 描述 `Piccolo_verification_done/SB/description.txt`、選單、sub-property 的 Verilog conjunct、case）。程式不改。
- 選單（`fine_choice_llm.menu`）：`csr_regfile`、`near_mem_dcache`、`near_mem_icache`（keep／cut），`gpr0`..`gpr31`（keep／word／havoc），以及 `candidates.json` 的**全部** 3 個運算子候選，依檔案順序：
  - `uf0`：ILA `n110 = n105 + n109`；RTL `alu_outputs___1_addr__h5583 = rs1_val_bypassed__h3337 + alu_outputs___1_addr__h5583__rhs`
  - `uf1`：ILA 同上；RTL `eaddr__h5553 = rs1_val_bypassed__h3337 + SEXT_near_mem_imem_instr__59_BITS_31_TO_20_02___d303`
  - `uf2`：ILA 同上；RTL `rd_val___1__h6550 = rs1_val_bypassed__h3337 + _theResult___snd__h7382`
- prompt 不提示哪個候選是對的，不含 S、`semantic_candidates` 或留出題規則的任何內容。
- 已知、照原樣保留的事實：實驗 B 的 case 說明寫「imm is inst[31:20]」（I-type 的 imm），而 `uf1` 的運算元名字含 `BITS_31_TO_20`，`uf0` 的運算元是不透明的 `__rhs`。這可能把模型引向 `eaddr`；不修改，結果照實報告。
- 「同一節點最多一個 `uf`」：實驗 B 的 `parse_choices` 不檢查這一點。若模型同時選了多個 `uf`，照原樣全部加入 spec（`to_spec`），並在統計中另列。
- 無效的答案：`decide` 原樣處理（該 choice 留在 keep），錯誤訊息照實記錄、另列。

## 3. 模型與呼叫

每個模型對 20 個 sub-property 各呼叫 1 次（`store_en` 先），共 40 次。驅動程式 `scripts/ask.py`（只呼叫 `fine_choice_llm.decide`）。

- DeepSeek：本機閘道 `deepseek-flash`，reasoning effort `low`（`src/deepseek_chat.py`，同實驗 B）。`LLM_BUDGET_USD=1`，花費上限 US$1。只接受 OpenCode Go／Command Code 服務的回應（`llm_rule.DEEPSEEK_DIRECT`、無 `provider` 欄位），否則立即停止。
- Claude Opus：`src/claude_cli.py` 的乾淨 `claude -p --model opus`，個人 claude.ai 帳號，每次一個新的空目錄、新的 session。init 事件的 `apiKeySource` 必須是 `none`，否則停止。**不使用任何 API key**；個人帳號額度不足、無法用 opus 或被限流就停止回報，不改用其他途徑。完整 stream-json 紀錄保留。
- 金鑰不印出、不放進 CLI 參數、log、commit 或 artifact。

## 4. Arm 與 rIC3

在 mazu 跑（P-core CPU 12–15；CPU 0–11 給留出題 session，16–31 不用）。CPU 組 `12,13/14,15`（各為一個實體核心的兩個 hyper-thread），同時 2 個 run。開跑前確認沒有其他程序綁在 12–15。

- 工具：`/var/tmp/neuroabs-runtime/env-20261024.sh`，rIC3 master `8c6df1b`（sha256 `90e7141bc92521fdc4cdbbf4310b1d953eee4aec4007c6ddb4fd1625ee696977`，與 zeus 相同）。
- 每個 run：`src/fine_batch.py` CEGAR，每個模型 300 s，最多 10 次 refinement，與留出題相同。同一 sub-property 上 abstraction 相同的 spec 只跑一次（`llm_rule_heldout/scripts/batch.py` 的 key），各 arm 共用。
- `store_en` 10 題上的 arm，依此順序執行：
  1. DeepSeek 逐題（本實驗的 spec）
  2. Claude 逐題（本實驗的 spec）
  3. S（留出題在 zeus 產生的 `specs/SB/S.jsonl`）
  4. Claude 規則 fb2（留出題在 zeus 產生的 `specs/SB/claude-fb2.jsonl`）
- 時間允許時，最後再跑 `pc` 10 題的同樣 4 個 arm。

## 5. 指標與比較

先報告（rIC3 之前）：每個模型在 `store_en` 10 題上，UF 設成 `uf0`（`h5583`，正確）、`uf1`（`eaddr`）、`uf2`、多個、或沒有 UF 的題數；GPR 與 unit 的選擇是否與 S 相同（S 的 GPR：keep 該題的 rs1、rs2，其餘 havoc；unit 全 cut）。

rIC3 之後，每個 arm 在 `store_en`（與 `pc`，若有跑）上：

1. `UNSAT` 數 / 10；
2. refinement 總次數；
3. 最終 COI state bits（總和，以及只算 `UNSAT` 的總和）；
4. 單次時間（只描述，不做加速結論）。

只在 mazu 這 4 個 arm 之間比較；不與 zeus 的時間比較。zeus 的 `UNSAT` 數只作為對照列出，若某 arm 在 mazu 與 zeus 的 `UNSAT` 數不同，照實報告。「逐題 LLM 贏過某 arm」= `UNSAT` 數較多。

## 6. 不做的事

不修補 LLM 答案；不改 `fine_choice`、`fine_choice_llm`、rIC3 或 IC3 內部；不用 AVR；不動留出題 session 的檔案與程序。

## 7. 變更

### 2026-10-28：順序對照與單選重問（呼叫 LLM 之前寫入）

第 1–6 節的結果照實保留。新增的原因：

- 逐題作答的 spec 大多是 ERROR，不是證不出來。兩個模型常對同一個 ILA 節點 `n110` 勾了多個 RTL 加法器，`fine_choice.uf_rewrite` 處理第二個 pair 時丟 `ValueError: n110 is not a binary operator on two signals`。實驗 B 的 prompt 沒說只能選一個。
- Claude 規則 fb2 的 `op_score` 給 `h5583` 和 `eaddr` 的分數都是 +5，平手時看選單順序，而 `candidates.json` 把 `h5583` 排在第一個。

`fine_choice.py` 不改；讓它接受一對多，等於改變選單的語意。

1. 順序對照（不呼叫 LLM）：`scripts/order.py` 把 SB 的候選順序反過來（`eaddr` 變第一個、`h5583` 變最後一個），用 `llm_rule_heldout/scripts/specs.py` 重新套用 fb2 和 S。若 fb2 改挑 `eaddr`，就在 mazu CPU 12–15 跑 store_en 10 題，設定同第 4 節。spec 與已經跑過的相同時（`batch.py` 的 key），沿用已有的結果。
2. 單選重問：`scripts/ask.py --single`。system prompt 在實驗 B 的 `fine_choice_context.txt` 後面加一句：「Each ILA operator is paired with at most one RTL operator: among the operator choices that share the same ILA operator, at most one may be "uf"; it is also allowed that none is.」其他文字不變，同樣不提示哪個是對的。只問 store_en 10 題，每題用兩種候選順序各問一次：原順序，以及反順序（`--reverse`，選單 id 依新順序重新編號）。Claude（個人帳號 `claude -p`，`apiKeySource` 必須是 none）和 DeepSeek 各問 20 次，共 40 次。DeepSeek 在 SB 的總花費上限仍是 US$1（含第 3 節已花的部分）。
   - 若回答仍對同一個 ILA 節點勾了多個 `uf`，記為「多選（不合法）」，不修補、不跑 rIC3，算未證出。
3. 單選回答的 rIC3：mazu CPU 12–15，store_en，設定同第 4 節（300 s、最多 10 次 refinement）。pc 只跑 spec 和先前不同的。
4. 報告：每題、每種順序挑了 `h5583`／`eaddr`／`rd_val`／不配／多選；各 arm 在 store_en 上的 `UNSAT` 數 / 10。
