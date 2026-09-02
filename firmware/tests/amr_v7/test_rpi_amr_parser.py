import importlib.util
import unittest
from pathlib import Path


def load_parser():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "firmware" / "tools" / "rpi_amr_parser.py"
    spec = importlib.util.spec_from_file_location("rpi_amr_parser", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RpiAmrParserTest(unittest.TestCase):
    def setUp(self):
        self.parser = load_parser()

    def test_calculates_checksum_for_amr_payload(self):
        payload = "CMD,STATE=SAFE,GAS=42,FLAME=0,BAT=12.00"
        self.assertEqual(self.parser.calculate_checksum(payload), 0x56)

    def test_parses_valid_amr_state_message(self):
        message = "<CMD,STATE=SAFE,GAS=42,FLAME=0,BAT=12.00,56>"
        parsed = self.parser.parse_amr_message(message)

        self.assertEqual(parsed["command"], "CMD")
        self.assertEqual(parsed["state"], "SAFE")
        self.assertEqual(parsed["gas"], 42)
        self.assertEqual(parsed["flame"], 0)
        self.assertEqual(parsed["battery"], 12.0)

    def test_rejects_bad_checksum(self):
        with self.assertRaises(ValueError):
            self.parser.parse_amr_message("<CMD,STATE=SAFE,GAS=42,FLAME=0,BAT=12.00,00>")

    def test_rejects_missing_frame(self):
        with self.assertRaises(ValueError):
            self.parser.parse_amr_message("CMD,STATE=SAFE,GAS=42,FLAME=0,BAT=12.00,56")

    def test_rejects_missing_required_field(self):
        with self.assertRaises(ValueError):
            self.parser.parse_amr_message("<CMD,STATE=SAFE,GAS=42,BAT=12.00,63>")

    def test_parses_v9_three_sensor_message(self):
        payload = "SENS,120,220,1,1200,0,0,0"
        checksum = sum(ord(char) for char in payload) % 256
        parsed = self.parser.parse_amr_message(f"<{payload},{checksum}>")

        self.assertEqual(parsed["command"], "SENS")
        self.assertEqual(parsed["mq135"], 120)
        self.assertEqual(parsed["mq2"], 220)
        self.assertEqual(parsed["flame"], 1)
        self.assertEqual(parsed["battery_centivolts"], 1200)
        self.assertEqual(parsed["state_code"], 0)
        self.assertEqual(parsed["action_code"], 0)
        self.assertEqual(parsed["fault_code"], 0)

    def test_rejects_v9_wrong_field_count(self):
        payload = "SENS,120,220,1,1200,0,0"
        checksum = sum(ord(char) for char in payload) % 256
        with self.assertRaises(ValueError):
            self.parser.parse_amr_message(f"<{payload},{checksum}>")

    def test_rejects_v9_bad_decimal_checksum(self):
        with self.assertRaises(ValueError):
            self.parser.parse_amr_message("<SENS,120,220,1,1200,0,0,0,0>")


if __name__ == "__main__":
    unittest.main()
