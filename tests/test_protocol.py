import unittest
from protocol import parse_line, validate

class TestProtocol(unittest.TestCase):
    def test_valid(self):
        ok, payload = parse_line('{"action":"deposit","account":"A1001","amount":10}')
        self.assertTrue(ok)
        self.assertEqual(payload["action"], "deposit")
        self.assertEqual(payload["amount"], 10)

    def test_missing_amount(self):
        ok, err = parse_line('{"action":"withdraw","account":"A1001"}')
        self.assertFalse(ok)
        self.assertEqual(err[0], "MISSING_FIELD")

    def test_invalid_amount(self):
        for amt in [-5, 0, "abc"]:
            ok, err = parse_line(f'{{"action":"deposit","account":"A1001","amount":{repr(amt) if not isinstance(amt,str) else chr(34)+amt+chr(34)}}}')
            self.assertFalse(ok)

    def test_malformed(self):
        ok, err = parse_line("not json")
        self.assertFalse(ok)
        self.assertEqual(err[0], "MALFORMED")

    def test_unknown_action(self):
        ok, err = parse_line('{"action":"transfer","account":"A1001","amount":5}')
        self.assertFalse(ok)
        # transfer not implemented as action; treated unsupported
        self.assertEqual(err[0], "UNSUPPORTED_ACTION")

if __name__ == "__main__":
    unittest.main()
