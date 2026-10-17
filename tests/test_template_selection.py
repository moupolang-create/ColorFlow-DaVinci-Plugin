import os
import tempfile
import unittest

from ColorFlowLib import features


class TemplateSelectionTest(unittest.TestCase):
    def setUp(self):
        self.original = (
            features.TEMPLATE_DIR,
            features.ACTIVE_TEMPLATE_PATH,
            features.GRADEPILOT_TEMPLATE,
        )
        self.folder = tempfile.TemporaryDirectory()
        features.TEMPLATE_DIR = self.folder.name
        features.ACTIVE_TEMPLATE_PATH = os.path.join(
            self.folder.name, "active_template.txt"
        )
        features.GRADEPILOT_TEMPLATE = os.path.join(
            self.folder.name, "missing.drx"
        )

    def tearDown(self):
        (
            features.TEMPLATE_DIR,
            features.ACTIVE_TEMPLATE_PATH,
            features.GRADEPILOT_TEMPLATE,
        ) = self.original
        self.folder.cleanup()

    def write_template(self, name, stamp):
        path = os.path.join(self.folder.name, name)
        with open(path, "wb") as handle:
            handle.write(b"DRX")
        os.utime(path, (stamp, stamp))
        return path

    def test_newest_five_node_template_is_preferred(self):
        old = self.write_template("ColorFlow_5node_100000.drx", 1000)
        new = self.write_template("ColorFlow_5node_120000.drx", 2000)
        self.write_template("other.drx", 3000)
        self.assertEqual(features.find_template(), new)
        self.assertNotEqual(features.find_template(), old)

    def test_active_template_pointer_wins(self):
        old = self.write_template("ColorFlow_5node_100000.drx", 1000)
        self.write_template("ColorFlow_5node_120000.drx", 2000)
        features.set_active_template(old)
        self.assertEqual(features.find_template(), old)


if __name__ == "__main__":
    unittest.main()
