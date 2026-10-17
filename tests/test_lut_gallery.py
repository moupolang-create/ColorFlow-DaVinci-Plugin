import os
import tempfile
import unittest

from ColorFlowLib import lut_gallery


IDENTITY_3D = """TITLE "Identity"
LUT_3D_SIZE 2
0 0 0
1 0 0
0 1 0
1 1 0
0 0 1
1 0 1
0 1 1
1 1 1
"""


class LutGalleryTest(unittest.TestCase):
    def write_cube(self, text):
        handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=".cube", delete=False, encoding="utf-8"
        )
        handle.write(text)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_identity_3d_uses_red_fastest_cube_order(self):
        cube = lut_gallery._parse_cube(self.write_cube(IDENTITY_3D))
        self.assertIsNotNone(cube)
        rgb = lut_gallery._lookup_3d(cube, 0.75, 0.25, 0.5)
        self.assertAlmostEqual(rgb[0], 0.75, places=6)
        self.assertAlmostEqual(rgb[1], 0.25, places=6)
        self.assertAlmostEqual(rgb[2], 0.5, places=6)

    def test_3d_input_range_is_applied(self):
        text = """LUT_3D_SIZE 2
DOMAIN_MIN 0 0 0
DOMAIN_MAX 2 2 2
""" + IDENTITY_3D.split("LUT_3D_SIZE 2\n", 1)[1]
        cube = lut_gallery._parse_cube(self.write_cube(text))
        rgb = lut_gallery._lookup_3d(cube, 1.0, 0.5, 0.0)
        self.assertAlmostEqual(rgb[0], 0.5, places=6)
        self.assertAlmostEqual(rgb[1], 0.25, places=6)
        self.assertAlmostEqual(rgb[2], 0.0, places=6)

    def test_1d_lookup_interpolates_each_channel(self):
        path = self.write_cube(
            """LUT_1D_SIZE 3
0 0.5 1
0.5 0.25 0.5
1 0 0
"""
        )
        cube = lut_gallery._parse_cube(path)
        rgb = lut_gallery._lookup_1d(cube, 0.75, 0.0, 0.25)
        self.assertAlmostEqual(rgb[0], 0.75, places=6)
        self.assertAlmostEqual(rgb[1], 0.5, places=6)
        self.assertAlmostEqual(rgb[2], 0.75, places=6)

    def test_combined_1d_shaper_and_3d_lut(self):
        path = self.write_cube(
            """LUT_1D_SIZE 2
0 0 0
1 1 1
LUT_3D_SIZE 2
0 0 0
1 0 0
0 1 0
1 1 0
0 0 1
1 0 1
0 1 1
1 1 1
"""
        )
        cube = lut_gallery._parse_cube(path)
        self.assertIsNotNone(cube)
        self.assertEqual(cube["shaper_size"], 2)
        rgb = lut_gallery._lookup_3d(cube, 0.2, 0.4, 0.8)
        self.assertAlmostEqual(rgb[0], 0.2, places=6)
        self.assertAlmostEqual(rgb[1], 0.4, places=6)
        self.assertAlmostEqual(rgb[2], 0.8, places=6)

    def test_preview_png_is_generated(self):
        path = self.write_cube(IDENTITY_3D)
        source = lut_gallery.synthetic_source(40, 24)
        target = lut_gallery.generate_cube_preview(
            path, source, width=48, height=27
        )
        self.assertTrue(target and os.path.exists(target))
        with open(target, "rb") as handle:
            self.assertEqual(handle.read(8), b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()
