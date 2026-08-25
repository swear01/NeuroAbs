import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SRC = Path(__file__).resolve().parents[1] / "src"


class CegarYosysScriptTest(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(SRC))
        self.pono_env = patch.dict(os.environ, {"PONO_BIN": "/bin/true"})
        self.pono_env.start()
        sys.modules.pop("cegar", None)
        self.cegar = importlib.import_module("cegar")

    def tearDown(self):
        sys.modules.pop("cegar", None)
        self.pono_env.stop()
        sys.path.remove(str(SRC))

    def test_lowers_check_cells_before_reset_simulation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            yosys = root / "gen_btor.ys"
            verilog = root / "wrapper.v"
            yosys.write_text(
                "read_verilog -formal old.v\n"
                "proc\n"
                "sim -clock clk -resetn rstn -rstlen 1 -n 1 -w top\n"
                "write_btor -s old.btor2\n"
            )
            verilog.write_text("module top; endmodule\n")

            with patch.object(
                self.cegar.os, "getcwd", return_value=str(root)
            ), patch.object(self.cegar, "run_yosys_script") as run_yosys:
                self.cegar.run_yosys_init(str(yosys), str(verilog))

            generated = Path(run_yosys.call_args.args[0]).read_text()
            self.assertLess(
                generated.index("chformal -lower"), generated.index("sim ")
            )


if __name__ == "__main__":
    unittest.main()
