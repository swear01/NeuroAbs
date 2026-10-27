# 小型試驗：LLM 能否自己寫出選擇規則 S（Piccolo ILA，rIC3）

狀態（2026-10-27）。在 [`fine_gpr_choices`](../fine_gpr_choices/README.md) 裡，手寫的結構規則 S（`src/fine_choice.py` 的 `structural()`）在 Piccolo 上追平或勝過逐個 sub-property 呼叫 DeepSeek 的結果。但 S 是看過 DeepSeek 對 ADDI 的回答後才寫的，所以這個比較是循環的。本試驗讓 DeepSeek 只看到設計與選單描述，加上幾個不附答案的 ADDI sub-property，由它自己寫一條規則（Python 函式），再把規則套用到 ADDI 全部 1,024 個 sub-property，以及留出的 LUI、AUIPC、JAL（各 63 個）。

結論摘要：

- 3 條獨立生成的規則都通過驗證，每個 sub-property 都產生合法輸出，沒有被拒絕的。
- **規則 1 與 S 完全相同**：ADDI 1,024/1,024，LUI、AUIPC、JAL 各 63/63。因此它的證明結果就是 S 已記錄的結果（四個指令全部 `UNSAT`），不需要重跑。
- 規則 2 在 ADDI 寫入情形中保留了加法器（`uf0` keep），並把 rd 設成 keep。在抽樣的 16 個 ADDI sub-property 中只證明 1 個（`x5.rs1=0`），15 個 `TIMEOUT`，而 S 在同一批上 16/16 `UNSAT`。在 LUI、AUIPC、JAL 上，它與 S 不同的 sub-property 全部 `UNSAT`，所以這三個指令都能完整證明。
- 規則 3 在每個 sub-property 上都與 S 不同：因為描述字串的子字串誤配（`"SC"`），它保留了 D-cache；rd 設成 keep；AUIPC、JAL 還保留了 I-cache。結果 ADDI 抽樣 64/64、LUI、AUIPC、JAL 全部 `UNSAT`，0 次 refinement，但在可比較的 CPU 組上比 S 慢（見下方時間表；只跑一次，不構成速度結論）。
- LLM 花費：3 次呼叫，US$0.1103。
- 循環性**只部分解除**（見最後一節）：3 個樣本中有 1 個在沒看過 S 的情況下重現了 S。但要從 3 個樣本裡挑出它，需要一個信號；而且介面與選單本身是知道 S 的人設計的。

## 設計

### 規則介面與執行（`src/llm_rule.py`、`src/llm_rule_exec.py`）

規則是一段受限 Python 原始碼，必須定義 `choose(sub, design)`，並對 `design["choices"]` 中每個 choice id 回傳一個合法 level。

- `design`（`design_input`）包含：
  - 屬性描述（`description.txt`）
  - `operand_fields`
  - 每個 choice 的 id、kind、levels。unit 另附 instance、module、COI bits、輸出埠；gpr 附暫存器號碼；operator 附 ILA/RTL 節點與運算式。
  - 每個 GPR 只涉及自己的 assume 式子（`gpr_assumptions`）
- `sub`（`sub_input`）包含：名稱、比較的 states、case 字串與解析後的 `case_terms`、assertion 式子。

執行與檢查：

- `validate` 以 AST 白名單檢查原始碼，拒絕以下內容：
  - import、while、try、with、class、del、global
  - 模組層級的非函式敘述
  - 底線開頭的名稱
  - 白名單以外的屬性，以及沒有被呼叫的屬性存取
  - 白名單以外的 builtin（執行時只提供 `SAFE_BUILTINS`）
- 規則在 `python3 -I src/llm_rule_exec.py` 子行程中執行（cwd `/`，RLIMIT_CPU 20 s，RLIMIT_AS 1 GiB，逾時 120 s）。每次呼叫前都會深拷貝輸入。
- 輸出必須恰好涵蓋每個 choice id，且 level 合法（`check_output`）。違反任何一項，該 sub-property 就被拒絕並回報，**不做任何修補**。
- 合法輸出經 `fine_choice_llm.to_spec` 轉成 spec，與 `fine_choice.structural` 比較（`normal`：keep/word GPR、units、uf）。

單元測試在 `tests/test_llm_rule.py`。

### Prompt（`prompt/`）

- system 是 `src/llm_rule_context.txt`：level 語意、refinement 說明、規則任務、輸入格式、受限語法、回答格式。
- user 是 ADDI 的 `design` 加上 7 個不附答案的訓練 sub-property（`prompt/examples-ADDI.json`：`mem`、`x5.frame`、`x17.frame`、`x5.rs1=0`、`x5.rs1=5`、`x5.rs1=6`、`x31.rs1=1`）。

Prompt 中**沒有**以下內容：S 的程式碼或描述、`fine_gpr_choices` README 中關於 S 的結論、`specs-structural*.jsonl`、`llm-decisions.jsonl`、DeepSeek 先前的回答。實際送出的請求與提交的 `prompt-system.txt`、`prompt-user.txt` 逐位元相同（已對照閘道的呼叫紀錄）。

sha256：

- `prompt-system.txt` 1ade64ba…
- `prompt-user.txt` 9d14c2a3…（30,824 bytes）
- `examples-ADDI.json` 2de0e036…

### 生成

透過本機閘道呼叫 `deepseek-flash`（served `deepseek-v4.1-flash`），reasoning effort low，獨立呼叫 3 次（`scripts/generate.sh 3`）。只做 zero-shot，因為最好的規則（規則 1）已經等於 S，所以**沒有**做可選的回饋輪。

| 樣本 | prompt tokens | completion tokens | 時間 s | 驗證錯誤 |
| --- | ---: | ---: | ---: | --- |
| 1 | 14,352 | 30,487 | 241 | 無 |
| 2 | 14,352（快取） | 28,741 | 204 | 無 |
| 3 | 14,352（快取） | 28,911 | 227 | 無 |

花費 US$0.1103：依 repo 的價格公式（`deepseek_prices.usage_cost`）計算，閘道記錄的 list cost 合計也相同。

### rIC3 執行

與 S arm 相同：`src/fine_batch.py` CEGAR，每個模型 300 s，最多 10 次 refinement。只跑規則與 S 不同的 sub-property；與 S 相同的 sub-property 直接沿用 `fine_gpr_choices/piccolo/<case>/` 的 S 紀錄。

- LUI、AUIPC、JAL：規則 2、3 所有不同的 sub-property 都跑了，所以得到整個指令的證明結果。
- ADDI：規則 2 有 992 個、規則 3 有 1,024 個 sub-property 與 S 不同，因此**抽樣**，用 `fine_gpr_choices` 的 64 個抽樣 sub-property（`subs-sample.json`）：
  - 規則 2 在抽樣中與 S 不同的有 32 個寫入情形，取每隔一個，共 16 個。
  - 規則 3 跑全部 64 個。

ADDI 的結果只代表抽樣，不是完整證明。

## 規則與 S 的一致性

規則原文在 `rules/rule-{1,2,3}.py`，完整回答在 `rules/answers.jsonl`。逐 sub-property 的比較在 `piccolo/compare-rule<i>-<case>.json`，與 S 不同時兩份 spec 都會列出。

| 規則 | ADDI（1,024） | LUI（63） | AUIPC（63） | JAL（63） | 拒絕 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 1,024 相同 | 63 相同 | 63 相同 | 63 相同 | 0 |
| 2 | 32 相同 / 992 不同 | 32 / 31 | 32 / 31 | 31 / 32 | 0 |
| 3 | 0 / 1,024 | 0 / 63 | 0 / 63 | 0 / 63 | 0 |

### 各規則的做法

**規則 1**
- 比較的 GPR（只要可能不被寫入）設為 keep。
- 寫入情形中，case 固定的 operand 設為 keep；rd 設為 word，前提是 rd 不被保留。
- operand 不固定時，所有 GPR 都設為 keep（ADDI、LUI、AUIPC、JAL 的 split 都沒有這種情形）。
- 只有兩種情況會保留 unit：assertion 中出現該 unit 的 instance 或輸出名稱；或描述中出現 CSR、LOAD、STORE、LW、SB 等關鍵字。這四個指令都沒有觸發，所以全部 cut。
- operator 一律設為 uf。

結果等於 S。

**規則 2**
- GPR 的處理與 S 類似，但寫入情形的 rd 設為 keep 而非 word。
- operator 在「資料相依」的寫入情形中，只要 operator 運算式與指令關鍵字不匹配就設為 keep。在 ADDI 中，這等於拿掉了 UF。
- 描述中的 `"JAL"` 觸發了分支邏輯，所以 JAL 的 `mem` 也保留 operator。

| 指令 | 與 S 的差異 | 數量 |
| --- | --- | ---: |
| ADDI | rd keep、`uf0` keep | 961 |
| ADDI | `rs1 == rd` 情形，只差 `uf0` keep | 31 |
| LUI | 寫入情形 rd keep | 31 |
| AUIPC | 寫入情形 rd keep、operator keep | 31 |
| JAL | 寫入情形 rd keep、operator keep | 31 |
| JAL | `mem` 的 operator keep | 1 |

**規則 3**
- 比較的 GPR 與來源 GPR 都設為 keep，包括寫入情形的 rd。
- unit 依描述關鍵字決定：
  - D-cache 的關鍵字中有 `"LR"`、`"SC"`，四個指令的描述都含有 `"SC"` 子字串，所以 D-cache 一律保留。
  - I-cache 在描述含 `"JAL"`、`"AUIPC"`，或 assertion 含 `pc` 時保留，所以 `mem` 與 AUIPC、JAL 的所有 sub-property 都保留 I-cache。
- operator 只有在描述含算術指令名稱時設為 uf。ADDI 正確匹配；LUI、AUIPC、JAL 是因為 `"OR"` 子字串誤配。

| 指令 | 與 S 的差異 |
| --- | --- |
| ADDI、LUI | D-cache keep（全部）；寫入情形 rd keep；`mem` 另保留 I-cache |
| AUIPC、JAL | D-cache 與 I-cache keep（全部）；寫入情形 rd keep |

三條規則都靠描述字串的關鍵字做判斷，這種判斷很脆弱：規則 3 的子字串誤配就是例子；規則 1 的 `"LD"`、`"SB"`、`"SH"` 也可能在別的指令描述中誤配。

## 結果

### 與 S 不同的 sub-property（rIC3）

- 「S 同批」是 `fine_gpr_choices` 中 S 在同一批 sub-property 上的紀錄（ADDI 抽樣與 JAL 的 S 跑在 E-cores，LUI、AUIPC 跑在 P 12–15）。
- 本試驗全部跑在 P-cores 12–13 / 14–15。
- 「整個指令」是規則跑過的部分加上與 S 相同部分的 S 紀錄。

| 指令 | 規則 | 跑的數量 | `UNSAT` | 未證明 | refinements | 時間 s | 中位數 s | S 同批：`UNSAT`、refinements、時間 s、中位數 s |
| --- | --- | ---: | ---: | --- | ---: | ---: | ---: | --- |
| ADDI（抽樣） | 2 | 16 | 1 | 15 `TIMEOUT` | 0 | 4,586 | 305 | 16、0、849、52 |
| ADDI（抽樣） | 3 | 64 | 64 | — | 0 | 3,085 | 42 | 64、1、2,627、40 |
| LUI | 2 | 31 | 31 | — | 0 | 352 | 11 | 31、0、357、12 |
| LUI | 3 | 63 | 63 | — | 0 | 1,259 | 19 | 63、1、934、15 |
| AUIPC | 2 | 31 | 31 | — | 0 | 336 | 11 | 31、0、517、17 |
| AUIPC | 3 | 63 | 63 | — | 0 | 2,481 | 36 | 63、1、1,204、18 |
| JAL | 2 | 32 | 32 | — | 1 | 304 | 9 | 32、1、775、23 |
| JAL | 3 | 63 | 63 | — | 0 | 2,078 | 32 | 63、1、1,608、25 |

整個指令（留出指令）：

| 指令 | S | 規則 1 | 規則 2 | 規則 3 |
| --- | --- | --- | --- | --- |
| LUI | 63 `UNSAT`、1 refinement、934 s | = S | 63、1、929 s | 63、0、1,259 s |
| AUIPC | 63、1、1,204 s | = S | 63、1、1,023 s | 63、0、2,481 s |
| JAL | 63、1、1,608 s | = S | 63、1、1,137 s | 63、0、2,078 s |

- 規則 2 在 ADDI 的 15 個 `TIMEOUT` 都是保留加法器的寫入情形，與 `fine_gpr_choices` 中 DeepSeek 保留 `uf0` 的 4 個 `TIMEOUT`，以及 split baseline 中 S 不帶 UF 時只證得 `rs1 = 0` 的結果一致。`TIMEOUT` 不產生反例，所以 CEGAR 無法修正。規則 2 唯一證出的 ADDI sub-property 是 `x5.rs1=0`。
- 規則 2 若用在整個 ADDI，有 961 個這類寫入情形，預期大多無法證明（這是依抽樣推論，沒有實際跑）。
- 規則 3 的 `mem` 保留了 I-cache，所以省下 S 的那 1 次 refinement；但每個 sub-property 多保留了 D-cache（和 I-cache），模型更大。

### 時間的注意事項

- 執行期間（10:59–13:07）另一個 session 在 E-cores 20–31 上跑搜尋，load average 30–100。本試驗只用 P-cores 12–15。
- S 對照組在同一 CPU 組上重跑了每個指令的 7–8 個 S spec（`arm-S-control-<case>.jsonl`），與 S 的紀錄相比，時間比值（重跑 / 紀錄）如下：

  | 指令 | 中位數 | 範圍 | S 紀錄的 CPU |
  | --- | ---: | --- | --- |
  | LUI | 0.95 | 0.91–0.97 | P 12–15（同組） |
  | AUIPC | 0.94 | 0.93–0.97 | P 12–15（同組） |
  | JAL | 0.52 | 0.45–0.54 | E 28–31 |
  | ADDI | 0.52 | 0.43–0.57 | E 24–27 |

- 因此，JAL 與 ADDI 的時間不能直接和 S 紀錄比較：規則 2 在 JAL 上 304 s 對 775 s 的差距，大部分來自 CPU 組不同。若用 0.52 換算，規則 3 的 ADDI 抽樣大約是 S 的 2 倍時間。
- 所有規則 arm 都只跑一次，沒有依 [`docs/evaluation.md`](../../docs/evaluation.md) 做重複計時，所以**不做任何加速或減速的結論**。只有證明數（`UNSAT` / `TIMEOUT`）可以下結論。

### 與 repo 中既有數字的對照

數字取自 [`fine_gpr_choices`](../fine_gpr_choices/README.md) 與 [`split_baseline`](../split_baseline/README.md)，每個模型 300 s。ADDI 一欄是 64 個抽樣 sub-property，其他指令是全部 63 個。

| Arm | ADDI | LUI | AUIPC | JAL | LLM 花費 |
| --- | --- | --- | --- | --- | --- |
| split-only（無抽象） | 19 / 64 | 61 | 63 | 53 | — |
| auto CEGAR | 34 / 64，23,893 s | （7 個抽樣全證） | （7 個） | （7 個） | — |
| DeepSeek 逐 sub-property | 60 / 64，3,805 s | 62，2,005 s | 63，1,828 s | 62，2,243 s | $0.47 + $0.35 + $0.43 + $0.49 = $1.74，253 次呼叫 |
| S（手寫） | 64 / 64，2,627 s | 63，934 s | 63，1,204 s | 63，1,608 s | — |
| 規則 1（LLM 寫，= S） | 64 / 64（ADDI 全部 1,024） | 63 | 63 | 63 | $0.1103，3 次呼叫產生 3 條規則 |
| 規則 2 | 抽樣 16 個不同中 1 個證明 | 63 | 63 | 63 | 同上 |
| 規則 3 | 64 / 64，3,085 s | 63 | 63 | 63 | 同上 |

規則的花費是一次性的。產生 3 條規則後，套用到 1,213 個 sub-property 不再需要任何 LLM 呼叫。逐 sub-property 的 DeepSeek 則每個 sub-property 一次呼叫。

## 循環性是否解除

**部分解除。**

支持的證據：
- DeepSeek 在沒有看到 S、S 的描述或先前答案的情況下，3 次中有 1 次寫出了與 S 在 1,213 個 sub-property 上逐一相同的規則，而且包含留出的三個指令。
- 規則 2 與規則 3 的偏差（rd keep、保留加法器、保留 cache）都是可讀的程式邏輯，可以從規則原文直接看出原因，而不是逐題回答的隨機差異。

限制：
1. 3 個樣本中有 2 個比 S 差。規則 2 在 ADDI 上大多無法證明；規則 3 能證明，但模型較大。要從 3 個樣本中挑出規則 1，需要一個選擇信號。一個不循環的候選信號是 ADDI 訓練抽樣上的實際 rIC3 結果，但本試驗沒有把它當作預先登記的選擇程序來執行。
2. 介面本身帶有設計者的知識：選單（unit cut/keep、GPR keep/word/havoc、operator UF）、split、解析好的 `case_terms`、`operand_fields`、`gpr_assumptions`，都是知道 S 的人設計的。這些輸入讓「keep 比較的 GPR 與 case 中的 operand、rd 設為 word」成為很自然的寫法。
3. 規則依賴描述字串的關鍵字，屬於脆弱的啟發式；規則 3 的 `"SC"` 與 `"OR"` 誤配就是例子。
4. 範圍很小：一個處理器、四個沒有記憶體或 CSR 存取的指令、一個模型、3 個樣本。ADDI 只抽樣跑了不同的 sub-property。

## 重現

在 repo 根目錄執行（需要 `/var/tmp/neuroabs-runtime/env-20261024.sh`、本機 DeepSeek 閘道，以及在 `PYTHONPATH` 中的 `Pyverilog_NeuroAbs`，見 `scripts/env.sh`）：

```bash
. results/llm_rule_pilot/scripts/env.sh               # 設定 $RUN、$R、$P 與 PYTHONPATH
results/llm_rule_pilot/scripts/generate.sh 3          # prompt 與 3 條規則（呼叫 DeepSeek，約 US$0.11）
for i in 1 2 3; do                                      # 規則與 S 的逐 sub-property 比較
  results/llm_rule_pilot/scripts/apply.sh $RUN/gen/rule-$i.py rule$i
done
results/llm_rule_pilot/scripts/specs.sh               # 與 S 不同、要跑 rIC3 的 spec（ADDI 抽樣）
results/llm_rule_pilot/scripts/queue.sh               # S 對照組、規則 2、規則 3（P-cores 12–15）
python3 results/llm_rule_pilot/scripts/summarize.py $RUN > results/llm_rule_pilot/piccolo/summary.json
```

`$RUN` 是 `/var/tmp/neuroabs-runtime/runs/llm-rule-20261027`。規則已提交在 `rules/`；`apply.sh` 也可以直接用 `rules/rule-$i.py`，結果相同。每個 arm 的 rIC3 紀錄在 `piccolo/arm-<arm>-<case>.jsonl`，跑過的 spec 在 `piccolo/specs/`，彙總在 `piccolo/summary.json`。單元測試：

```bash
python3 -m unittest discover -s tests -p 'test_llm_rule.py'
```
