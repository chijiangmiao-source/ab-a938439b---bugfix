"""任意精度整数 JSON 读写测试。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bigjson  # noqa: E402


class BigJsonTest(unittest.TestCase):
    def test_integer_tokens_keep_full_precision(self):
        for token in ["1000000000000000000", "1000000000000000000000000000000",
                      "-999999999999999999999999999999999999"]:
            v = bigjson.loads('{"x": %s}' % token)["x"]
            self.assertIsInstance(v, int)
            self.assertEqual(str(v), token.lstrip("-") if v > 0 else token)
            self.assertEqual(v, int(token))

    def test_nested_structures(self):
        v = bigjson.loads('{"a": [1, 1000000000000000001],'
                          ' "b": {"c": -%s}}' % ("1" + "0" * 30))
        self.assertEqual(v["a"][1], 1000000000000000001)
        self.assertIsInstance(v["b"]["c"], int)
        self.assertEqual(v["b"]["c"], -10 ** 30)

    def test_float_tokens_remain_float(self):
        # 浮点必须保持 float，交给字段级校验拒绝（保留 loc 定位语义）
        v = bigjson.loads('{"x": 1.5, "y": 2.0, "z": 1e3}')
        self.assertIsInstance(v["x"], float)
        self.assertIsInstance(v["y"], float)
        self.assertIsInstance(v["z"], float)

    def test_oversized_literal_rejected(self):
        with self.assertRaises(ValueError):
            bigjson.loads('{"x": 1%s}' % ("0" * 200))


if __name__ == "__main__":
    unittest.main(verbosity=2)
