"""Careful end-to-end smoke test on a duplicated timeline.

The original timeline is never modified. The duplicate is deleted at the end.
"""

import os
import sys
import time
import traceback
from datetime import datetime


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import DaVinciResolveScript as dvr

from ColorFlowLib import analysis
from ColorFlowLib import resolve_bridge as rb


def main():
    resolve = dvr.scriptapp("Resolve")
    context = rb.get_context(resolve)
    project = context["project"]
    original = context["timeline"]
    if original is None:
        raise RuntimeError("No current timeline")

    stamp = datetime.now().strftime("%H%M%S")
    name = "ColorFlow Smoke %s" % stamp
    duplicate = original.DuplicateTimeline(name)
    if duplicate is None:
        raise RuntimeError("DuplicateTimeline returned None")
    print("duplicate", duplicate.GetName(), duplicate.GetUniqueId(), flush=True)

    try:
        if not project.SetCurrentTimeline(duplicate):
            raise RuntimeError("Could not switch to duplicate timeline")
        time.sleep(0.3)
        resolve.OpenPage("edit")
        time.sleep(0.8)
        resolve.OpenPage("color")
        time.sleep(1.8)
        items = rb.video_items(duplicate, "timeline", None)
        item = duplicate.GetCurrentVideoItem() or items[0]
        print("item", item.GetName(), item.GetUniqueId(), flush=True)
        capture = rb.capture_item_thumbnail(duplicate, item)
        print("stats", analysis.describe_stats(capture["stats"]), flush=True)
        model = analysis.restore_model(capture["stats"], 0.25, False)
        print("model", analysis.describe_model(model), flush=True)
        nodes = rb.list_nodes(item)
        empty = [node for node in nodes if node["likely_empty"]]
        target = empty[-1] if empty else nodes[-1]
        print("target node", target, flush=True)

        before_version = rb.current_version(item)
        backup, version_name = rb.create_backup_version(item, "smoke")
        print("backup", before_version, "new", version_name, flush=True)
        tools_original = sum(len(node["tools"]) for node in rb.list_nodes(item))
        print("original tools", tools_original, flush=True)

        text = analysis.model_to_dctl(model, "dwg", "smoke")
        path, relative = rb.write_dctl(text, "smoke")
        print("dctl", path, relative, flush=True)
        applied = rb.apply_lut(project, item, target["index"], path, relative)
        print("applied", applied, flush=True)
        assigned = item.GetNodeGraph().GetLUT(target["index"])
        print("assigned", assigned, flush=True)
        if not assigned:
            raise RuntimeError("LUT path was not assigned")
        managed = [node for node in rb.list_nodes(item) if node.get("managed")]
        print("managed nodes", managed, flush=True)
        if not managed:
            raise RuntimeError("ColorFlow-managed node was not detected")

        tools_before = sum(len(node["tools"]) for node in rb.list_nodes(item))
        rb.reset_grade(item)
        time.sleep(0.2)
        tools_after_reset = sum(len(node["tools"]) for node in rb.list_nodes(item))
        print(
            "reset tools",
            tools_before,
            "->",
            tools_after_reset,
            flush=True,
        )
        if tools_after_reset >= tools_before:
            raise RuntimeError("ResetAllGrades did not clear the node tools")

        previous_name = backup.get("versionName")
        previous_type = backup.get("versionType", 0)
        print("restore previous", previous_name, previous_type, flush=True)
        if previous_name and not rb.restore_version(item, previous_name, previous_type):
            raise RuntimeError("Could not restore version after reset")
        time.sleep(0.2)
        tools_after_restore = sum(len(node["tools"]) for node in rb.list_nodes(item))
        print("restored tools", tools_after_restore, flush=True)
        if tools_after_restore != tools_original:
            raise RuntimeError("Version restore did not restore the node tools")
        restored_lut = item.GetNodeGraph().GetLUT(target["index"])
        print("restored lut", repr(restored_lut), flush=True)
        if restored_lut:
            raise RuntimeError("Restored version still has the ColorFlow LUT")
        print("SMOKE_OK", flush=True)
    finally:
        try:
            project.SetCurrentTimeline(original)
        except Exception:
            pass
        time.sleep(0.2)
        try:
            media_pool = project.GetMediaPool()
            deleted = media_pool.DeleteTimelines([duplicate])
            print("duplicate deleted", deleted, flush=True)
        except Exception:
            print("duplicate delete failed", traceback.format_exc(), flush=True)


if __name__ == "__main__":
    main()

