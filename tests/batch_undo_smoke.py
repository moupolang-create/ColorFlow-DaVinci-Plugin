import os
import sys
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import DaVinciResolveScript as dvr

from ColorFlowLib import features
from ColorFlowLib import resolve_bridge as rb


resolve = dvr.scriptapp("Resolve")
context = rb.get_context(resolve)
project = context["project"]
original = context["timeline"]
duplicate = original.DuplicateTimeline("ColorFlow Batch Undo Smoke")
if duplicate is None:
    raise RuntimeError("DuplicateTimeline failed")
print("duplicate", duplicate.GetName(), flush=True)
try:
    project.SetCurrentTimeline(duplicate)
    time.sleep(0.3)
    resolve.OpenPage("edit")
    time.sleep(0.6)
    resolve.OpenPage("color")
    time.sleep(1.0)
    item = duplicate.GetCurrentVideoItem() or rb.video_items(
        duplicate, "timeline", None
    )[0]
    tools_before = sum(len(node["tools"]) for node in rb.list_nodes(item))
    previous, new_version = rb.create_backup_version(item, "batch undo smoke")
    print("previous", previous, "new", new_version, flush=True)
    data = features.save_batch_manifest(
        "match",
        duplicate,
        [
            (
                item,
                previous.get("versionName"),
                previous.get("versionType", 0),
            )
        ],
    )
    print("manifest", features.LAST_BATCH_PATH, bool(data), flush=True)
    rb.reset_grade(item)
    time.sleep(0.3)
    tools_after_reset = sum(len(node["tools"]) for node in rb.list_nodes(item))
    loaded = features.load_batch_manifest()
    restored, failed = features.restore_batch_manifest(duplicate, loaded)
    time.sleep(0.3)
    tools_after_restore = sum(len(node["tools"]) for node in rb.list_nodes(item))
    print("tools", tools_before, tools_after_reset, tools_after_restore, flush=True)
    print("restored", restored, "failed", failed, flush=True)
    features.clear_batch_manifest()
    print("BATCH_UNDO_SMOKE_OK", flush=True)
finally:
    try:
        project.SetCurrentTimeline(original)
    except Exception:
        pass
    time.sleep(0.3)
    try:
        print(
            "deleted",
            project.GetMediaPool().DeleteTimelines([duplicate]),
            flush=True,
        )
    except Exception:
        pass

