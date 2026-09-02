import importlib.util
import unittest
from pathlib import Path


def load_keepalive_tool():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "firmware" / "tools" / "rpi_keepalive.py"
    spec = importlib.util.spec_from_file_location("rpi_keepalive", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RpiKeepaliveToolTest(unittest.TestCase):
    def setUp(self):
        self.tool = load_keepalive_tool()

    def test_calculates_decimal_sum_checksum_for_v9_ping_payload(self):
        self.assertEqual(self.tool.calculate_checksum("CMD,PING"), 46)

    def test_builds_v9_framed_ping_message_with_newline(self):
        self.assertEqual(self.tool.build_message("CMD,PING"), "<CMD,PING,46>\n")

    def test_builds_explicit_legacy_v7_ping_message(self):
        self.assertEqual(
            self.tool.build_legacy_v7_message("CMD,PING"),
            "<CMD,PING,76>\n",
        )

    def test_rejects_invalid_interval(self):
        with self.assertRaises(ValueError):
            self.tool.validate_interval(0)

    def test_dry_run_returns_messages_without_serial_dependency(self):
        messages = self.tool.run_keepalive(
            port=None,
            interval_sec=1.0,
            count=2,
            dry_run=True,
            sleep_func=lambda _seconds: None,
        )

        self.assertEqual(messages, ["<CMD,PING,46>\n", "<CMD,PING,46>\n"])

    def test_reads_all_available_serial_lines(self):
        class FakeSerialInput:
            def __init__(self, lines):
                self.lines = [line.encode("utf-8") for line in lines]

            @property
            def in_waiting(self):
                return len(self.lines)

            def readline(self):
                return self.lines.pop(0)

        fake = FakeSerialInput(
            [
                "AMR_state_v9 start\n",
                "<SENS,1,2,0,1200,0,0,0,1>\n",
            ]
        )

        self.assertEqual(
            self.tool.read_available_lines(fake),
            [
                "AMR_state_v9 start",
                "<SENS,1,2,0,1200,0,0,0,1>",
            ],
        )


if __name__ == "__main__":
    unittest.main()
