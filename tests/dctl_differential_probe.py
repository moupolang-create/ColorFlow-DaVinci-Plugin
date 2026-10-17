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


KNOWN_DCTL = "Onv13GradePilot/onv13-dwg-scene-look-candidate-120-1792139902574-55180171f5d258.dctl"


def delta(path_a, path_b):
    a = Image.open(path_a).convert("RGB")
    b = Image.open(path_b).convert("RGB")
    return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3.0


resolve = dvr.scriptapp("Resolve")
context = rb.get_context(resolve)
project = context["project"]
original = context["timeline"]
duplicate = original.DuplicateTimeline(
    "ColorFlow Diff " + datetime.now().strftime("%H%M%S")
)
temp_dir = tempfile.mkdtemp(prefix="colorflow-diff-")
paths = {name: os.path.join(temp_dir, name + ".jpg") for name in ("base", "ours", "known", "node2")}
print("duplicate", duplicate.GetName(), temp_dir, flush=True)
try:
    project.SetCurrentTimeline(duplicate)
    time.sleep(0.4)
    resolve.OpenPage("edit")
    time.sleep(0.8)
    resolve.OpenPage("color")
    time.sleep(1.8)
    item = duplicate.GetCurrentVideoItem() or rb.video_items(duplicate, "timeline", None)[0]
    start, end = int(item.GetStart()), int(item.GetEnd())
    target = start + max(0, min(1, (end - start) // 2))
    tc = frames_to_timecode(
        target - int(duplicate.GetStartFrame()),
        float(duplicate.GetSetting("timelineFrameRate") or 25.0),
        duplicate.GetStartTimecode(),
        str(duplicate.GetSetting("timelineDropFrameTimecode") or "0") == "1",
    )
    duplicate.SetCurrentTimecode(tc)
    time.sleep(0.4)
    graph = item.GetNodeGraph()
    graph.SetNodeEnabled(6, True)
    time.sleep(0.3)
    project.ExportCurrentFrameAsStill(paths["base"])
    print("base exported", flush=True)

    backup, version = rb.create_backup_version(item, "diff")
    model = {
        "exposure_stops": 1.0,
        "wb_rg": 0.0,
        "wb_bg": 0.0,
        "contrast": 1.0,
        "saturation": 1.0,
    }
    text = analysis.model_to_dctl(model, "dwg", "diff-ev1")
    path, relative = rb.write_dctl(text, "diff-ev1")
    rb.apply_lut(project, item, 6, path, relative)
    time.sleep(1.2)
    project.ExportCurrentFrameAsStill(paths["ours"])
    print("ours delta", round(delta(paths["base"], paths["ours"]), 4), flush=True)

    rb.apply_lut(project, item, 6, os.path.join(rb.lut_root(), KNOWN_DCTL), KNOWN_DCTL)
    time.sleep(1.2)
    project.ExportCurrentFrameAsStill(paths["known"])
    print("known delta", round(delta(paths["base"], paths["known"]), 4), flush=True)

    # Also try our DCTL on node 2, which definitely contains existing tools.
    rb.apply_lut(project, item, 2, path, relative)
    time.sleep(1.2)
    project.ExportCurrentFrameAsStill(paths["node2"])
    print("node2 delta", round(delta(paths["base"], paths["node2"]), 4), flush=True)
finally:
    try:
        project.SetCurrentTimeline(original)
    except Exception:
        pass
    time.sleep(0.3)
    try:
        print("deleted", project.GetMediaPool().DeleteTimelines([duplicate]), flush=True)
    except Exception:
        pass

