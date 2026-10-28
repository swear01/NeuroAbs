# 留出指令上的 LLM 選擇規則比較（Piccolo ILA，rIC3）

狀態（2026-10-28）。DeepSeek 與 Claude 各寫 5 條選擇規則，再各有一輪回饋，共 10 條。每個模型只依 ADDI 訓練題挑出一條，然後在 13 個留出指令上，和 split（= COI）、auto、S 比較。預先登記見 [`PREREG.md`](PREREG.md)，第 9 節是登記後的修改。本輪**不以「與 S 一致」評分**，只看 rIC3 的 `UNSAT` 數、refinement 次數和最終 COI bits。

結論摘要：

- 挑出的規則是 Claude `rule-fb2` 和 DeepSeek `rule-fb4`。兩條都是回饋輪的修訂版，在 ADDI 訓練題上都是 16/16 `UNSAT`、0 次 refinement。
- 13 個指令合計（每個 20 題，共 260 題）的 `UNSAT` 數：Claude fb2 246、DeepSeek fb4 228、S 217、auto 195、split 155。沒有任何被拒絕的 sub-property。
- 兩條 LLM 規則在 ADD 上都是 20/20，S 和 auto 都是 9/20。原因是配對：S 把 ILA 的加法配給 load 位址加法器 `eaddr__h5553`，LLM 規則配給 `rd_val___1__h6550`。這個選擇不是平手，所以和選單順序無關（見下文）。
- SB、SH：Claude fb2 20/20，S、auto、DeepSeek fb4 都是 11/20。**但 fb2 的 20/20 來自選單順序**：fb2 給 `h5583` 和 `eaddr` 同分，平手時取排在前面的 `h5583`。[PR #22](https://github.com/swear01/NeuroAbs/pull/22)（`results/sb_llm_per_sub`）把選單順序反過來後，fb2 在 SB `store_en` 掉到 1/10，和 S 相同。
- BEQ、BNE：S、DeepSeek fb4、Claude fb2 都是 20/20；auto 和 split 都是 15/20。
- SLTI 沒有 UF 候選，五個 arm 都是 6/20，而且沒證出的 14 題都相同。
- 除了 ADD、SB、SH，兩條 LLM 規則的 `UNSAT` 數都與 S 相同。它們的 refinement 次數較少（大多為 0），COI bits 相近或較小。依預先登記的判讀規則，`UNSAT` 數相同時不宣稱較好。
- LLM 花費：DeepSeek 依 `src/deepseek_prices.py` 估算為 US$0.3101，閘道回報的 `list_cost` 合計 US$0.155。Claude 用個人 claude.ai 帳號（`claude -p`），Anthropic API 花費 US$0。

## 設定

完整定義在 `PREREG.md`。重點如下：

- 訓練用 ADDI，抽 16 個 sub-property。測試用 ADD（`ADD_Flatten`）、SUB、OR、XOR、ANDI、SLTI、LUI、AUIPC、JAL、BEQ、BNE（`BNE_new`）、SB、SH，每個指令用固定 seed 抽 20 個 sub-property。LB 的 property 本身不成立，所以排除。
- Arm：
  - split（= COI）：什麼都不拿掉。
  - auto：`fine_choice.coarsest` 加上 CEGAR。
  - S：`fine_choice.structural`。
  - 兩條 LLM 規則：原樣使用；驗證或執行失敗就記為 rejected。`rules.py` 的既有規則就是 COI、S、auto 這三條，所以不另外跑。
- 每個 run：`src/fine_batch.py` CEGAR，每個模型限時 300 s，最多 10 次 refinement。
- 挑選順序：`UNSAT` 數多者優先，再來是 rejected 少、最終 COI bits 小、時間短（`scripts/training.py`）。回饋只含規則自己在訓練題上的 rIC3 結果，不提 S。
- Prompt 對兩個模型完全相同，不含 S 的資訊，並明確禁止用子字串判斷。sha256 記在 `PREREG.md` 第 5 節。

### 預先登記早於所有 LLM 呼叫

- `PREREG.md` 在 commit `ab3e05c` 中 commit，時間 2026-10-27T10:10:32Z（18:10:32 +08）。
- 第一次 LLM 呼叫約在 10:11:23Z：DeepSeek 的 5 次生成依序執行，run 目錄的 `gen-deepseek.log` 在 10:29:52Z 寫完，往回減去 `rules/deepseek/answers.jsonl` 中 5 次的 `elapsed_seconds`（共 1,109 s）。Claude 最早的 stream-json 紀錄是 10:12:07Z（`rules/claude/*.claude.jsonl`）。
- 之後的兩次修改（取消 API key 備援、停用 zeus）都寫在 `PREREG.md` 第 9 節，舊文字保留。

## 訓練與挑選（ADDI 16 題，zeus）

| 名次 | 規則 | UNSAT | rejected | 最終 COI bits | 時間 s | refinement | 狀態 |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | `claude-fb2` | 16 | 0 | 15,773 | 836 | 0 | UNSAT 16 |
| 2 | `deepseek-fb4` | 16 | 0 | 16,169 | 947 | 0 | UNSAT 16 |
| 3 | `deepseek-fb5` | 16 | 0 | 16,169 | 947 | 0 | UNSAT 16 |
| 4 | `deepseek-4` | 16 | 0 | 16,169 | 968 | 1 | UNSAT 16 |
| 5 | `deepseek-5` | 16 | 0 | 16,169 | 968 | 1 | UNSAT 16 |
| 6 | `deepseek-fb2` | 16 | 0 | 16,169 | 968 | 1 | UNSAT 16 |
| 7 | `claude-fb4` | 16 | 0 | 16,744 | 865 | 0 | UNSAT 16 |
| 8 | `claude-4` | 16 | 0 | 17,576 | 857 | 0 | UNSAT 16 |
| 9 | `claude-2` | 6 | 0 | 13,843 | 3,381 | 0 | TIMEOUT 10、UNSAT 6 |
| 10 | `deepseek-2` | 6 | 0 | 13,853 | 3,388 | 1 | TIMEOUT 10、UNSAT 6 |
| 11 | `claude-fb3` | 6 | 0 | 14,438 | 3,392 | 0 | TIMEOUT 10、UNSAT 6 |
| 12 | `deepseek-fb1` | 6 | 0 | 20,319 | 3,449 | 0 | TIMEOUT 10、UNSAT 6 |
| 13 | `claude-fb5` | 6 | 0 | 27,538 | 3,533 | 0 | TIMEOUT 10、UNSAT 6 |
| 14 | `deepseek-1` | 6 | 0 | 31,427 | 5,623 | 49 | TIMEOUT 10、UNSAT 6 |
| 15 | `deepseek-3` | 6 | 0 | 35,025 | 7,841 | 83 | TIMEOUT 9、UNSAT 6、max_iterations 1 |
| 16 | `deepseek-fb3` | 6 | 0 | 53,701 | 3,495 | 0 | TIMEOUT 10、UNSAT 6 |
| 17 | `claude-fb1` | 5 | 0 | 44,785 | 4,171 | 0 | TIMEOUT 11、UNSAT 5 |
| 18 | `claude-3` | 4 | 12 | 4,078 | 174 | 0 | rejected 12、UNSAT 4 |
| 19 | `claude-1` | 0 | 16 | 0 | 0 | 0 | rejected 16 |
| 20 | `claude-5` | 0 | 16 | 0 | 0 | 0 | rejected 16 |

- 前兩名都是 16/16 `UNSAT`，由 COI bits 決定名次：Claude `claude-fb2`（15,773）、DeepSeek `deepseek-fb4`（16,169）。
- Rejected 都出在 Claude 的初始規則：
  - `claude-1`、`claude-5`：模組層級的非函式敘述、`try`/`except`、不允許的屬性 `isalnum`；
  - `claude-3`：執行時 `NameError: isinstance`。
- 回饋輪之後，Claude 的 5 條修訂規則都沒有被拒絕。

## 測試結果（每個指令 20 題）

每格：`UNSAT` 數／refinement 次數／最終 COI bits 總和（千）。全部是 `rejected` 0。

| 指令 | 機器 | split (COI) | auto | S | DeepSeek fb4 | Claude fb2 |
| --- | --- | --- | --- | --- | --- | --- |
| ADD | mazu | 6／0／103.2 | 9／137／48.5 | 9／101／45.2 | **20**／0／21.6 | **20**／0／21.4 |
| SUB | mazu | 8／0／103.2 | 8／115／46.3 | 20／1／22.4 | 20／0／21.6 | 20／0／21.4 |
| OR | mazu | 10／0／103.2 | 20／118／46.9 | 20／1／22.4 | 20／0／21.6 | 20／0／21.4 |
| XOR | mazu | 8／0／103.2 | 20／115／46.3 | 20／1／22.4 | 20／0／21.6 | 20／0／21.4 |
| ANDI | mazu | 15／0／103.2 | 20／104／46.4 | 20／1／21.2 | 20／0／17.4 | 20／0／20.1 |
| SLTI | mazu | 6／0／103.2 | 6／91／44.5 | 6／1／17.4 | 6／0／17.4 | 6／0／17.4 |
| LUI | mazu | 20／0／103.2 | 20／75／41.7 | 20／1／16.1 | 20／0／16.1 | 20／0／16.1 |
| AUIPC | mazu | 20／0／103.2 | 20／79／43.3 | 20／1／16.1 | 20／0／16.1 | 20／0／16.1 |
| JAL | mazu | 20／0／103.2 | 20／80／43.7 | 20／1／16.1 | 20／0／16.1 | 20／0／16.1 |
| BEQ | zeus | 15／0／103.3 | 15／34／26.2 | 20／7／23.6 | 20／7／19.1 | 20／0／23.0 |
| BNE | mazu | 15／0／103.3 | 15／34／26.2 | 20／7／23.6 | 20／7／19.1 | 20／0／23.0 |
| SB | zeus | 6／0／103.3 | 11／74／36.1 | 11／73／40.0 | 11／53／34.0 | **20**／0／24.7 |
| SH | zeus | 6／0／103.3 | 11／83／37.6 | 11／62／38.3 | 11／59／36.4 | **20**／0／24.7 |

合計：

| Arm | UNSAT | refinement | 最終 COI bits | 只算 UNSAT 的 COI bits |
| --- | ---: | ---: | ---: | ---: |
| split (COI) | 155 / 260 | 0 | 1,342,092 | 799,977 |
| auto | 195 / 260 | 1,139 | 533,748 | 380,794 |
| S | 217 / 260 | 258 | 324,803 | 240,579 |
| DeepSeek fb4 | 228 / 260 | 126 | 278,137 | 225,181 |
| Claude fb2 | 246 / 260 | 0 | 266,862 | 254,678 |

- 沒證出的全部是 `TIMEOUT`，只有 SH auto 的 `store_en.rs1=29.rs2=3` 是 `max_iterations`。逐題清單由 `scripts/table.py` 產生。
- 合計的時間跨兩台機器，所以不列出，也不做速度結論。單次時間在 `summary.json`。
- 數字由原始結果重算：`scripts/summarize.py <run> split auto S deepseek-fb4 claude-fb2`，存成 `summary.json`。表格由 `scripts/table.py summary.json training/all.json` 產生。

### ADD：配對選的加法器不同

ADD 的 UF 候選與 ADDI 相同，有 3 個 RTL 加法器都配上 ILA 的加法 `n175`：`alu_outputs___1_addr__h5583`（store 位址）、`eaddr__h5553`（load 位址）、`rd_val___1__h6550`（寫回 rd 的值）。

- S 和 auto（配對器 `s_pairs.json`）在 20 題都配給 `eaddr`，也就是 load 位址。
  - 寫入 rd 的題目會一直 refine 或超時：S 9/20、101 次 refinement；auto 9/20、137 次。
- Claude fb2 在 15 題、DeepSeek fb4 在 16 題配給 `rd_val`，其餘題不配 UF。兩者都是 20/20、0 次 refinement。
- 這不是平手：
  - fb2 的 `op_score` 對寫 rd 的指令，給名稱同時含 `rd` 和 `val` 的節點 +10，給含 `addr`／`eaddr` 的節點 −5；分數小於 0 的不用。
  - fb4 也一樣：寫回時 `rd_val` +10，`addr`／`eaddr` −10。
  - 所以 `rd_val` 是唯一的最高分，跟選單順序無關。
- SUB 的選單只有一個候選 `rd_val___1__h6558`，S 也配給它，所以 S 20/20。auto 在 SUB 只有 8/20：經過 115 次 refinement，12 題仍超時。

### SB、SH：fb2 的 20/20 來自選單順序

SB、SH 的選單和 ADD 一樣，ILA 端是位址加法 `n110`。

| Arm | 配對（20 題） | pc（10 題） | store_en（10 題） |
| --- | --- | --- | --- |
| S、auto | 全部 `eaddr` | 10 | 1 |
| DeepSeek fb4 | pc 題 `h5583`，store_en 題不配 UF | 10 | 1 |
| Claude fb2 | 18 題 `h5583`，`rs1=0.rs2=0` 的 2 題不配 UF | 10 | 10 |

（SB 的數字；SH 的 `UNSAT` 數相同。）

- `store_en` 要證得出來，關鍵是把 store 位址加法器 `h5583` 配給 `n110`（`semantic_candidates`）。
- fb2 在 store_en 題上挑了 `h5583`，10/10 都是 0 次 refinement 的 `UNSAT`。但這是平手的結果：
  - SB 不寫 rd。fb2 的 `op_score` 給含 `addr`／`eaddr` 的節點 +5；`alu_outputs___1_addr__h5583` 和 `eaddr__h5553` 都含 `addr`，都是 +5。
  - 平手時取選單上排前面的那個。`h5583` 是 `prepare.name_operands` 新增的候選，剛好排第一。
- [PR #22](https://github.com/swear01/NeuroAbs/pull/22)（`results/sb_llm_per_sub`）把選單順序反過來：
  - fb2 在 SB `store_en` 掉到 1/10，和 S 相同；
  - 9 題改挑 `eaddr`，這 9 題的 spec 和 S 完全相同。
- 所以 fb2 在 SB、SH 上贏 S，不是規則判斷出了 store 位址。SH 的選單與 SB 相同，是同一個機制；#22 沒有在 SH 上跑反序。
- DeepSeek fb4 對有 `load_en`／`store_en` 的題目一律不配 UF（`if not is_mem_sub`），而且把 GPR 全部 havoc。store_en 題因此 9/10 超時，和 S 同樣是 11/20。

### BEQ、BNE

- S、DeepSeek fb4、Claude fb2 都是 20/20。只有一個候選（比較器 `…_EQ_ETC___d216`），三者都用它，或在部分題目不用 UF。
- fb2 0 次 refinement；S 和 fb4 各 7 次（pc 題各 1 次）。
- auto 和 split 都在同樣 5 題 `pc` 上超時（15/20）。
- BNE 的結果與 BEQ 逐格相同：BEQ 在 zeus 跑，BNE 在 mazu 跑。

### DeepSeek 與 Claude

- 兩條規則在 SB、SH 以外的 11 個指令上，`UNSAT` 數都相同。差別都在 SB、SH 的 `store_en`（18 題）；如上所述，那是選單順序造成的。
- 不看 SB、SH 時，兩者都是 206/220，S 是 195/220（差在 ADD 的 11 題）。
- Refinement：fb2 全部 0 次；fb4 共 126 次，全在 BEQ、BNE、SB、SH。
- Rejected：測試都是 0。訓練時，Claude 的初始規則有 3 條被拒（44 題），DeepSeek 0 條。

## 重複計時（SB、BEQ，mazu）

第 7 節的主要結論是 SB 與 BEQ 的證明數比較。對每個 LLM 規則 × 非 LLM arm 的配對，取兩者都 `UNSAT` 的前 3 個 sub-property（依抽樣順序，由 zeus 上的測試結果決定），兩個 spec 各重跑 3 次。依第 9 節，重複計時在 mazu 的 `0-3`／`4-7`／`8-11` 跑，90 個 run 全部 `UNSAT`。中位數比 = LLM 時間中位數 ÷ 對照時間中位數；`scripts/reptime.py BEQ SB`。

#### BEQ

| LLM | 對照 | sub-property | LLM 時間 s | 對照時間 s | 中位數比 |
| --- | --- | --- | --- | --- | ---: |
| DeepSeek fb4 | split (COI) | `load_en.rs1=0.rs2=0` | 5、6、5 | 56、56、55 | 0.10 |
| DeepSeek fb4 | split (COI) | `load_en.rs1=2.rs2=23` | 6、6、6 | 64、86、63 | 0.09 |
| DeepSeek fb4 | split (COI) | `load_en.rs1=5.rs2=14` | 7、7、6 | 65、58、79 | 0.10 |
| DeepSeek fb4 | S | `load_en.rs1=0.rs2=0` | 5、6、5 | 7、7、7 | 0.81 |
| DeepSeek fb4 | S | `load_en.rs1=2.rs2=23` | 6、6、6 | 6、6、6 | 0.94 |
| DeepSeek fb4 | S | `load_en.rs1=5.rs2=14` | 7、7、6 | 9、10、8 | 0.71 |
| DeepSeek fb4 | auto | `load_en.rs1=0.rs2=0` | 5、6、5 | 7、7、7 | 0.77 |
| DeepSeek fb4 | auto | `load_en.rs1=2.rs2=23` | 6、6、6 | 5、5、6 | 1.07 |
| DeepSeek fb4 | auto | `load_en.rs1=5.rs2=14` | 7、7、6 | 5、5、5 | 1.26 |
| Claude fb2 | split (COI) | `load_en.rs1=0.rs2=0` | 6、6、5 | 56、56、55 | 0.11 |
| Claude fb2 | split (COI) | `load_en.rs1=2.rs2=23` | 6、6、6 | 64、86、63 | 0.10 |
| Claude fb2 | split (COI) | `load_en.rs1=5.rs2=14` | 9、10、8 | 65、58、79 | 0.14 |
| Claude fb2 | S | `load_en.rs1=0.rs2=0` | 6、6、5 | 7、7、7 | 0.91 |
| Claude fb2 | S | `load_en.rs1=2.rs2=23` (同一 spec) | 6、6、6 | 6、6、6 | 1.00 |
| Claude fb2 | S | `load_en.rs1=5.rs2=14` (同一 spec) | 9、10、8 | 9、10、8 | 1.00 |
| Claude fb2 | auto | `load_en.rs1=0.rs2=0` | 6、6、5 | 7、7、7 | 0.86 |
| Claude fb2 | auto | `load_en.rs1=2.rs2=23` | 6、6、6 | 5、5、6 | 1.14 |
| Claude fb2 | auto | `load_en.rs1=5.rs2=14` | 9、10、8 | 5、5、5 | 1.77 |

#### SB

| LLM | 對照 | sub-property | LLM 時間 s | 對照時間 s | 中位數比 |
| --- | --- | --- | --- | --- | ---: |
| DeepSeek fb4 | split (COI) | `pc.rs1=0.rs2=0` | 28、28、28 | 131、124、135 | 0.21 |
| DeepSeek fb4 | split (COI) | `pc.rs1=0.rs2=7` | 26、24、25 | 101、102、97 | 0.25 |
| DeepSeek fb4 | split (COI) | `pc.rs1=7.rs2=17` | 23、23、23 | 107、113、110 | 0.21 |
| DeepSeek fb4 | S | `pc.rs1=0.rs2=0` | 28、28、28 | 20、21、19 | 1.38 |
| DeepSeek fb4 | S | `pc.rs1=0.rs2=7` | 26、24、25 | 29、30、32 | 0.84 |
| DeepSeek fb4 | S | `pc.rs1=2.rs2=23` | 22、22、15 | 21、22、23 | 0.97 |
| DeepSeek fb4 | auto | `pc.rs1=0.rs2=0` | 28、28、28 | 50、51、54 | 0.54 |
| DeepSeek fb4 | auto | `pc.rs1=0.rs2=7` | 26、24、25 | 34、40、40 | 0.64 |
| DeepSeek fb4 | auto | `pc.rs1=2.rs2=23` | 22、22、15 | 35、26、23 | 0.85 |
| Claude fb2 | split (COI) | `pc.rs1=0.rs2=0` | 9、17、15 | 131、124、135 | 0.11 |
| Claude fb2 | split (COI) | `pc.rs1=0.rs2=7` | 33、29、23 | 101、102、97 | 0.28 |
| Claude fb2 | split (COI) | `pc.rs1=7.rs2=17` | 16、22、24 | 107、113、110 | 0.20 |
| Claude fb2 | S | `pc.rs1=0.rs2=0` | 9、17、15 | 20、21、19 | 0.73 |
| Claude fb2 | S | `pc.rs1=0.rs2=7` | 33、29、23 | 29、30、32 | 0.95 |
| Claude fb2 | S | `pc.rs1=2.rs2=23` | 16、15、17 | 21、22、23 | 0.73 |
| Claude fb2 | auto | `pc.rs1=0.rs2=0` | 9、17、15 | 50、51、54 | 0.29 |
| Claude fb2 | auto | `pc.rs1=0.rs2=7` | 33、29、23 | 34、40、40 | 0.64 |
| Claude fb2 | auto | `pc.rs1=2.rs2=23` | 16、15、17 | 35、26、23 | 0.64 |

- 兩邊都證得出來的題目上，LLM 規則比 split 快約 4–11 倍（中位數比 0.09–0.28）。和 S、auto 相比，比值在 0.54–1.77 之間，有快有慢，不構成速度結論。
- SB 的這些題目都是 `pc`，因為 S、auto、fb4 在 `store_en` 上大多證不出來。所以重複計時**沒有涵蓋** fb2 和其他 arm 差別所在的 `store_en`。

## 執行過程

### 機器

- ADDI 訓練、規則挑選，以及 SB、BEQ、SH 的測試在 zeus 跑：2 × Xeon E5-2630 v4，9 個 CPU 組，每組 2 個實體核心加上 HT。
  - 工具：`zeus/env-20261024.sh`，rIC3 master `8c6df1b`（sha256 `90e7141b…6977`）、與 mazu 相同的 Yosys 和 venv。
  - 驗證：ADDI S 的 3 題重現已知結果（`zeus/verify-ADDI-S.jsonl`）。
- 2026-10-28 00:49 +08，依使用者指示停用 zeus（`PREREG.md` 第 9 節）：
  - 當時正在跑 XOR 的 LLM arm。zeus 上整個 run 目錄（132,652 個檔案）rsync 回 mazu，逐檔 sha256 比對全部相符。
  - 之後刪除了 zeus 上的 run 目錄和 `/var/tmp/neuroabs-tools`。
- SB、BEQ、SH 的五個 arm 都已在 zeus 跑完，所以保留 zeus 的結果。其餘 10 個指令的五個 arm 全部在 mazu 重跑：
  - 機器：i9-14900K，只用 P-core CPU 0–11，分成 `0-3`／`4-7`／`8-11` 三組；
  - 工具版本相同，重新產生的 85 個 spec 檔與 zeus 上的 sha256 相同。
  - ADD、SUB、OR、BNE 的 LLM arm 和 XOR 的部分 LLM arm 先前在 zeus 跑過，這些結果只留作紀錄，不進表格。它們的 `UNSAT` 數與 mazu 相同。
- 同一個指令的五個 arm 都在同一台機器、同一種 CPU 組上執行。

### LLM

- DeepSeek：本機閘道 `deepseek-flash`，5 次生成加上 5 次回饋。花費依 `src/deepseek_prices.py` 估算為 US$0.3101（上限 $3）；閘道回報的 `list_cost` 合計 US$0.155，由 OpenCode Go 的訂閱額度支付（`cost` 0）。全部由 `deepseek-v4.1-flash`（OpenCode Go）服務，沒有經過 OpenRouter。
- Claude：本機已登入的個人 claude.ai 帳號，`claude -p --model opus`，5 次生成加上 5 次回饋。
  - 每次呼叫的 stream-json 紀錄都是 `claude-opus-5-5`、`apiKeySource: none`（`rules/claude/*.claude.jsonl`）。
  - 沒有使用任何 API key；`PREREG.md` 原本的 API key 備援已取消，也從未觸發。
  - 帳號的每週用量在這 10 次呼叫中從 0.85 升到 0.88。
- 與預先登記的差異：Claude Code 仍會在 prompt 外附加一段系統資訊（工作目錄、平台、模型身分、日期）和使用者 email，並使用預設的 effort `medium`。這些內容不含 repo 或 S 的資訊（`docs/notes.md`）。

## 限制與風險

- **SB、SH 的勝出不穩健。** Claude fb2 在 SB、SH 上贏 S 的 18 題，來自平手時的選單順序，不是規則的判斷。#22 顯示順序反過來後，結果和 S 相同。不看 SB、SH，兩條 LLM 規則對 S 的優勢只剩 ADD 的 11 題。
- **ADD 的勝出是 S 的配對器選錯。** 配對器 `match_pairs` 在 ADD 選了 load 位址 `eaddr`。LLM 規則的名稱打分選了 `rd_val`，這不依賴順序。但名稱打分本身依賴 RTL 命名（`rd_val`、`addr`），換一個設計不一定成立。
- **候選選單是知道答案的人設計的。** `prepare.name_operands` 的改寫是因為已知 SB 的正確配對不在選單裡才加的（`PREREG.md` 1.1）；`store_en` 的拆題方式沿用 `semantic_candidates` 的 rs1×rs2 切法。
- **樣本小。** 每個指令 20 題，每個模型只挑一條規則，各 5 個樣本加一輪回饋。
- **兩台機器。** SB、BEQ、SH 在 zeus，其餘在 mazu。同一指令內的 arm 可以互相比較，跨指令比較時間沒有意義（例如 BEQ 和 BNE 的 `UNSAT` 數逐格相同，但 mazu 的時間短很多）。
- **時間大多只跑一次。** 只有 SB、BEQ 做了重複計時，而且只涵蓋兩邊都證出的題目。
- S 是看過 DeepSeek 對 ADDI 的回答才寫的，所以不是獨立的尺；本實驗也不以「與 S 一致」評分。

## 檔案

- `PREREG.md`：預先登記與第 9 節的修改。
- `prompt/`：兩個模型共用的 prompt。
- `rules/{claude,deepseek}/`：全部 20 條規則、原始回答，以及 Claude 的 stream-json 紀錄。
- `problems/<case>/`：各指令的輸入、UF 候選、S 的配對和抽樣。
- `training/`：訓練結果、挑選與回饋訊息。
- `runs/ADDI/`：訓練的 batch 與結果。
- `runs/<case>/`：
  - `<batch>.jsonl`：rIC3 結果，`test` 是 zeus、`mazu` 是 mazu；
  - `batches/<batch>.jsonl` 和 `.map.json`：每個 run 的 spec，以及 arm × sub-property 到 run 的對應；
  - SB、BEQ 另有 `rep.jsonl`，是重複計時。
- `summary.json`：`scripts/summarize.py` 的輸出。
- `scripts/`：產生題目、規則、spec、佇列、統計與表格的程式；`env.sh` 是目前的 mazu 設定。
- `zeus/`：zeus 的工具環境與驗證紀錄。
- run 目錄 `/var/tmp/neuroabs-runtime/runs/llm-heldout-20261027`（mazu）還保留了：
  - `queue-zeus/`：zeus 的佇列紀錄；
  - `runs/<case>/test/`：只留作紀錄的 zeus 結果；
  - `zeus-manifest.sha256`：複製回 mazu 時的 sha256 清單。
