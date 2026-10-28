# 預先登記：留出指令上的 LLM 選擇規則比較

登記日期 2026-10-27。本檔在**任何 LLM 呼叫之前** commit。登記之後內容不得更改；若必須更改，在文末另開「變更」一節，寫明原因與時間，舊文字保留。

問題：在 Piccolo 的 13 個留出指令上，LLM（DeepSeek、Claude）寫的抽象選擇規則，與非 LLM 的做法比起來，能證出幾題、需要幾次 refinement、最終模型多大。規則只用 ADDI 的抽樣挑選，挑選過程不看 S。

S（`fine_choice.structural`）是在讀過 DeepSeek 的 ADDI 答案之後才寫的，所以不是獨立的尺。**本輪不以「與 S 一致」評分**；S 只是其中一個 arm。

## 1. 題目

- 指令來自 `Piccolo_verification_done/`。repo 裡沒有 ORI、XORI、BLT、SW，用 OR、XOR、BNE（`BNE_new`）、SH 代替，不生成新的 ILA 題目。LB 的 property 本身不成立（`semantic_candidates`），排除。
- 訓練：ADDI。測試：`ADD_Flatten`（ADD）、SUB、OR、XOR、ANDI、SLTI、LUI、AUIPC、JAL、BEQ、`BNE_new`（BNE）、SB、SH。
- 每個指令的輸入由 `scripts/prepare.py` 產生，存在 `problems/<case>/`。14 個指令都成功，`problems/failed.json` 是空的。

### 1.1 Wrapper：運算元命名

`prepare.name_operands` 對每個 wrapper 做同一個改寫：RTL 中若有 `assign n = rs1_val* op {...};` 或 `rs2_val* op {...}`（另一個運算元是 concat），就把 concat 宣告成 wire `n__rhs`。模型行為不變，只是讓這個節點能被 `fine_choice.operator_args` 解析、成為 UF 候選。在 Piccolo 上，這個改寫在每個指令都只命中一個節點：`alu_outputs___1_addr__h5583`（store 位址）。

要誠實說明：這個改寫是因為 `semantic_candidates` 已知「SB 的正確配對因為 concat 而不在選單裡」才加的。它對所有指令、所有 arm 一視同仁；新名字 `…__rhs` 不含 `imm`／`SEXT`，所以不改變預先登記的配對器（S、auto 用的）選出的配對。實際檢查：每個指令在改寫前後的 `match_pairs` 結果相同。改寫後 wrapper 的 sha256 在 `problems/<case>/wrapper.v.sha256`。

### 1.2 Units 與 UF 候選

- units：`choice_abstraction.discover_units`，用 `flute-piccolo-20261025` 的具體模型 B0。每個指令都是 `csr_regfile`、`gpr_regfile_regfile`、`near_mem_dcache`、`near_mem_icache`。
- UF 候選（`candidates.json`，給 LLM 的選單）：`rules.match_pairs` 在 tie-break 之前的全部配對。ILA 端是讀 GPR 的二元運算子節點；RTL 端是同一運算子、且有一個運算元叫 `rs1_val*`／`rs2_val*` 的節點。
  - ADDI、ADD、SB、SH：3 個（`h5583`、`eaddr__h5553`、`rd_val___1__h6550`）
  - SUB、OR、XOR、ANDI、BEQ、BNE：各 1 個
  - SLTI、LUI、AUIPC、JAL：0 個
- 同一個 ILA 節點或 RTL 節點的候選，最多只能有一個設成 `uf`。違反的輸出由 `llm_rule.check_output` 拒絕（不修補）。

### 1.3 拆題

- property 有 GPR conjunct（x1..x31）的指令：`fine_choice.ila_split`，與之前相同。
- property 沒有 GPR conjunct 的指令（BEQ、BNE、SB、SH）：每個比較的 state `s` 依 operand fields 的值拆成 `s.rs1=a.rs2=b`（case `rs1==a&&rs2==b`），共 32×32 個。對每個 `s`，這些 case 涵蓋所有指令。這與 `semantic_candidates` 的 rs1×rs2 切法相同，但套用到每個 state，而不是只套到已知證不出的那個；它是所有 arm 共用的前處理。

### 1.4 抽樣

`random.Random(20261027)`，在各層內 `sample` 不放回，結果依拆題順序排列（`prepare.sample`）。

| 指令類型 | 層與數量 |
| --- | --- |
| 訓練 ADDI（16） | `mem` 1、frame 3、rs1=0 2、rs1=rd 2、rs1 ≠ 0 且 ≠ rd 8 |
| 寫入、無 operand field（LUI、AUIPC、JAL；20） | `mem` 1、frame 6、write 13 |
| 寫入、rs1（ANDI、SLTI；20） | `mem` 1、frame 3、rs1=0 2、rs1=rd 2、rs1 ≠ 0 且 ≠ rd 12 |
| 寫入、rs1 與 rs2（ADD、SUB、OR、XOR；20） | `mem` 1、frame 3、兩者皆 0 1、恰一個 0 2、rs1=rs2≠0 2、rd ∈ {rs1, rs2}（兩者相異非零）3、rs1、rs2、rd 兩兩相異且非零 8 |
| 無 GPR conjunct（BEQ、BNE、SB、SH；20） | 20 個平均分給各 state（BEQ／BNE：`load_en` 7、`pc` 7、`store_en` 6；SB／SH：`pc` 10、`store_en` 10）；每個 state 內：兩者皆 0 1、恰一個 0 1、rs1=rs2≠0 1、其餘都是 rs1 ≠ rs2 且非零 |

因為 seed 相同，拆法相同的指令抽到同樣的 sub-property 名稱。抽出的清單：

- `ADDI`（訓練，16）：`mem`、`x1.frame`、`x2.rs1=23`、`x4.frame`、`x5.rs1=14`、`x6.rs1=8`、`x7.rs1=14`、`x7.rs1=17`、`x8.frame`、`x14.rs1=0`、`x14.rs1=14`、`x14.rs1=30`、`x16.rs1=16`、`x18.rs1=0`、`x21.rs1=13`、`x28.rs1=18`
- `ADD_Flatten`、`SUB`、`OR`、`XOR`（各 20）：`mem`、`x1.frame`、`x2.rs1=2.rs2=24`、`x2.rs1=28.rs2=13`、`x3.rs1=6.rs2=0`、`x4.rs1=11.rs2=11`、`x5.rs1=28.rs2=8`、`x6.rs1=24.rs2=28`、`x8.rs1=2.rs2=30`、`x8.rs1=6.rs2=15`、`x8.rs1=16.rs2=16`、`x14.frame`、`x14.rs1=0.rs2=0`、`x16.frame`、`x16.rs1=12.rs2=13`、`x19.rs1=27.rs2=19`、`x23.rs1=17.rs2=8`、`x25.rs1=0.rs2=5`、`x29.rs1=6.rs2=29`、`x31.rs1=14.rs2=6`
- `ANDI`、`SLTI`（各 20）：`mem`、`x1.rs1=28`、`x1.rs1=30`、`x2.rs1=23`、`x3.rs1=3`、`x4.rs1=15`、`x5.rs1=14`、`x6.rs1=8`、`x7.rs1=14`、`x7.rs1=17`、`x8.rs1=24`、`x14.frame`、`x14.rs1=0`、`x14.rs1=30`、`x16.frame`、`x18.frame`、`x21.rs1=13`、`x24.rs1=0`、`x28.rs1=18`、`x31.rs1=31`
- `LUI`、`AUIPC`、`JAL`（各 20）：`mem`、`x1.write`、`x2.frame`、`x2.write`、`x3.write`、`x4.write`、`x5.frame`、`x7.frame`、`x8.write`、`x14.write`、`x16.write`、`x18.write`、`x20.frame`、`x24.write`、`x25.write`、`x26.frame`、`x28.write`、`x29.write`、`x31.frame`、`x31.write`
- `BEQ`、`BNE_new`（各 20）：`load_en.rs1=0.rs2=0`、`load_en.rs1=2.rs2=23`、`load_en.rs1=5.rs2=14`、`load_en.rs1=6.rs2=8`、`load_en.rs1=7.rs2=7`、`load_en.rs1=8.rs2=0`、`load_en.rs1=28.rs2=18`、`pc.rs1=0.rs2=0`、`pc.rs1=1.rs2=0`、`pc.rs1=1.rs2=1`、`pc.rs1=1.rs2=28`、`pc.rs1=4.rs2=15`、`pc.rs1=8.rs2=24`、`pc.rs1=14.rs2=30`、`store_en.rs1=0.rs2=0`、`store_en.rs1=2.rs2=2`、`store_en.rs1=15.rs2=11`、`store_en.rs1=19.rs2=29`、`store_en.rs1=29.rs2=3`、`store_en.rs1=30.rs2=0`
- `SB`、`SH`（各 20）：`pc.rs1=0.rs2=0`、`pc.rs1=0.rs2=7`、`pc.rs1=2.rs2=23`、`pc.rs1=5.rs2=14`、`pc.rs1=6.rs2=8`、`pc.rs1=7.rs2=14`、`pc.rs1=7.rs2=17`、`pc.rs1=14.rs2=14`、`pc.rs1=21.rs2=13`、`pc.rs1=28.rs2=18`、`store_en.rs1=0.rs2=0`、`store_en.rs1=1.rs2=28`、`store_en.rs1=1.rs2=30`、`store_en.rs1=2.rs2=2`、`store_en.rs1=15.rs2=11`、`store_en.rs1=15.rs2=12`、`store_en.rs1=17.rs2=26`、`store_en.rs1=19.rs2=29`、`store_en.rs1=29.rs2=3`、`store_en.rs1=30.rs2=0`

## 2. Arm

每個測試指令、每個抽到的 sub-property 跑以下 arm（`scripts/specs.py`）：

| Arm | 定義 |
| --- | --- |
| split（= COI 規則） | 什麼都不拿掉：所有 unit keep、所有 GPR keep、沒有 UF。`rules.py` 的 COI 規則只拿掉 COI 外的東西，rIC3 本來就只看 COI，所以兩者等價；每個 split 模型的實際 COI bits 會記錄下來。 |
| auto | `fine_choice.coarsest`（unit 全 cut、GPR 全拿掉、配對器的 UF），再做 CEGAR。 |
| S | `fine_choice.structural`，配對器的 UF（`s_pairs.json`）。 |
| `rules.py` 既有非 LLM 規則 | `results/semantic_candidates/scripts/rules.py` 只有三條規則：COI、S、auto，就是上面三個 arm，不另外跑。配對器 `match_pairs` 不修改。 |
| DeepSeek | 第 3 節挑出的一條 DeepSeek 規則。 |
| Claude | 第 3 節挑出的一條 Claude 規則。 |

- 每個 run：`src/fine_batch.py` CEGAR，每個模型 300 s，最多 10 次 refinement，與之前的 S arm 相同。
- 同一個 sub-property 上，abstraction 相同的 spec（`scripts/batch.py` 的 key）只跑一次，各 arm 共用結果。
- LLM 規則原樣使用。被拒絕的 sub-property（驗證錯誤、執行錯誤、輸出不合法）記為「rejected」，算未證出，不跑 rIC3。

## 3. 挑選方法

1. 每個模型獨立生成 5 條規則（第 5 節）。
2. 每條規則套用到 ADDI 的 16 個訓練 sub-property，跑 rIC3（與測試相同的設定）。
3. 依序比較（`scripts/training.py`）：
   1. `UNSAT` 數多者優先；
   2. rejected 數少者優先（rejected 沒有模型，沒有 COI bits 和時間，所以先比這一項）；
   3. 非 rejected 的 sub-property 最終 COI state bits 總和小者優先；
   4. 非 rejected 的 sub-property 總時間（`total_seconds`：build + rIC3 + replay，所有 iteration）短者優先；
   5. 仍相同時，取順序在前者：初始 1–5，再來回饋後的 1–5。
4. 每個模型只挑一條，只有這一條跑測試題。

## 4. 回饋輪

- 每個模型最多一輪：5 條初始規則各得到一則回饋訊息，在同一個對話中再回答一次，得到 5 條修訂規則（`rule-fb<i>.py`）。
- 回饋內容只有該規則自己在 16 個訓練 sub-property 上的 rIC3 結果：每題的名稱、case、狀態（`UNSAT`／`TIMEOUT`／`max_iterations`／`real`／rejected 與錯誤訊息）、refinement 次數、依序被 refine 的 choice id。訊息模板在 `scripts/training.py` 的 `FEEDBACK`。不提 S，也不提其他規則或其他模型。
- 修訂規則同樣跑訓練題，與初始規則一起進入第 3 節的挑選（每個模型 10 條取 1）。

## 5. Prompt 與生成

- DeepSeek 與 Claude 用完全相同的 prompt：system 是 `src/llm_rule_context.txt`（= `prompt/prompt-system.txt`），user 是 `prompt/prompt-user.txt`（ADDI 的 design 加上 7 個不附答案的 ADDI 訓練 sub-property，`prompt/examples-ADDI.json`，與 pilot 相同）。
  - sha256 `prompt-system.txt`：`18685d6d654d49490752f9de711762344c302f81f1b055ecb35a5b094188f10d`
  - sha256 `prompt-user.txt`：`61e56e8fb9ace2f91229ef8c2d0de4757faa8c1b543d29980de9fd3c72e26db2`
  - sha256 `examples-ADDI.json`：`2de0e0369188ea566b93c78dd12fa9c2919eb4a99cf5a21e785b78617683c54b`
- 相對 pilot 的改動：
  - 目標（證得出來，模型越小越好；比較順序）與選錯的代價（太粗：CEGAR 退回、可能退錯、10 次用完；太細：超時，沒有反例可 refine）；
  - 設計事實：unit／模組、COI、GPR、運算子節點與運算元來源（`ila_operand_sources`／`rtl_operand_sources`：運算元與其讀的訊號的 Verilog 指定式，最多 3 層、每個運算元 6 行）、case 欄位、拆題方式；
  - 同一節點的多個 UF 候選最多一個 `uf`；
  - 明確要求不要用子字串判斷（舉例 "RISC" 含 "SC"、"for" 含 "OR"）。
- Prompt 中沒有 S 的程式碼、描述或結論，也沒有「GPR 應該 keep 或 word」之類的暗示。
- DeepSeek：本機閘道 `deepseek-flash`，reasoning effort `low`（`src/deepseek_chat.py`），獨立 5 次。花費上限 US$3（含回饋輪）。本輪不准使用 OpenRouter：閘道依序嘗試 OpenCode Go、Command Code，最後才是 OpenRouter，所以 `llm_rule.ask` 只接受 served model `deepseek-v4.1-flash`（OpenCode Go）或 `deepseek/deepseek-v4.1-flash`（Command Code）且回應沒有 `provider` 欄位；否則立即停止並回報，不再呼叫。
- Claude：本機已登入的 `claude -p`（個人 claude.ai 帳號），`--model opus`，獨立 5 次，每次一個新的空目錄。`src/claude_cli.py`：`--tools ""`、`--safe-mode`（不載入 CLAUDE.md、skills、hooks、plugins）、`--setting-sources ""`、`--strict-mcp-config` 加上空的 MCP 設定、`--system-prompt` 用我們的 prompt、環境變數只保留 HOME、PATH、USER、LANG。每次呼叫保留完整 stream-json 紀錄；init 事件列出任何工具或 MCP、或回答中出現 tool use，就視為失敗。實際 model id 從紀錄取得。
  - 若個人帳號額度不足、不能用 opus、或被限流：改用使用者授權的 Anthropic API key（只在行程內讀入環境變數），模型 `claude-opus-5-5`，API 花費上限 US$5，並記錄改用的原因。
  - 已知：smoke test 顯示 Claude Code 仍會在第一則 user 訊息附加使用者 email、工作目錄、平台與日期。這些不含 repo 或 S 的資訊。
- 金鑰不印出、不放進 CLI 參數、log、commit 或 artifact。不修改閘道設定或 allowlist。超出花費上限就停止並回報。

## 6. 機器與執行

- 所有計時的 rIC3 都在 zeus（2 × Xeon E5-2630 v4，40 threads）跑，不在 mazu 跑。工具：`zeus/env-20261024.sh`，rIC3 master `8c6df1b`（sha256 `90e7141b…6977`）、Yosys 0.68+120（binary sha256 與 mazu 相同）、同一個 venv（從 mazu rsync）與 `Pyverilog_NeuroAbs`。
- zeus 驗證：ADDI S 的 `x5.frame`、`x16.rs1=6`、`mem` 重現了已知結果（`UNSAT`，0／0／1 次 refinement，COI bits 981／1,077／1,322，與紀錄相同；`zeus/verify-ADDI-S.jsonl`）。
- 平行度：9 個 CPU 組，每組 2 個實體核心加上它們的 hyper-thread（`0,1,20,21` … `16,17,36,37`），同時最多 9 個 run。核心 18、19 留給系統與 spec 產生。所有 batch 由 `scripts/queue.sh` 一次一個執行，所以訓練與測試的每個 arm 都用同一台機器、同樣的平行度。
- 時間只在 zeus 內比較，不與 mazu 的舊紀錄比較。

## 7. 指標與判讀

主要指標（每個測試指令、每個 arm）：

1. `UNSAT` 數（20 個中；rejected 算未證出）；
2. refinement 總次數；
3. 最終 COI state bits（總和，以及只算 `UNSAT` 的總和）。

判讀：

- 「LLM 在某指令上贏過某 arm」= `UNSAT` 數較多。`UNSAT` 數相同時，再看 refinement 次數與 COI bits，但只描述差異，不宣稱「較好」，除非 `UNSAT` 數也較多。
- 特別報告 SB 與 BEQ（以及同題型的 SH、BNE）：LLM 挑出的規則是否贏過 S、split（COI）與 auto。
- 時間：只有主要結論做重複計時（`docs/evaluation.md`）。主要結論是 SB 與 BEQ 上的證明數比較。若 LLM 規則與某個非 LLM arm 在 SB 或 BEQ 上都證出某些 sub-property，取這些 sub-property 依抽樣順序的前 3 個，兩個 arm 的 spec 各在 zeus 上重跑 3 次（同一 CPU 組設定），報告分布。其他結果只報告單次時間，不做加速或減速結論。
- 也報告：每條規則在訓練題上的結果、挑選結果、每個模型的 rejected 數、DeepSeek 與 Claude 的比較。

## 8. 不做的事

- 不修補 LLM 規則；不改 `rules.py`、`fine_choice.refine`、rIC3 或 IC3 內部；不用 AVR；不用 sudo。
- 不以「與 S 一致」評分。

## 9. 修改

### 2026-10-27T14:48Z（22:48 +08）：取消 Claude 的 API key 備援

- 第 5 節第 105 行的 API key 備援，已依使用者指示取消。`~/.secrets` 中的 `ANTHROPIC_API_KEY` 是實驗室的 key，不是使用者的。
- Claude 一律使用本機已登入的個人 claude.ai 帳號（`claude -p`）。若個人帳號額度不足、無法使用 opus 或被限流，就停止並回報，不改用任何 API key。
- 這項備援實際上沒有觸發：
  - 生成 5 次、回饋 5 次，共 10 次 Claude 呼叫，stream-json 紀錄都是 `apiKeySource: none`、`claude-opus-5-5`。
  - 本實驗的程式從未讀取 `~/.secrets`。
  - Anthropic API 花費為 US$0。
- 第 105 行的原文保留不改。

### 2026-10-27T16:51Z（2026-10-28 00:51 +08）：停用 zeus，剩餘工作改在 mazu 跑

- 原因：使用者指示不再使用 zeus。zeus 是較舊的伺服器，使用者沒有打算讓本實驗使用它的資源。第 6 節「計時的 rIC3 只在 zeus 跑」不再適用；原文保留。
- 停止時間：約 2026-10-28 00:49 +08。當時 zeus 正在跑 XOR 的 LLM arm。這個 job 已停掉，它的部分結果只留作紀錄。
- 沿用 zeus 結果的指令：SB、BEQ、SH。這三個指令的五個 arm（split、auto、S、DeepSeek fb4、Claude fb2）都已在 zeus 跑完，使用同一組 9 個 CPU 群組。ADDI 訓練與規則挑選也在 zeus 完成，不重跑。
- 在 mazu 重跑全部五個 arm 的指令：ADD（ADD_Flatten）、SUB、OR、XOR、ANDI、SLTI、LUI、AUIPC、JAL、BNE（BNE_new）。其中 ADD、SUB、OR、BNE 的 LLM arm 已在 zeus 跑完，XOR 的 LLM arm 跑了一部分；這些 zeus 結果只留作紀錄，不進表格。
- 第 7 節中 SB、BEQ 的重複計時改在 mazu 跑。比較的 sub-property 與配對仍由 zeus 上的測試結果決定，方法照舊。
- mazu 的 CPU 配置（Intel i9-14900K）：
  - 只用 P-core CPU 0–11，分成 3 個群組：`0-3`、`4-7`、`8-11`。每組是 2 個 P-core 加上它們的 HT sibling，和 zeus 每組的形狀相同。
  - CPU 12–15 留給另一個 session；CPU 16–31（E-core）被另一個專案佔用，都不使用。
  - 同一個指令的所有 arm 都在同一台機器、同一組 CPU 上、以相同平行度執行。
- mazu 上的批次名為 `mazu`，結果在 `runs/<case>/mazu/`。工具版本與 zeus 相同：rIC3 8c6df1b、同一套 oss-cad-suite、Pyverilog_NeuroAbs。
- 只換執行機器，不改任何規則、樣本、挑選方式、時間上限或 refinement 上限。
