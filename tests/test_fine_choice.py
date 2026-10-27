import importlib
import sys
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"

WRAPPER = """module wrapper(clk);
assign post_value_holder__p1__ = (!(monitor_s3))||((__auxvar2__recorder)==(RTL__DOT__gpr_regfile__DOT__regfile__DOT__arr_1_)) ;
assign post_value_holder__p2__ = (!(monitor_s3))||((__auxvar3__recorder)==(RTL__DOT__gpr_regfile__DOT__regfile__DOT__arr_2_)) ;
assign variable_map_assume___p3__ = (!(__START__))||((__ILA_SO_x1)==(__auxvar2__recorder)) ;
assign variable_map_assume___p4__ = (!(__START__))||((__ILA_SO_x2)==(__auxvar3__recorder)) ;
assign noreset__p5__ = (!(__RESETED__))||(!(dummy_reset)) ;
assign variable_map_assert__p6__ = (!(__IEND__))||((__ILA_SO_pc)==(__auxvar1__recorder)) ;
assign variable_map_assert__p7__ = (!(__IEND__))||((__ILA_SO_x1)==(RTL__DOT__gpr_regfile__DOT__regfile__DOT__arr_1_)) ;
assign variable_map_assert__p8__ = (!(__IEND__))||((__ILA_SO_x2)==(RTL__DOT__gpr_regfile__DOT__regfile__DOT__arr_2_)) ;
assign __all_assert_wire__ = (variable_map_assert__p6__) && (variable_map_assert__p7__) && (variable_map_assert__p8__) ;
assign __all_assume_wire__ = (post_value_holder__p1__)&& (post_value_holder__p2__)&& (variable_map_assume___p3__)&& (variable_map_assume___p4__)&& (noreset__p5__) ;
endmodule
module other(clk);
endmodule
"""

UF_DESIGN = """module wrapper(clk);
riscv__DOT__ADDI ILA (
   .clk(clk)
);
mkCPU RTL(
    .CLK(clk)
);
assign __all_assume_wire__ = (noreset__p5__) ;
endmodule
module riscv__DOT__ADDI(
clk
);
input clk;
assign n110 =  ( n107 ) + ( n109 )  ;
assign n111 =  ( n107 ) ^ ( n109 )  ;
assign n112 =  ( n107 ) == ( n109 )  ;
endmodule
module mkCPU(CLK
);
  assign rd_val___1__h6550 =
\t     rs1_val_bypassed__h3337 + _theResult___snd__h7382 ;
endmodule
"""

UNITS = [{"id": "csr_regfile", "path": "RTL.csr_regfile", "module": "mkCSR_RegFile", "coi_state_bits": 480,
          "memories": [], "levels": ["keep", "cut"]}]


class FineChoiceTest(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(SRC))
        for name in ("fine_choice", "choice_abstraction"):
            sys.modules.pop(name, None)
        self.fine = importlib.import_module("fine_choice")

    def tearDown(self):
        for name in ("fine_choice", "choice_abstraction"):
            sys.modules.pop(name, None)
        sys.path.remove(str(SRC))

    def test_conjuncts_are_named_by_ila_state(self):
        self.assertEqual(self.fine.property_conjuncts(WRAPPER),
                         {"pc": ["variable_map_assert__p6__"], "x1": ["variable_map_assert__p7__"],
                          "x2": ["variable_map_assert__p8__"]})

    def test_recorders_map_to_registers(self):
        assigns = self.fine.read_assigns(WRAPPER)
        recorders = self.fine.recorder_map(assigns)
        self.assertEqual(recorders, {"__auxvar2__recorder": 1, "__auxvar3__recorder": 2})
        self.assertEqual(self.fine.gpr_refs(assigns["variable_map_assume___p4__"], recorders), {2})
        self.assertEqual(self.fine.gpr_refs(assigns["noreset__p5__"], recorders), set())

    def test_split_keeps_selected_asserts_and_drops_assumptions_of_removed_registers(self):
        text = self.fine.split_wrapper(WRAPPER, {"states": ["x1"], "case": "rd!=1", "keep_gprs": [1]})
        assigns = self.fine.read_assigns(text)
        self.assertEqual(assigns["__all_assert_wire__"],
                         "(!((__split_inst__[11:7] != 5'd1))) || ((variable_map_assert__p7__))")
        self.assertEqual(self.fine.conjunct_names(assigns, "assume"),
                         ["post_value_holder__p1__", "variable_map_assume___p3__", "noreset__p5__"])
        lines = text.splitlines()
        latch = lines.index("always @(posedge clk) if (__START__) __split_inst__ <= __ILA_I_inst;")
        self.assertEqual(lines[latch + 1], "endmodule")
        self.assertEqual(text.count("__split_inst__ <="), 1)

    def test_rd_guard_requires_each_register_only_when_it_is_rd(self):
        text = self.fine.split_wrapper(WRAPPER, {"states": ["pc", "x2"], "case": "rs1==1", "rd_guard": True})
        self.assertEqual(self.fine.read_assigns(text)["__all_assert_wire__"],
                         "(!((__split_inst__[19:15] == 5'd1))) || ((variable_map_assert__p6__) && "
                         "((!((__split_inst__[11:7] == 5'd2))) || (variable_map_assert__p8__)))")

    def test_split_covers_every_register_and_case(self):
        self.assertEqual(self.fine.ila_split(["x1"], [])[1:], [
            {"name": "x1.frame", "states": ["x1"], "case": "rd!=1"},
            {"name": "x1.write", "states": ["x1"], "case": "rd==1"}])
        subs = self.fine.ila_split(["pc", "x0", "x1", "x2"], ["rs1"])
        self.assertEqual(subs[0], {"name": "mem", "states": ["pc", "x0"]})
        self.assertEqual(len(subs), 1 + 2 * 33)
        self.assertEqual(subs[1], {"name": "x1.frame", "states": ["x1"], "case": "rd!=1"})
        self.assertEqual([s["case"] for s in subs[2:34]], ["rd==1&&rs1=={:d}".format(r) for r in range(32)])
        self.assertEqual(subs[2]["name"], "x1.rs1=0")

    def test_structural_keeps_the_registers_named_by_the_sub_property(self):
        ufs = [{"ila": "n110", "rtl": "r"}]
        spec = self.fine.structural({"states": ["x5"], "case": "rd==5&&rs1==6"}, UNITS, ufs)
        self.assertEqual((spec["keep_gprs"], spec["word_gprs"], spec["units"], spec["uf"]),
                         ([6], [5], {"csr_regfile": "cut"}, ufs))
        spec = self.fine.structural({"states": ["x5"], "case": "rd==5&&rs1==5"}, UNITS, ufs)
        self.assertEqual((spec["keep_gprs"], spec["word_gprs"]), ([5], []))
        spec = self.fine.structural({"states": ["x5"], "case": "rd!=5"}, UNITS, ufs)
        self.assertEqual((spec["keep_gprs"], spec["word_gprs"]), ([5], []))
        spec = self.fine.structural({"states": ["pc", "x0"]}, UNITS, ufs)
        self.assertEqual((spec["keep_gprs"], spec["word_gprs"]), ([0], []))

    def test_operand_fields_are_read_from_the_ila(self):
        design = UF_DESIGN.replace("assign n110 =", "assign n15 = inst[19:15] ;\nassign n110 =")
        self.assertEqual(self.fine.operand_fields(design), ["rs1"])
        self.assertEqual(self.fine.operand_fields(UF_DESIGN), [])

    def test_keep_all_registers_keeps_every_assumption(self):
        text = self.fine.split_wrapper(WRAPPER, {"states": ["pc", "x2"]})
        assigns = self.fine.read_assigns(text)
        self.assertEqual(assigns["__all_assert_wire__"], "(variable_map_assert__p6__) && (variable_map_assert__p8__)")
        self.assertEqual(len(self.fine.conjunct_names(assigns, "assume")), 5)

    def test_case_terms(self):
        self.assertEqual(self.fine.case_expr("rd==3&&rs1==0"),
                         "(__split_inst__[11:7] == 5'd3) && (__split_inst__[19:15] == 5'd0)")
        self.assertEqual(self.fine.case_expr("imm!=0"), "(__split_inst__[31:20] != 12'd0)")
        with self.assertRaises(ValueError):
            self.fine.case_expr("funct3==3")
        with self.assertRaises(ValueError):
            self.fine.case_expr("rd==32")

    def test_removed_words_and_ila_registers_are_cut(self):
        spec = {"states": ["x1"], "keep_gprs": list(range(1, 32))}
        lines = self.fine.word_cut_lines(spec, "sel", {})
        self.assertEqual(lines[:2], ["select *", "memory"])
        self.assertIn("cutpoint wrapper/w:RTL.gpr_regfile.regfile.arr?0?", lines)
        self.assertIn("cutpoint wrapper/w:ILA.x0", lines)
        self.assertEqual(sum(line.startswith("cutpoint") for line in lines), 2)

    def test_free_values_map_back_to_registers_and_units(self):
        self.assertEqual(self.fine.unit_of("gpr_w7", UNITS), "gpr7")
        self.assertEqual(self.fine.unit_of("ila_x7", UNITS), "gpr7")
        self.assertEqual(self.fine.unit_of("csr_regfile", UNITS), "csr_regfile")
        self.assertIsNone(self.fine.unit_of("other", UNITS))

    def test_refine_restores_the_choice_with_most_free_values(self):
        spec = {"states": ["x1"], "keep_gprs": [1], "units": {"csr_regfile": "cut"}}
        self.assertEqual(self.fine.refine(spec, UNITS, {"gpr4": 3, "csr_regfile": 1})["keep_gprs"], [1, 4])
        refined = self.fine.refine(spec, UNITS, {"gpr4": 1, "csr_regfile": 2})
        self.assertEqual(refined["units"], {"csr_regfile": "keep"})
        self.assertEqual(spec["units"], {"csr_regfile": "cut"})
        self.assertIsNone(self.fine.refine(spec, UNITS, {}))

    def test_refine_a_unit_whose_id_starts_with_gpr(self):
        units = UNITS + [{"id": "gpr_regfile_f", "path": "RTL.gpr_regfile.f", "module": "FIFO2", "coi_state_bits": 64,
                          "memories": [], "levels": ["keep", "cut"]}]
        spec = {"states": ["x1"], "keep_gprs": [1], "units": {"gpr_regfile_f": "cut"}}
        self.assertEqual(self.fine.refine(spec, units, {"gpr_regfile_f": 2})["units"], {"gpr_regfile_f": "keep"})

    def test_word_level_registers_keep_their_words(self):
        spec = {"states": ["x1"], "keep_gprs": [1], "word_gprs": [2, 3]}
        self.assertEqual(self.fine.removed_gprs(spec), [0] + list(range(4, 32)))
        text = self.fine.split_wrapper(WRAPPER, spec)
        self.assertNotIn("variable_map_assume___p4__", self.fine.conjunct_names(self.fine.read_assigns(text), "assume"))
        refined = self.fine.refine(spec, UNITS, {"gpr2": 1})
        self.assertEqual((refined["keep_gprs"], refined["word_gprs"]), ([1, 2], [3]))
        refined = self.fine.refine(spec, UNITS, {})
        self.assertEqual((refined["keep_gprs"], "word_gprs" in refined), ([1, 2, 3], False))
        refined = self.fine.refine({"states": ["x1"], "word_gprs": [2]}, UNITS, {})
        self.assertEqual((refined["keep_gprs"], "word_gprs" in refined), ("all", False))

    def test_empty_conjunctions_are_true(self):
        assigns = self.fine.read_assigns(self.fine.split_wrapper(WRAPPER.replace(
            "(post_value_holder__p1__)&& (post_value_holder__p2__)&& (variable_map_assume___p3__)&& "
            "(variable_map_assume___p4__)&& (noreset__p5__)", "(variable_map_assume___p4__)"),
            {"states": [], "keep_gprs": []}))
        self.assertEqual((assigns["__all_assert_wire__"], assigns["__all_assume_wire__"]), ("1'b1", "1'b1"))

    def test_batch_runs_errors_again(self):
        import json
        import tempfile
        from unittest import mock
        import fine_batch
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "results.jsonl"
            self.assertEqual(fine_batch.finished(str(path)), set())
            path.write_text("".join(json.dumps(r) + "\n" for r in [
                {"name": "a", "status": "UNSAT"}, {"name": "b", "status": "ERROR", "exit": 1},
                {"name": "c", "status": "TIMEOUT"}]))
            self.assertEqual(fine_batch.finished(str(path)), {"a", "c"})
            with open(path, "a") as f:
                f.write('{"name": "d", "status": "UN')
            self.assertEqual(fine_batch.finished(str(path)), {"a", "c"})
            specs = Path(d) / "specs.jsonl"
            specs.write_text(json.dumps({"name": "d", "spec": {}}) + "\n")
            with mock.patch.object(fine_batch, "check", return_value={"name": "d", "status": "UNSAT"}):
                code = fine_batch.main(["--wrapper", "w.v", "--units", "u.json", "--specs", str(specs),
                                        "--workdir", d, "--cpus", "0", "--time-limit", "1", "--max-iterations", "0"])
            self.assertEqual((code, fine_batch.finished(str(path))), (0, {"a", "c", "d"}))

    def test_batch_records_a_job_that_fails_to_run_and_goes_on(self):
        import json
        import tempfile
        from unittest import mock
        import fine_batch

        def check(name, spec, cpus, args):
            if name == "a":
                raise OSError("taskset not found")
            return {"name": name, "status": "UNSAT"}

        with tempfile.TemporaryDirectory() as d:
            specs = Path(d) / "specs.jsonl"
            specs.write_text("".join(json.dumps({"name": n, "spec": {}}) + "\n" for n in ("a", "b", "c")))
            with mock.patch.object(fine_batch, "check", side_effect=check):
                code = fine_batch.main(["--wrapper", "w.v", "--units", "u.json", "--specs", str(specs),
                                        "--workdir", d, "--cpus", "0", "--time-limit", "1", "--max-iterations", "0"])
            records = [json.loads(line) for line in (Path(d) / "results.jsonl").read_text().splitlines()]
        self.assertEqual(code, 1)
        self.assertEqual([(r["name"], r["status"]) for r in records], [("a", "ERROR"), ("b", "UNSAT"), ("c", "UNSAT")])
        self.assertIn("taskset not found", records[0]["error"])

    def test_operator_args(self):
        self.assertEqual(self.fine.operator_args(UF_DESIGN, "riscv__DOT__ADDI", "n110"), ("n107", "+", "n109"))
        self.assertEqual(self.fine.operator_args(UF_DESIGN, "mkCPU", "rd_val___1__h6550"),
                         ("rs1_val_bypassed__h3337", "+", "_theResult___snd__h7382"))
        self.assertEqual(self.fine.operator_args(UF_DESIGN, "riscv__DOT__ADDI", "n112"), ("n107", "==", "n109"))
        with self.assertRaises(ValueError):
            self.fine.operator_args(UF_DESIGN, "mkCPU", "n110")

    def test_uf_rewrite_adds_ackermann_assumption(self):
        text = self.fine.uf_rewrite(UF_DESIGN, 0, {"ila": "n110", "rtl": "rd_val___1__h6550"})
        self.assertIn("assign n110 = __uf0_w;", text)
        self.assertIn("assign rd_val___1__h6550 = __uf0_r;", text)
        self.assertIn("assign __uf0_a = n107;\nassign __uf0_b = n109;\nendmodule", text)
        self.assertIn("module riscv__DOT__ADDI(__uf0_w, __uf0_a, __uf0_b, ", text)
        self.assertIn("riscv__DOT__ADDI ILA (.__uf0_w(__uf0_w), .__uf0_a(__uf0_ila_a), .__uf0_b(__uf0_ila_b), ", text)
        self.assertIn("mkCPU RTL(.__uf0_r(__uf0_free), .__uf0_ra(__uf0_rtl_a), .__uf0_rb(__uf0_rtl_b), ", text)
        wrapper = text[:text.index("endmodule")]
        self.assertIn("wire [31:0] __uf0_free = $anyseq;", wrapper)
        self.assertIn("__uf0_lra <= __uf0_rtl_a; __uf0_lrb <= __uf0_rtl_b; __uf0_lr <= __uf0_free;", wrapper)
        self.assertIn("always @(posedge clk) if (rst) __uf0_ok <= 1'b0; else if (__START__) __uf0_ok <= 1'b1;", wrapper)
        self.assertIn("wire __uf0_assume = !(__uf0_ok && __uf0_la == __uf0_lra && __uf0_lb == __uf0_lrb) || "
                      "(__uf0_lw == __uf0_lr);", wrapper)
        self.assertIn("assign __all_assume_wire__ = (noreset__p5__) && (__uf0_assume) ;", wrapper)
        self.assertIn("assign n111 =  ( n107 ) ^ ( n109 )  ;", text)

    def test_uf_rejects_a_parameterized_instance(self):
        design = UF_DESIGN.replace("riscv__DOT__ADDI ILA (", "riscv__DOT__ADDI #(.W(32)) ILA (")
        with self.assertRaises(ValueError):
            self.fine.add_ports(design, "riscv__DOT__ADDI", "ILA", [("input", 32, "p", "p")], [], ("n110", "p"))

    def test_uf_rejects_different_operators(self):
        with self.assertRaises(ValueError):
            self.fine.uf_rewrite(UF_DESIGN, 0, {"ila": "n111", "rtl": "rd_val___1__h6550"})

    def test_uf_free_value_is_attributed_and_refined_away(self):
        self.assertEqual(self.fine.unit_of("uf0", UNITS), "uf0")
        spec = {"states": ["x1"], "keep_gprs": [1], "uf": [{"ila": "n110", "rtl": "r"}]}
        self.assertEqual(self.fine.refine(spec, UNITS, {"uf0": 2})["uf"], [])
        lines = self.fine.uf_cut_lines(spec, "sel", {})
        self.assertEqual(lines, ["select -write sel/uf0.txt wrapper/w:__uf0_free wrapper/w:__uf0_w %u %ci* t:$anyseq %i"])


if __name__ == "__main__":
    unittest.main()
