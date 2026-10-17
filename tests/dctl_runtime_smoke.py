"""Prove that a generated DCTL actually changes Resolve's rendered pixels.

The test runs on a duplicated timeline. It exports the current frame before
and after writing a strong +1 EV DCTL, compares the JPEGs with Pillow, then
restores the previous colour version and deletes the duplicate.
"""

import os
import sys
import tempfile
import time
from datetime import datetime

from PIL import Image, ImageChops, ImageStat


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import DaVinciResolveScript as dvr

from ColorFlowLib import analysis
from ColorFlowLib import resolve_bridge as rb
from ColorFlowLib.timeline_tools import frames_to_timecode


def frame_delta(path_a, path_b):
    image_a = Image.open(path_a).convert("RGB")
    image_b = Image.open(path_b).convert("RGB")
    if image_a.size != image_b.size:
        raise RuntimeError("Exported frame sizes differ")
    diff = ImageChops.difference(image_a, image_b)
    stat = ImageStat.Stat(diff)
    return sum(stat.mean) / 3.0


def main():
    resolve = dvr.scriptapp("Resolve")
    context = rb.get_context(resolve)
    project = context["project"]
    original = context["timeline"]
    duplicate = original.DuplicateTimeline(
        "ColorFlow DCTL Runtime " + datetime.now().strftime("%H%M%S")
    )
    if duplicate is None:
        raise RuntimeError("DuplicateTimeline returned None")
    temp_dir = tempfile.mkdtemp(prefix="colorflow-runtime-")
    before_path = os.path.join(temp_dir, "before.jpg")
    after_path = os.path.join(temp_dir, "after.jpg")
    restored_path = os.path.join(temp_dir, "restored.jpg")
    print("duplicate", duplicate.GetName(), temp_dir, flush=True)
    try:
        project.SetCurrentTimeline(duplicate)
        time.sleep(0.4)
        resolve.OpenPage("edit")
        time.sleep(0.8)
        resolve.OpenPage("color")
        time.sleep(1.8)
        item = duplicate.GetCurrentVideoItem()
        if item is None:
            item = rb.video_items(duplicate, "timeline", None)[0]
        start = int(item.GetStart())
        end = int(item.GetEnd())
        target_frame = start + max(0, min(1, (end - start) // 2))
        fps = float(duplicate.GetSetting("timelineFrameRate") or 25.0)
        tc = frames_to_timecode(
            target_frame - int(duplicate.GetStartFrame()),
            fps,
            duplicate.GetStartTimecode(),
            str(duplicate.GetSetting("timelineDropFrameTimecode") or "0") == "1",
        )
        duplicate.SetCurrentTimecode(tc)
        time.sleep(0.4)
        print("frame", item.GetName(), target_frame, tc, flush=True)
        if not project.ExportCurrentFrameAsStill(before_path):
            raise RuntimeError("Before export failed")

        nodes = rb.list_nodes(item)
        target = [node for node in nodes if node["likely_empty"]]
        target = target[-1] if target else nodes[-1]
        print("node", target, flush=True)
        backup, version = rb.create_backup_version(item, "dctl-runtime")
        model = {
            "exposure_stops": 1.0,
            "wb_rg": 0.0,
            "wb_bg": 0.0,
            "contrast": 1.0,
            "saturation": 1.0,
        }
        text = analysis.model_to_dctl(model, "dwg", "runtime-ev1")
        path, relative = rb.write_dctl(text, "runtime-ev1")
        rb.apply_lut(project, item, target["index"], path, relative)
        time.sleep(1.2)
        if not project.ExportCurrentFrameAsStill(after_path):
            raise RuntimeError("After export failed")
        delta_apply = frame_delta(before_path, after_path)
        print("delta_apply", round(delta_apply, 4), flush=True)
        if delta_apply < 1.0:
            raise RuntimeError(
                "DCTL path was assigned but the rendered frame did not change"
            )

        previous_name = backup.get("versionName")
        previous_type = backup.get("versionType", 0)
        if previous_name and not rb.restore_version(item, previous_name, previous_type):
            raise RuntimeError("Could not restore previous version")
        time.sleep(1.0)
        if not project.ExportCurrentFrameAsStill(restored_path):
            raise RuntimeError("Restore export failed")
        delta_restore = frame_delta(before_path, restored_path)
        print("delta_restore", round(delta_restore, 4), flush=True)
        if delta_restore > 2.0:
            raise RuntimeError("Restored frame is still visibly different")
        print("DCTL_RUNTIME_OK", flush=True)
    finally:
        try:
            project.SetCurrentTimeline(original)
        except Exception:
            pass
        time.sleep(0.3)
        try:
            print(
                "duplicate deleted",
                project.GetMediaPool().DeleteTimelines([duplicate]),
                flush=True,
            )
        except Exception:
            pass


if __name__ == "__main__":
    main()

