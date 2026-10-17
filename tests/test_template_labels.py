import unittest

from ColorFlowLib import features


def node_message(index):
    return bytes(
        [
            0x08,
            index,
            0x10,
            index,
            0x20,
            0x01,
            0x28,
            0x01,
            0x38,
            0x01,
        ]
    )


def template_body(nodes):
    payload = bytearray([0x08, 0x01])
    for index in range(1, nodes + 1):
        node = node_message(index)
        payload.append(0x3A)
        payload.extend(features._encode_varint(len(node)))
        payload.extend(node)
    return (
        b"\x0a"
        + features._encode_varint(len(payload))
        + bytes(payload)
    )


class TemplateLabelTest(unittest.TestCase):
    def test_default_restore_labels_use_last_node_for_match(self):
        labels = features.default_restore_labels(6)
        self.assertEqual(labels[1], "01 降噪")
        self.assertEqual(labels[2], "02 曝光")
        self.assertEqual(labels[3], "03 色温")
        self.assertEqual(labels[4], "04 饱和")
        self.assertEqual(labels[5], "05 备用")
        self.assertEqual(labels[6], "06 匹配")

    def test_relabel_body_inserts_node_label_fields(self):
        body = template_body(2)
        labels = {1: "01 降噪", 2: "02 匹配"}
        result = features._relabel_template_body(body, labels)
        payload = features._template_payload(result)
        nodes = [
            encoded
            for key, encoded in features._split_proto_fields(payload)
            if key == 0x3A
        ]
        self.assertEqual(len(nodes), 2)
        for node, expected in zip(nodes, ("01 降噪", "02 匹配")):
            length, start = features._read_varint(node, 1)
            node_payload = node[start : start + length]
            label_field = [
                encoded
                for key, encoded in features._split_proto_fields(node_payload)
                if key == 0x32
            ][0]
            label_length, label_start = features._read_varint(
                label_field, 1
            )
            self.assertEqual(
                label_field[label_start : label_start + label_length].decode(
                    "utf-8"
                ),
                expected,
            )


if __name__ == "__main__":
    unittest.main()
