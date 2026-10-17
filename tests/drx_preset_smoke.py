"""Smoke-test DRX preset export/apply and the HTML report.

Uses a generated colour-bar still and a temporary timeline in the currently
open project. The timeline and media-pool clip are removed at the end.
"""

import os
import sys
import time

from PIL import Image, ImageDraw


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import DaVinciResolveScript as dvr

from ColorFlowLib import features
from ColorFlowLib import resolve_bridge as rb


def make_fixture(path):
    image = Image.new("RGB", (1920, 1080), (28, 30, 34))
    draw = ImageDraw.Draw(image)
    colors = [
        (230, 230, 230),
        (230, 210, 60),
        (60, 210, 210),
        (60, 200, 80),
        (210, 60, 210),
        (210, 60, 60),
        (60, 70, 210),
    ]
    width = image.width // len(colors)
    for index, color in enumerate(colors):
        draw.rectangle(
            [index * width, 0, (index + 1) * width, image.height // 2],
            fill=color,
        )
    draw.rectangle([0, image.height // 2, image.width, image.height], fill=(88, 88, 88))
    image.save(path)


def main():
    fixture = os.path.join(ROOT, "tests", "fixtures", "colorflow_bars.png")
    os.makedirs(os.path.dirname(fixture), exist_ok=True)
    make_fixture(fixture)
    resolve = dvr.scriptapp("Resolve")
    context = rb.get_context(resolve)
    project = context["project"]
    original = context["timeline"]
    mpp = project.GetMediaPool()
    imported = mpp.ImportMedia([fixture]) or []
    if not imported:
        raise RuntimeError("ImportMedia returned no clip")
    clip = imported[0]
    timeline = None
    try:
        timeline = mpp.CreateTimelineFromClips("ColorFlow Preset Smoke", [clip])
        if timeline is None:
            raise RuntimeError("CreateTimelineFromClips failed")
        project.SetCurrentTimeline(timeline)
        time.sleep(0.3)
        resolve.OpenPage("edit")
        time.sleep(0.6)
        resolve.OpenPage("color")
        time.sleep(1.0)
        entry = features.save_preset_with_project(project, timeline, "API Smoke", "室内")
        print("preset", entry["file"], os.path.exists(entry["file"]), flush=True)
        item = timeline.GetCurrentVideoItem() or rb.video_items(timeline, "timeline", None)[0]
        print("apply", features.apply_preset(project, item, entry["file"]), flush=True)
        report, rows = features.report_timeline(project, timeline)
        print("report", report, len(rows), os.path.exists(report), flush=True)
        print("DRX_SMOKE_OK", flush=True)
    finally:
        try:
            if original is not None:
                project.SetCurrentTimeline(original)
        except Exception:
            pass
        time.sleep(0.2)
        try:
            print("timeline deleted", mpp.DeleteTimelines([timeline]), flush=True)
        except Exception:
            pass
        try:
            print("clip deleted", mpp.DeleteClips([clip]), flush=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()

