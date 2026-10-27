# 候選題目：該保留什麼不在 property 文字裡（rIC3）

2026-10-27 的狀態：在 Piccolo ADDI、LUI、AUIPC、JAL 上，結構化規則 S 至少跟 DeepSeek 一樣好，因為子 property 的名字（`xk.rs1=r`）已經點名要保留哪些 GPR（[`split_baseline`](../split_baseline/README.md)）。這份文件找的是答案不在 property 文字裡的題目，並且只用 rIC3 確認可行性。沒有呼叫 LLM，DeepSeek 花費 US$0。

## 排名與建議

每個候選都用同一組非 LLM arm 對照，規則在跑之前就寫死並 commit（見下一節「預先登記的規則」）。COI、S、auto 的數字來自預先登記的 `rules` batch；「手做配對」用的是正確的運算子配對。所有 time limit 都是 300 s，CEGAR 最多 10 次 refinement。每格是：UNSAT 數 / 樣本數（`mem` 加 5 組 (rs1, rs2)）。

| 排名 | 題目 | 只拆 = COI 規則 | S，現有切法（`mem`） | S，rs1×rs2 切法 | auto（coarsest + CEGAR） | 手做配對（S + 正確 UF） |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Piccolo SB `store_en` | 0 / 6（`mem` 和 5 組 rs1×rs2 都 TIMEOUT；(5,6) 在 1200 s 也 TIMEOUT） | `mem`：10 次 refinement 用完，沒有結論 | 0 / 5：配對器選到 load 位址加法器 `eaddr`，5–6 次 refinement 後 TIMEOUT（477–562 s） | 0 / 6：`mem` 10 次用完；5 組都在 6–10 次 refinement 後 TIMEOUT（542–743 s） | 5 / 5 UNSAT，68–103 s，0 次 refinement；(5,6) 重複 3 次是 83–85 s |
| 2 | Piccolo BEQ `pc` | 0 / 6（同上；(5,6) 在 1200 s 也 TIMEOUT） | `mem`：10 次 refinement 用完 | 5 / 5 UNSAT，125–174 s（各 1 次 refinement，把 I-cache 退回） | 0 / 6：`mem` 10 次用完；5 組都在 6 次 refinement 後 TIMEOUT（504–537 s） | 同 S，配對器找到的就是正確的比較器 |
| — | Piccolo LB | 寫入類在沒有 abstraction 的模型上就是 SAT（深度 13） | — | — | — | 不適用：property 本身不成立 |
| — | PicoRV32 riscv-formal（[`regfile_havoc`](../regfile_havoc/README.md)） | B0 103–202 s 可證 | — | — | — | regfile havoc：0.56 倍時間（重複 3 次）。只有一個 array，「沒點名的 array 都 havoc」這條規則就做得到，對 LLM 沒有空間 |
| — | Flute | B0 一小時沒有結論 | — | — | — | 沒有找到：`__IEND__` 在第 283 個 cycle 以前到不了（[`flute_piccolo_choices`](../flute_piccolo_choices/README.md)） |

auto 在 BEQ 和 SB 上的失敗方式都一樣：CEGAR 先把三個單元退回來，再把 UF 拿掉（CEX 裡 UF 的 free value 最多），最後加回 rs1、rs2 的 GPR。最終模型（2,286–2,674 bits）在 300 s TIMEOUT。這和 ADDI 上的 auto 相同（[`fine_gpr_choices`](../fine_gpr_choices/README.md)）。

建議：

1. **先做 SB `store_en`**。它是唯一一題所有預先登記的非 LLM arm（COI、S 兩種切法、auto）都證不出來，而存在一個可證的 sound abstraction 的題目。缺的那一步是「store 位址是 rs1 加 S-type 立即數，RTL 對應的是 `alu_outputs___1_addr__h5583`」，而不是 `eaddr__h5553`。這要從指令語意判斷，文字和結構化配對都給不出來。
2. **BEQ `pc` 當第二題**，只有在 LLM 要自己決定切法時才有意義。如果 rs1×rs2 切法是所有 arm 共用的前處理，預先登記的 S 就已經 5 / 5，LLM 頂多追平。它要測的是：property 只比 `pc`，LLM 能不能看出要依 rs1、rs2 拆，並保留這兩個 GPR。在現有切法上，S、auto、COI 都沒有結論。

SH、BNE 是同一題型，但沒有實測。

## 預先登記的規則

`scripts/rules.py`（commit `21dbf76`，在跑任何 rules run 之前，也在 SB／BEQ 有任何 LLM 答案之前）。它對每個 sub-property 產生三個 spec；產生的 spec 也一起 commit 在 `specs/*-rules.jsonl`：

- **COI**：保留 split-only 模型 COI 裡有 state 的每個單元和 GPR word，不加 UF。在 BEQ、SB 上，四個單元和全部 1,024 bits 的 GPR 都在 COI 裡，所以 COI 的 spec 和只拆相同（缺的單元 level 預設是 keep）。rs1×rs2 的 COI spec 因此沒有重跑，數字用只拆的 run；`mem.coi` 有實際跑。
- **S**：`fine_choice.structural`，沒有修改：保留 property 比較的 GPR 和 case 點名的 rs1、rs2，所有單元 cut，加上配對器找到的 UF。
- **auto**：`fine_choice.coarsest`（GPR 全部拿掉，單元全部 cut，加上配對器找到的 UF），再用 `fine_choice.refine` 做 CEGAR，跟 `fine_gpr_choices` 的 auto 相同。
- **結構化運算子配對器**：ILA 端找一個二元運算子節點，它有一個運算元是 GPR 讀取 mux（assignment 裡選得到 `x31`）；RTL 端找同一個運算子、且有一個運算元叫 `rs1_val*` 或 `rs2_val*` 的節點。有多個候選時，選另一個運算元名字像立即數（`SEXT` 或 `imm`）的那個，否則選原始碼裡的第一個。結果：BEQ 是 `n166`／`…_d216`，SB 是 `n110`／`eaddr__h5553`。

要誠實說明：這些規則雖然是在 LLM 之前寫死的，但**不是在這份 PR 的 rIC3 screen 之前**。寫配對器時，我已經知道 SB 的正確配對因為運算元是 concat，`operator_args` 解析不了；也知道 `eaddr` 配對會 TIMEOUT（`SB/eaddr` screen）。配對器的 tie-break 規則也是在這之後定的。不過，就算改成能解析 concat 的配對器，`h5583` 的另一個運算元是 concat、不含 `SEXT`／`imm`，依同一個 tie-break 還是會選 `eaddr`。下一步的 LLM 實驗要用這個 commit 的 `rules.py`，不能再改。

## 現有切法為什麼讓 S 失敗

`fine_choice.py split` 把 ILA property 拆成 `mem`（所有不是 x1..x31 的 conjunct）和每個 GPR 的 frame／寫入 case。BEQ 和 SB 不寫 rd，所以整個 property 只有 `mem` 這一類：BEQ 是 `pc`、`load_en`、`store_en`，SB 是 `pc`、`store_en`（4 個 conjunct：位址、資料、enable、size）。這些 conjunct 裡沒有任何 `xk`，S 因此一個 GPR 都不留（`keep_gprs = []`）。結果 CEGAR 拿到的每個 CEX 都是 spurious：它先把 I-cache、D-cache、CSR 退回來，再一次加一個 GPR，10 次用完時模型已經回到 2,739 bits，還是沒有結論（BEQ `pc.S`、`mem.S`，SB `store_en.S`）。

如果反過來，照 COI 把 GPR 全部留下，也證不出來：BEQ `pc` 保留全部 GPR、cut CSR 和 D-cache 會 TIMEOUT；再加上比較器 UF（`pc.allgpr.cd.uf`）還是 TIMEOUT。跟 ADDI 一樣，UF 要搭配「依 rs1、rs2 拆」才有用。

## 難點在哪（診斷 screen）

| 題目 | Abstraction（CSR、D-cache cut，I-cache 保留） | 結果 | 說明 |
| --- | --- | --- | --- |
| BEQ `pc`，rs1 = rs2 = 0 | 保留 {0} | UNSAT 33 s | 一定跳，比較器的結果是常數 |
| BEQ `pc`，rs1 = rs2 = 5 | 保留 {5} | UNSAT 47 s | 同一個暫存器比較，一定成立 |
| BEQ `pc`，rs1 = 5、rs2 = 0 | 保留 {0, 5} | TIMEOUT | 跟常數 0 比較也不行 |
| BEQ `pc`，rs1 = 5、rs2 = 6 | 保留 {5, 6} | TIMEOUT（BMC 65，IC3 frame 10） | |
| BEQ `pc`，rs1 = 5、rs2 = 6 | 保留 {5, 6} + 比較器 UF | UNSAT 129 s | |
| SB `store_en`，rs1 = 0、rs2 = 6 | 保留 {0, 6} | UNSAT 80 s | 位址就是立即數，不用加法 |
| SB `store_en`，rs1 = 5、rs2 = 6 | 保留 {5, 6} | TIMEOUT | |
| SB `store_en`，rs1 = 5、rs2 = 6 | 保留 {5, 6} + 位址加法器 UF | UNSAT 148 s | |

結論：control 和 pc 加法器都不是障礙，障礙是兩個不同 GPR 值之間的關係。BEQ 卡在比較器 `x[rs1] == x[rs2]`，SB 卡在位址 `x[rs1] + imm`。原因跟 ADDI 相同：ILA 在 `__START__` 讀 recorder，而 recorder 要到 stage 3 才和 RTL 的 `arr_j` 對上；RTL 則在 stage 1 讀 bypass 後的值。把運算子換成 UF 以後，IC3 需要的 lemma 都只是 latched word 之間的相等。

## 運算子 UF 的配對

| 題目 | ILA 節點 | RTL 節點 | 結構化配對（同一個運算子，運算元是 `rs*_val*`） |
| --- | --- | --- | --- |
| BEQ | `n166 = n102 == n165` | `IF_near_mem_imem_instr__59_BITS_19_TO_15_60_EQ_ETC___d216 = rs1_val_bypassed__h3337 == rs2_val__h5339` | 找得到，`==` 只有這一個候選 |
| SB | `n110 = n105 + n109`（S-type 立即數） | `alu_outputs___1_addr__h5583 = rs1_val_bypassed__h3337 + {sext S-imm}` | 找不到：它的第二個運算元是 concat。配對器會選到 `eaddr__h5553`（load 位址，I-type 立即數） |

為了讓 `operator_args` 接受 SB 的配對，`scripts/sb_named_imm.py` 把 concat 宣告成 wire `store_imm__uf`，產生 `piccolo-SB-named/wrapper.v`。這只是替子表達式命名，model 的行為不變。SB 的 `s4`、`long`、`rep`、`s3` 都用這個 wrapper（只拆的 run 也一樣）；`s1`、`s2`、`eaddr` 用 repo 原本的 wrapper。

`src/fine_choice.py` 的 `operator_args` 現在也接受 `==`。UF 的 free value 是 32 bits，賦值給 1-bit 節點時取最低位。這仍然 sound：在任何 concrete trace 中，讓兩個 free value 都取真結果的零擴展，Ackermann assumption 就成立。

錯配對的對照（`SB/eaddr`）：S 加上 `eaddr` 的 UF，前 6 個模型都是 SAT。CEGAR 依序退回 I-cache、D-cache、CSR，再加回 GPR 31、19，最後把 UF 也拿掉；第 7 個模型（2,480 bits）在 300 s TIMEOUT，總共 546 s。正確配對則是 0 次 refinement、68–85 s。

## 樣本結果

5 組 (rs1, rs2)：(5,6)、(12,3)、(31,1)、(20,9)、(7,26)。只拆的 time limit 是 300 s，(5,6) 另外跑 1200 s。「S+uf」是：保留 {rs1, rs2}、三個單元都 cut、加上 UF，CEGAR 最多 10 次（就是 S 規則加上正確的 UF 配對）。

| 題目 | 只拆 UNSAT | 只拆 1200 s（5,6） | S+uf UNSAT | S+uf 時間 s | refinement | COI bits 只拆 / S+uf |
| --- | ---: | --- | ---: | --- | ---: | --- |
| BEQ `pc` | 0 / 5 | TIMEOUT（BMC 130，IC3 frame 10） | 5 / 5 | 134、151、181、185、186 | 每條 1（I-cache） | 5,163 / 1,484 |
| SB `store_en` | 0 / 5 | TIMEOUT（BMC 40，IC3 frame 11） | 5 / 5 | 68、76、94、95、103 | 0 | 5,163 / 1,078 |

重複計時：(5,6) 的 S+uf 在同一組 CPU 上連跑 3 次。BEQ 是 145、146、145 s，SB 是 85、83、84 s，都是 UNSAT。只拆這邊沒有能比較的時間（全部 TIMEOUT），所以這裡的結論是「能證／不能證」，不是加速倍數。

全部 52 筆 screen 紀錄（不含預先登記的 `rules` batch，它在後面另列）（`scripts/table.py` 產生；BMC／IC3 是最後一個 rIC3 run 的最深 bound 和 frame）：

| Case | Batch | Sub-property / arm | Status | Ref. | Time s | rIC3 s | Final COI bits | BMC / IC3 (last) | CEX depths |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| BEQ | long | `pc.rs1=5.rs2=6.split` | TIMEOUT | 0 | 1208 | 1206 | 5,163 | 130 / 10 | - |
| BEQ | rep | `pc.rs1=5.rs2=6.S+uf.r1` | UNSAT | 1 | 145 | 130 | 1,484 | 30 / 14 | 8 |
| BEQ | rep | `pc.rs1=5.rs2=6.S+uf.r2` | UNSAT | 1 | 146 | 130 | 1,484 | 30 / 14 | 8 |
| BEQ | rep | `pc.rs1=5.rs2=6.S+uf.r3` | UNSAT | 1 | 145 | 130 | 1,484 | 30 / 14 | 8 |
| BEQ | s1 | `load_en.split` | UNSAT | 0 | 108 | 104 | 5,131 | 24 / 10 | - |
| BEQ | s1 | `store_en.split` | UNSAT | 0 | 125 | 121 | 5,131 | 28 / 13 | - |
| BEQ | s1 | `pc.split` | TIMEOUT | 0 | 312 | 309 | 5,131 | 11 / 10 | - |
| BEQ | s1 | `pc.allgpr.cd` | TIMEOUT | 0 | 309 | 304 | 4,136 | 11 / 10 | - |
| BEQ | s1 | `mem.S` | max_iterations | 10 | 465 | 375 | 2,739 | 10 / 6 | 8,11,13,11,11,11,11,11,11,11,11 |
| BEQ | s1 | `pc.S` | max_iterations | 10 | 462 | 371 | 2,739 | 10 / 7 | 8,11,11,13,11,11,11,11,11,11,11 |
| BEQ | s1 | `pc.rs1=5.rs2=6.split` | TIMEOUT | 0 | 312 | 308 | 5,163 | 30 / 10 | - |
| BEQ | s1 | `pc.rs1=5.rs2=6.keep56.cd` | TIMEOUT | 0 | 310 | 303 | 1,291 | 65 / 10 | - |
| BEQ | s2 | `pc.rs1=0.rs2=0.keep0.cd` | UNSAT | 0 | 33 | 26 | 1,161 | 15 / 10 | - |
| BEQ | s2 | `pc.rs1=5.rs2=5.keep5.cd` | UNSAT | 0 | 47 | 40 | 1,194 | 20 / 12 | - |
| BEQ | s2 | `pc.rs1=5.rs2=0.keep5.cd` | TIMEOUT | 0 | 309 | 302 | 1,258 | 67 / 10 | - |
| BEQ | s3 | `pc.rs1=5.rs2=6.keep56.cd.uf` | UNSAT | 0 | 129 | 122 | 1,484 | 30 / 14 | - |
| BEQ | s3 | `pc.rs1=12.rs2=3.keep.cd.uf` | UNSAT | 0 | 148 | 141 | 1,484 | 40 / 17 | - |
| BEQ | s3 | `pc.rs1=5.rs2=6.S+uf` | UNSAT | 1 | 151 | 134 | 1,484 | 30 / 14 | 8 |
| BEQ | s3 | `pc.allgpr.cd.uf` | TIMEOUT | 0 | 310 | 305 | 4,329 | 20 / 10 | - |
| BEQ | s4 | `pc.rs1=12.rs2=3.S+uf` | UNSAT | 1 | 186 | 170 | 1,484 | 65 / 17 | 8 |
| BEQ | s4 | `pc.rs1=12.rs2=3.split` | TIMEOUT | 0 | 312 | 308 | 5,163 | 20 / 10 | - |
| BEQ | s4 | `pc.rs1=31.rs2=1.split` | TIMEOUT | 0 | 314 | 310 | 5,163 | 30 / 10 | - |
| BEQ | s4 | `pc.rs1=31.rs2=1.S+uf` | UNSAT | 1 | 185 | 165 | 1,484 | 65 / 16 | 8 |
| BEQ | s4 | `pc.rs1=20.rs2=9.S+uf` | UNSAT | 1 | 134 | 116 | 1,484 | 30 / 10 | 8 |
| BEQ | s4 | `pc.rs1=20.rs2=9.split` | TIMEOUT | 0 | 314 | 310 | 5,163 | 30 / 10 | - |
| BEQ | s4 | `pc.rs1=7.rs2=26.S+uf` | UNSAT | 1 | 181 | 162 | 1,484 | 40 / 11 | 8 |
| BEQ | s4 | `pc.rs1=7.rs2=26.split` | TIMEOUT | 0 | 314 | 310 | 5,163 | 30 / 10 | - |
| LB | s1 | `x5.rs1=6.split` | real | 0 | 103 | 99 | 5,163 | 12 / 8 | 13 |
| LB | s1 | `load_en.split` | TIMEOUT | 0 | 313 | 309 | 5,131 | 14 / 10 | - |
| LB | s1 | `x5.rs1=6.S` | max_iterations | 10 | 509 | 416 | 2,964 | 12 / 7 | 9,11,13,13,13,13,13,17,13,13,13 |
| LB | s1 | `load_en.S` | max_iterations | 10 | 393 | 317 | 2,739 | 10 / 8 | 8,11,11,11,11,11,11,11,11,11,11 |
| SB-named | long | `store_en.rs1=5.rs2=6.split` | TIMEOUT | 0 | 1207 | 1205 | 5,163 | 40 / 11 | - |
| SB-named | rep | `store_en.rs1=5.rs2=6.S+uf.r1` | UNSAT | 0 | 85 | 78 | 1,078 | 20 / 8 | - |
| SB-named | rep | `store_en.rs1=5.rs2=6.S+uf.r2` | UNSAT | 0 | 83 | 77 | 1,078 | 20 / 9 | - |
| SB-named | rep | `store_en.rs1=5.rs2=6.S+uf.r3` | UNSAT | 0 | 84 | 77 | 1,078 | 20 / 10 | - |
| SB-named | s3 | `store_en.rs1=5.rs2=6.S+uf` | UNSAT | 0 | 68 | 64 | 1,078 | 20 / 8 | - |
| SB-named | s3 | `store_en.rs1=5.rs2=6.keep56.cd.uf` | UNSAT | 0 | 148 | 140 | 1,484 | 20 / 15 | - |
| SB-named | s4 | `store_en.rs1=12.rs2=3.S+uf` | UNSAT | 0 | 76 | 68 | 1,078 | 14 / 8 | - |
| SB-named | s4 | `store_en.rs1=31.rs2=1.S+uf` | UNSAT | 0 | 94 | 84 | 1,078 | 20 / 8 | - |
| SB-named | s4 | `store_en.rs1=31.rs2=1.split` | TIMEOUT | 0 | 313 | 309 | 5,163 | 20 / 11 | - |
| SB-named | s4 | `store_en.rs1=12.rs2=3.split` | TIMEOUT | 0 | 315 | 311 | 5,163 | 20 / 11 | - |
| SB-named | s4 | `store_en.rs1=20.rs2=9.S+uf` | UNSAT | 0 | 103 | 94 | 1,078 | 20 / 9 | - |
| SB-named | s4 | `store_en.rs1=20.rs2=9.split` | TIMEOUT | 0 | 315 | 310 | 5,163 | 20 / 11 | - |
| SB-named | s4 | `store_en.rs1=7.rs2=26.S+uf` | UNSAT | 0 | 95 | 86 | 1,078 | 20 / 12 | - |
| SB-named | s4 | `store_en.rs1=7.rs2=26.split` | TIMEOUT | 0 | 313 | 309 | 5,163 | 20 / 11 | - |
| SB | eaddr | `store_en.rs1=5.rs2=6.S+uf-eaddr` | TIMEOUT | 6 | 546 | 487 | 2,480 | 30 / 11 | 8,12,12,12,12,12 |
| SB | s1 | `store_en.split` | TIMEOUT | 0 | 311 | 308 | 5,131 | 13 / 11 | - |
| SB | s1 | `store_en.S` | max_iterations | 10 | 478 | 387 | 2,739 | 11 / 7 | 8,11,12,12,12,12,12,12,12,12,12 |
| SB | s1 | `pc.split` | UNSAT | 0 | 266 | 262 | 5,131 | 30 / 24 | - |
| SB | s2 | `store_en.rs1=0.rs2=6.keep6.cd` | UNSAT | 0 | 80 | 73 | 1,258 | 20 / 13 | - |
| SB | s2 | `store_en.rs1=5.rs2=6.keep56.cd` | TIMEOUT | 0 | 310 | 303 | 1,291 | 30 / 10 | - |
| SB | s2 | `store_en.rs1=5.rs2=6.split` | TIMEOUT | 0 | 311 | 308 | 5,163 | 22 / 11 | - |

預先登記的 `rules` batch（26 筆）：

| Case | Batch | Sub-property / arm | Status | Ref. | Time s | rIC3 s | Final COI bits | BMC / IC3 (last) | CEX depths |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| BEQ | rules | `mem.coi` | TIMEOUT | 0 | 311 | 307 | 5,131 | 11 / 10 | - |
| BEQ | rules | `mem.S` | max_iterations | 10 | 436 | 351 | 2,642 | 10 / 7 | 8,11,11,11,11,11,11,11,11,11,11 |
| BEQ | rules | `mem.auto` | max_iterations | 10 | 442 | 356 | 2,642 | 10 / 7 | 9,11,11,11,11,11,11,11,11,11,11 |
| BEQ | rules | `pc.rs1=5.rs2=6.S` | UNSAT | 1 | 134 | 120 | 1,484 | 30 / 14 | 8 |
| BEQ | rules | `pc.rs1=12.rs2=3.S` | UNSAT | 1 | 150 | 136 | 1,484 | 65 / 16 | 8 |
| BEQ | rules | `pc.rs1=31.rs2=1.S` | UNSAT | 1 | 159 | 145 | 1,484 | 65 / 16 | 8 |
| BEQ | rules | `pc.rs1=5.rs2=6.auto` | TIMEOUT | 6 | 505 | 453 | 2,286 | 65 / 10 | 8,11,11,11,11,11 |
| BEQ | rules | `pc.rs1=12.rs2=3.auto` | TIMEOUT | 6 | 504 | 453 | 2,286 | 65 / 10 | 8,11,11,11,11,11 |
| BEQ | rules | `pc.rs1=20.rs2=9.S` | UNSAT | 1 | 125 | 109 | 1,484 | 30 / 11 | 8 |
| BEQ | rules | `pc.rs1=7.rs2=26.S` | UNSAT | 1 | 174 | 157 | 1,484 | 40 / 11 | 8 |
| BEQ | rules | `pc.rs1=31.rs2=1.auto` | TIMEOUT | 6 | 534 | 470 | 2,286 | 40 / 10 | 8,11,12,11,11,11 |
| BEQ | rules | `pc.rs1=20.rs2=9.auto` | TIMEOUT | 6 | 532 | 469 | 2,286 | 40 / 10 | 8,11,13,11,11,11 |
| BEQ | rules | `pc.rs1=7.rs2=26.auto` | TIMEOUT | 6 | 537 | 471 | 2,286 | 65 / 10 | 8,17,11,11,11,11 |
| SB | rules | `mem.coi` | TIMEOUT | 0 | 312 | 308 | 5,131 | 14 / 11 | - |
| SB | rules | `mem.auto` | max_iterations | 10 | 448 | 368 | 2,642 | 11 / 7 | 9,11,12,12,12,12,12,12,12,12,12 |
| SB | rules | `mem.S` | max_iterations | 10 | 448 | 369 | 2,642 | 11 / 6 | 9,11,12,12,12,12,15,12,12,12,12 |
| SB | rules | `store_en.rs1=5.rs2=6.S` | TIMEOUT | 6 | 526 | 474 | 2,480 | 30 / 11 | 8,12,12,12,12,12 |
| SB | rules | `store_en.rs1=12.rs2=3.S` | TIMEOUT | 6 | 526 | 474 | 2,480 | 25 / 11 | 8,11,12,12,12,12 |
| SB | rules | `store_en.rs1=5.rs2=6.auto` | TIMEOUT | 9 | 667 | 588 | 2,577 | 25 / 11 | 8,12,12,12,12,12,12,12,12 |
| SB | rules | `store_en.rs1=12.rs2=3.auto` | TIMEOUT | 8 | 649 | 569 | 2,480 | 25 / 11 | 8,11,12,12,12,12,12,12 |
| SB | rules | `store_en.rs1=31.rs2=1.S` | TIMEOUT | 6 | 562 | 500 | 2,480 | 24 / 11 | 10,11,12,12,12,12 |
| SB | rules | `store_en.rs1=31.rs2=1.auto` | TIMEOUT | 6 | 542 | 477 | 2,286 | 25 / 11 | 8,11,12,12,12,14 |
| SB | rules | `store_en.rs1=20.rs2=9.S` | TIMEOUT | 5 | 477 | 433 | 2,383 | 30 / 11 | 9,11,12,12,15 |
| SB | rules | `store_en.rs1=7.rs2=26.S` | TIMEOUT | 6 | 538 | 481 | 2,480 | 30 / 11 | 8,11,12,12,12,13 |
| SB | rules | `store_en.rs1=20.rs2=9.auto` | TIMEOUT | 10 | 743 | 650 | 2,674 | 25 / 11 | 8,11,12,12,12,12,12,12,12,12 |
| SB | rules | `store_en.rs1=7.rs2=26.auto` | TIMEOUT | 8 | 585 | 524 | 2,480 | 30 / 11 | 8,11,12,12,12,12,12,12 |

名稱裡的 `keep…` 後綴只是標籤，不一定是完整的保留集合。例如 `pc.rs1=5.rs2=0.keep5.cd` 實際保留 {0, 5}，`pc.rs1=12.rs2=3.keep.cd.uf` 保留 {3, 12}。完整集合在 spec 的 `keep_gprs`，也列在上面的診斷表。

`real` 表示 CEX 裡沒有任何 choice 的 free value，也沒有可退回的 word-level GPR，所以是真反例。`max_iterations` 表示 10 次 refinement 都用完，最後一個模型仍是 SAT。

## 對 LLM 對照實驗設計的影響

- 在這些題目上，規則 S 輸的不是「該留哪個 GPR」本身，而是現有切法沒有替非 GPR 的 conjunct 依 rs1、rs2 拆 case。一旦拆了，case 名字（`rs1==5&&rs2==6`）就又寫出答案，S 加上正確的 UF 就能 5 / 5。所以給 LLM 的選單要包含「這個 conjunct 要不要依哪些欄位拆」。如果把拆法當成所有 arm 共用的前處理，BEQ 就會回到「從文字讀得出來」。
- 比預先登記的 S 更強的結構化規則也可能找到 GPR 依賴：例如在 ILA 端算 conjunct 的 COI，看它經過哪些 `inst[19:15]`／`inst[24:20]` 的 mux。這條規則沒有預先登記。如果要加進對照，必須在看到任何 LLM 答案之前 commit，跟 `rules.py` 一樣。
- UF 配對是 SB 上 LLM 真正有空間的地方：預先登記的配對器選錯，後果是 S 0 / 5、auto 0 / 6。BEQ 的配對用配對器就找得到。
- 更省的拆法（還沒測）：SB 的 `store_addr` 只依賴 rs1、`store_data` 只依賴 rs2；如果能按 conjunct 分開拆，每題只要 32 + 32 個 case，不必 1,024 個。這需要 `split_wrapper` 能依 conjunct 選，而不是依 ILA state 選。

## 環境

Mazu（i9-14900K），Yosys 0.68+120，rIC3 master `8c6df1b`（SHA-256 `90e7141b…6977`），default portfolio，`--cex`。每個模型用 `taskset` 跑在兩個 logical CPU 上：

- E-core 16–31：s1、s2、s4、rep、eaddr，以及 s3 的 BEQ。
- s3 的 SB 兩條：E 30–31 或 P 12–13，沒有記錄是哪一條在哪組。
- long：P 12–13（BEQ）、14–15（SB）。
- rules：E 20–25（BEQ）、26–31（SB），10:46–11:30。

另一個 session 從 10:58 起在 P-core 12–15 上跑 LLM 規則 pilot（`llm-rule-20261027`）。它和 `rules` batch 用不同的 CPU。`rules` 期間的 1 分鐘 load average 是 0.3–109（`rules-loadavg.log`，每分鐘一筆）。load 偏高是因為每個 rIC3 portfolio 約有 17 個 thread，全都綁在 2 個 CPU 上，所以 load 不代表 CPU 被搶。但記憶體頻寬和 cache 是共用的，`rules` 和 `rep` 之間的時間只能大致比較。

最多 8 個 run 同時跑。機器上還有別的 session，但大多閒置。時間包含兩次 Yosys build 和 witness replay。`units.json` 是從 `fine-gpr-20261026/piccolo-ADDI` 複製來的：BEQ、SB、LB 的單元 instance 和 level 都一樣，只有 `coi_state_bits` 這個資訊欄位可能略有不同。

## 重現

Run dir 是 `/var/tmp/neuroabs-runtime/runs/semantic-cand-20261027`（在 Mazu 上，不保證保留）。每個腳本都會 source `/var/tmp/neuroabs-runtime/env-20261024.sh`。

```bash
S=results/semantic_candidates/scripts
RUN=/var/tmp/neuroabs-runtime/runs/semantic-cand-20261027
mkdir -p $RUN/specs
for c in BEQ SB LB; do mkdir -p $RUN/piccolo-$c; cp /var/tmp/neuroabs-runtime/runs/fine-gpr-20261026/piccolo-ADDI/units.json $RUN/piccolo-$c/; done
mkdir -p $RUN/piccolo-SB-named && cp $RUN/piccolo-SB/units.json $RUN/piccolo-SB-named/
python3 $S/sb_named_imm.py Piccolo_verification_done/SB/wrapper.v $RUN/piccolo-SB-named/wrapper.v
for s in s1 s2 s3 s4 s5; do python3 $S/specs_$s.py $RUN/specs; done
$S/batch.sh BEQ s1 $RUN/specs/BEQ-s1.jsonl 16-17/18-19/20-21/22-23 300 10
$S/batch.sh SB  s1 $RUN/specs/SB-s1.jsonl 24-25/26-27 300 10
$S/batch.sh LB  s1 $RUN/specs/LB-s1.jsonl 28-29/30-31 300 10
$S/batch.sh BEQ s2 $RUN/specs/BEQ-s2.jsonl 16-17/18-19/20-21 300 0
$S/batch.sh SB  s2 $RUN/specs/SB-s2.jsonl 22-23/24-25/26-27 300 0
$S/batch.sh BEQ s3 $RUN/specs/BEQ-s3.jsonl 16-17/18-19/28-29 300 10
$S/batch.sh SB-named s3 $RUN/specs/SB-named-s3.jsonl 30-31/12-13 300 10
$S/batch.sh BEQ s4 $RUN/specs/BEQ-s4.jsonl 20-21/22-23/24-25 300 10
$S/batch.sh SB-named s4 $RUN/specs/SB-named-s4.jsonl 26-27/28-29/30-31 300 10
$S/batch.sh BEQ long $RUN/specs/BEQ-long.jsonl 12-13 1200 0
$S/batch.sh SB-named long $RUN/specs/SB-named-long.jsonl 14-15 1200 0
$S/batch.sh BEQ rep $RUN/specs/BEQ-rep.jsonl 28-29 300 10
$S/batch.sh SB-named rep $RUN/specs/SB-named-rep.jsonl 26-27 300 10
$S/batch.sh SB eaddr $RUN/specs/SB-eaddr.jsonl 30-31 300 10
mkdir -p $RUN/rules
python3 $S/rules.py BEQ Piccolo_verification_done/BEQ/wrapper.v $RUN/piccolo-BEQ/units.json $RUN/piccolo-BEQ/s4/pc.rs1=12.rs2=3.split/iter0/model.btor2 $RUN/rules/BEQ.jsonl
python3 $S/rules.py SB Piccolo_verification_done/SB/wrapper.v $RUN/piccolo-SB/units.json $RUN/piccolo-SB/s1/store_en.split/iter0/model.btor2 $RUN/rules/SB.jsonl
# rules/<case>-run.jsonl = rules/<case>.jsonl without the rs1×rs2 .coi lines (identical to the split specs)
$S/batch.sh BEQ rules $RUN/rules/BEQ-run.jsonl 20-21/22-23/24-25 300 10
$S/batch.sh SB rules $RUN/rules/SB-run.jsonl 26-27/28-29/30-31 300 10
python3 $S/table.py $RUN
```

紀錄（每個子 property 一行）放在 `piccolo/<case>/<batch>.jsonl`，specs 在 `specs/`，每個模型的 SHA-256 在 `model-sha256.txt`。s2 跑的時候我改了 `batch.sh`，bash 會邊跑邊讀腳本，所以 s2 最後的 `cp`／`.done` 沒有執行，留下 `s2.failed`。但 6 筆紀錄都完整寫進了 `results.jsonl`，`s2.jsonl` 是事後手動拷的（`piccolo/*/s2.note`）。沒有任何 `ERROR` 紀錄。`rules` batch 跑的時候，`batch.sh` 的 EXIT trap 有一個 bug：它在函式裡用了 `$2`，而那是函式自己的參數（空的），所以沒有把紀錄拷出來。26 筆紀錄都完整寫進了 `results.jsonl`，`rules.jsonl` 是手動拷的。之後修正為先存成 `b=$2`，並用一個空的 batch 測過。

## 沒做的與風險

- 每題只有 5 組 (rs1, rs2) 樣本，加上 rs1 = rs2、rs1 = 0 的診斷。完整的 BEQ `pc`、SB `store_en` 各要 1,024 個 case，照樣本時間估計約 40 和 25 小時的兩-CPU 時間。
- 只拆在 1200 s 只跑了 (5,6) 一條，其他只拆的 case 都是 300 s。
- 沒有跑 SH、BNE。它們的 conjunct 和 SB、BEQ 相同，但沒有實測。
- 預先登記的規則是在 LLM 之前，但在這份 PR 的 screen 之後寫的（見「預先登記的規則」），所以配對器的定義可能偏向對 SB 不利。更強的 ILA-COI 規則沒有實作。
- auto 和 S 各只跑了一次，沒有重複計時；它們的結論是「證不出／證得出」，不是時間比。
- SB 的 RTL 配對需要先把 concat 命名成 wire。如果 LLM 選單只列出 `operator_args` 認得的節點，正確配對根本不會出現在選單裡。
