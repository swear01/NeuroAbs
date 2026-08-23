import sys
import tempfile
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from extract_signal import get_signal


class ExtractSignalTest(unittest.TestCase):
    def test_extracts_named_removed_wires_for_prefix(self):
        log = """\
6.7. Executing OPT_CLEAN pass (remove unused cells and wires).
  removing unused non-port wire \\RTL.shared.
  removing unused non-port wire \\RTL.byte_controller.only_constant.
  removing unused non-port wire \\RTL.$internal.
  removing unused non-port wire \\OTHER.ignore.
  removing unused non-port wire \\RTL.shared.
"""
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "yosys.log"
            output = Path(directory) / "signals.txt"
            source.write_text(log)

            get_signal(source, output, "RTL")

            self.assertEqual(
                output.read_text().splitlines(),
                ["\\RTL.byte_controller.only_constant", "\\RTL.shared"],
            )


if __name__ == "__main__":
    unittest.main()
