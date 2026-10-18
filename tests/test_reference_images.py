import base64
import os
import tempfile
import unittest

from ColorFlowLib import features
from ColorFlowLib import preview


class ReferenceImageTest(unittest.TestCase):
    def test_png_roundtrip_and_reference_stats(self):
        width, height = 4, 2
        rgb = bytes(
            [
                20,
                40,
                60,
                80,
                100,
                120,
                140,
                160,
                180,
                200,
                220,
                240,
                10,
                20,
                30,
                40,
                50,
                60,
                70,
                80,
                90,
                100,
                110,
                120,
            ]
        )
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "reference.png")
            preview.write_png(path, width, height, rgb)
            read_width, read_height, read_rgb = preview.read_png_rgb(path)
            self.assertEqual((read_width, read_height), (width, height))
            self.assertEqual(read_rgb, rgb)
            reference = features._reference_from_png(
                path, "test", "local"
            )
            self.assertEqual(reference["name"], "test")
            self.assertEqual(reference["thumbnail"]["width"], width)
            self.assertEqual(
                base64.b64decode(reference["thumbnail"]["data"]), rgb
            )
            self.assertIn("p50", reference["stats"])


if __name__ == "__main__":
    unittest.main()
