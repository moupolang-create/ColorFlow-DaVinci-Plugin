import os
import re
import unittest

import zstandard

from ColorFlowLib import features


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(
    ROOT, "assets", "node-templates", "ColorFlow_5node_default.drx"
)


class BundledTemplateTest(unittest.TestCase):
    def test_default_template_has_five_named_nodes(self):
        self.assertTrue(os.path.isfile(TEMPLATE))
        with open(TEMPLATE, "rb") as handle:
            data = handle.read()
        match = re.search(rb"<Body>([0-9a-fA-F]+)</Body>", data)
        self.assertIsNotNone(match)
        raw = bytes.fromhex(match.group(1).decode("ascii"))
        body = zstandard.ZstdDecompressor().decompress(
            raw[1:], max_output_size=10 * 1024 * 1024
        )
        self.assertEqual(features._template_node_count(body), 5)
        payload = features._template_payload(body)
        labels = []
        for key, encoded in features._split_proto_fields(payload):
            if key != 0x3A:
                continue
            length, start = features._read_varint(encoded, 1)
            node = encoded[start : start + length]
            for field_key, field in features._split_proto_fields(node):
                if field_key != 0x32:
                    continue
                label_length, label_start = features._read_varint(field, 1)
                labels.append(
                    field[
                        label_start : label_start + label_length
                    ].decode("utf-8")
                )
        self.assertEqual(
            labels,
            ["01 降噪", "02 曝光", "03 色温", "04 饱和", "05 匹配"],
        )


if __name__ == "__main__":
    unittest.main()
