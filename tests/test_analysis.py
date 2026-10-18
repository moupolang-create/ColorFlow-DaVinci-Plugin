import base64
import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ColorFlowLib import analysis
from ColorFlowLib import features
from ColorFlowLib.timeline_tools import (
    frames_to_timecode,
    natural_key,
    parse_fps,
    parse_resolution,
    summarize_sources,
)


def solid(width, height, rgb, channels=3):
    pixel = bytes(rgb[:channels]) + bytes(max(0, channels - 3))
    return pixel * (width * height)


def thumbnail(width, height, rgb, channels=3):
    return {
        "width": width,
        "height": height,
        "format": "RGB 8 bit",
        "data": base64.b64encode(solid(width, height, rgb, channels)).decode("ascii"),
    }


class AnalysisTests(unittest.TestCase):
    def test_neutral_gray_restore_is_mild(self):
        stats = analysis.analyze_thumbnail(thumbnail(64, 64, (128, 128, 128)))
        model = analysis.restore_model(stats, 1.0)
        self.assertLess(abs(model["wb_rg"]), 0.01)
        self.assertLess(abs(model["wb_bg"]), 0.01)
        self.assertLess(abs(model["exposure_stops"]), 0.35)

    def test_warm_cast_is_pulled_back(self):
        stats = analysis.analyze_thumbnail(thumbnail(64, 64, (165, 120, 95)))
        self.assertGreater(stats["rg"], 0.30)
        model = analysis.restore_model(stats, 1.0)
        self.assertLess(model["wb_rg"], -0.05)
        corrected = analysis.apply_model_to_rgb(
            model, solid(64, 64, (165, 120, 95)), 3
        )
        corrected_stats = analysis.analyze_pixels(64, 64, corrected, 3)
        self.assertLess(abs(corrected_stats["rg"]), abs(stats["rg"]))
        self.assertLess(abs(corrected_stats["bg"]), abs(stats["bg"]))

    def test_dark_frame_gets_positive_exposure(self):
        stats = analysis.analyze_thumbnail(thumbnail(64, 64, (40, 40, 40)))
        model = analysis.restore_model(stats, 1.0)
        self.assertGreater(model["exposure_stops"], 0.5)
        self.assertLessEqual(model["exposure_stops"], 2.0)

    def test_match_moves_target_toward_reference(self):
        reference = analysis.analyze_thumbnail(thumbnail(64, 64, (150, 150, 150)))
        target = analysis.analyze_thumbnail(thumbnail(64, 64, (70, 55, 45)))
        model = analysis.match_model(reference, target, 1.0)
        self.assertGreater(model["exposure_stops"], 0.5)
        corrected = analysis.apply_model_to_rgb(
            model, solid(64, 64, (70, 55, 45)), 3
        )
        corrected_stats = analysis.analyze_pixels(64, 64, corrected, 3)
        before = abs(
            __import__("math").log2(target["p50"] / reference["p50"])
        )
        after = abs(
            __import__("math").log2(corrected_stats["p50"] / reference["p50"])
        )
        self.assertLess(after, before)
        self.assertLess(abs(corrected_stats["rg"]), abs(target["rg"]))

    def test_flat_black_match_has_no_contrast_shift(self):
        stats = analysis.analyze_thumbnail(thumbnail(16, 16, (0, 0, 0)))
        model = analysis.match_model(stats, stats, 0.7)
        self.assertAlmostEqual(model["contrast"], 1.0, places=6)
        self.assertAlmostEqual(model["saturation"], 1.0, places=6)

    def test_flat_log_restore_gets_stronger_tone_lift(self):
        flat = {
            "p50": 0.10,
            "p85": 0.30,
            "p01": 0.0,
            "p99": 0.45,
            "contrast_stops": 2.2,
            "saturation": 0.08,
            "rg": 0.0,
            "bg": 0.0,
            "used_neutral": True,
            "neutral_ratio": 0.05,
        }
        tone = analysis.saturation_model(flat, 0.70, True)
        self.assertGreater(tone["contrast"], 1.45)
        self.assertGreater(tone["saturation"], 1.40)
        restored = analysis.restore_model(flat, 0.70, True)
        self.assertGreater(restored["contrast"], 1.45)
        self.assertGreater(restored["saturation"], 1.40)
        self.assertEqual(restored["stretch"], 0.0)
        self.assertEqual(restored["white_point"], 1.0)
        dctl = analysis.model_to_dctl(restored, "dwg", "flat")
        self.assertIn("Tone stretch", dctl)
        self.assertIn("cf_mix", dctl)
        normal = dict(flat, contrast_stops=4.0, saturation=0.20)
        normal_model = analysis.saturation_model(normal, 0.70, True)
        self.assertLess(normal_model["contrast"], 1.15)
        self.assertLess(normal_model["saturation"], 1.15)

    def test_dctl_is_self_contained(self):
        stats = analysis.analyze_thumbnail(thumbnail(32, 32, (120, 100, 80)))
        model = analysis.match_model(stats, stats, 0.7)
        text = analysis.model_to_dctl(model, "dwg", "shot 01")
        self.assertIn("transform(int p_Width", text)
        self.assertIn("cf_decode", text)
        self.assertNotIn("_exp2f", text)
        self.assertNotIn("_log2f", text)
        self.assertIn("return encoded", text)

    def test_cdl_ranges(self):
        stats = analysis.analyze_thumbnail(thumbnail(32, 32, (180, 120, 80)))
        model = analysis.restore_model(stats, 0.8)
        cdl = analysis.model_to_cdl(model, 3)
        self.assertEqual(cdl["NodeIndex"], "3")
        self.assertEqual(len(cdl["Slope"].split()), 3)
        self.assertEqual(len(cdl["Offset"].split()), 3)
        self.assertEqual(len(cdl["Power"].split()), 3)
        self.assertGreater(float(cdl["Saturation"]), 0.0)

    def test_tone_and_skin_dctl(self):
        stats = analysis.analyze_thumbnail(thumbnail(32, 32, (110, 100, 90)))
        tone = analysis.tone_stretch_dctl(stats, 0.7, "dwg", "auto-bw")
        self.assertIn("auto black/white", tone)
        self.assertIn("cf_mix", tone)
        self.assertNotIn("_exp2f", tone)
        skin = analysis.skin_dctl(5, 10, -5, 0.5, True, "dwg", "skin")
        self.assertIn("skin-selective", skin)
        self.assertIn("cf_smooth", skin)
        self.assertIn("background", skin)
        self.assertNotIn("_log2f", skin)

    def test_dctl_labels_are_ascii(self):
        self.assertEqual(analysis.ascii_label("自动白平衡"), "auto_white_balance")
        self.assertEqual(analysis.ascii_label("一键还原-A132"), "one_click_restore")
        self.assertEqual(analysis.ascii_label("02-exposure"), "02-exposure")
        for value in ("自动白平衡", "匹配-A132", "一键还原"):
            label = analysis.ascii_label(value)
            self.assertTrue(all(ord(character) < 128 for character in label))

    def test_combined_warning_model(self):
        stats = analysis.analyze_thumbnail(thumbnail(32, 32, (165, 120, 95)))
        model = analysis.combined_warning_model(stats, 0.7)
        self.assertTrue(model["applied"])
        self.assertTrue(
            abs(model["wb_rg"]) > 0.0
            or abs(model["wb_bg"]) > 0.0
            or abs(model["saturation"] - 1.0) > 0.0
        )


class TimelineToolTests(unittest.TestCase):
    def test_parse_resolution(self):
        self.assertEqual(parse_resolution("5120x2700"), (5120, 2700))
        self.assertEqual(parse_resolution("1920 × 1080"), (1920, 1080))
        self.assertIsNone(parse_resolution("unknown"))

    def test_parse_fps(self):
        self.assertEqual(parse_fps("29.97"), 29.97)
        self.assertEqual(parse_fps("30.0"), 30.0)
        self.assertIsNone(parse_fps(""))

    def test_summarize_sources(self):
        summary = summarize_sources(
            [
                {"resolution": (1920, 1080), "fps": 25.0},
                {"resolution": (3840, 2160), "fps": 25.0},
                {"resolution": (3840, 2160), "fps": 30.0},
            ]
        )
        self.assertEqual((summary["width"], summary["height"]), (3840, 2160))
        self.assertEqual(summary["fps"], 25.0)
        self.assertTrue(summary["mixed_resolution"])
        self.assertTrue(summary["mixed_fps"])

    def test_timecode_offset(self):
        self.assertEqual(frames_to_timecode(0, 30, "01:00:00:00"), "01:00:00:00")
        self.assertEqual(frames_to_timecode(1, 30, "01:00:00:00"), "01:00:00:01")
        self.assertEqual(frames_to_timecode(30, 30, "01:00:00:00"), "01:00:01:00")
        self.assertEqual(frames_to_timecode(0, 25, "00:00:00:00"), "00:00:00:00")

    def test_drop_frame_timecode(self):
        self.assertEqual(
            frames_to_timecode(0, 29.97, "01:00:00:00", True),
            "01:00:00:00",
        )
        self.assertEqual(
            frames_to_timecode(1799, 29.97, "00:00:00:00", True),
            "00:00:59:29",
        )
        self.assertEqual(
            frames_to_timecode(1800, 29.97, "00:00:00:00", True),
            "00:01:00:02",
        )
        self.assertEqual(
            frames_to_timecode(0, 29.97, "01:00:00:00", False),
            "01:00:00:00",
        )

    def test_natural_key(self):
        names = ["shot10", "shot2", "shot1"]
        names.sort(key=natural_key)
        self.assertEqual(names, ["shot1", "shot2", "shot10"])


class MetadataTests(unittest.TestCase):
    class FakeClip:
        def __init__(self, name, props, meta):
            self.name = name
            self.props = props
            self.meta = meta

        def GetName(self):
            return self.name

        def GetClipProperty(self):
            return self.props

        def GetMetadata(self):
            return self.meta

    def test_slog3_detection_and_info(self):
        clip = self.FakeClip(
            "A001_SLog3.mxf",
            {
                "Resolution": "3840x2160",
                "FPS": "25",
                "Video Codec": "ProRes 422 HQ",
                "Bit Depth": "10 bit",
            },
            {
                "Color Space": "S-Gamut3.Cine/S-Log3",
                "White Balance": "5600 K",
            },
        )
        info = features.clip_info(clip)
        self.assertEqual(info["log"]["name"], "SLog3")
        self.assertEqual(info["resolution"], "3840x2160")
        self.assertEqual(info["bit_depth"], "10 bit")
        self.assertIn("5600", info["white_balance"])

    def test_clog_and_hlg_detection(self):
        self.assertEqual(
            features.detect_log({"Color Space": "Canon Log 3"}, {}, "clip")["name"],
            "CLog3",
        )
        self.assertEqual(
            features.detect_log({"Gamma": "HLG"}, {}, "clip")["name"],
            "HLG",
        )


if __name__ == "__main__":
    unittest.main()

