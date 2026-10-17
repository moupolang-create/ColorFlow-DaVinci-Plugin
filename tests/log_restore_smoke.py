import os
import sys
import time
import types


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import DaVinciResolveScript as dvr

from ColorFlowLib import resolve_bridge as rb
from ColorFlowLib.ui_v3 import ColorFlowApp


resolve = dvr.scriptapp("Resolve")
context = rb.get_context(resolve)
project = context["project"]
original = context["timeline"]
duplicate = original.DuplicateTimeline("ColorFlow Log Restore Smoke")
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
    before = {
        node["index"]: node["lut"] for node in rb.list_nodes(item)
    }
    print("before_luts", before, flush=True)

    fusion = resolve.Fusion()
    bmd = types.SimpleNamespace(UIDispatcher=dvr.UIDispatcher)
    app = ColorFlowApp(resolve, fusion, bmd)
    app.win = app._build_window()
    app.tab_buttons = [app._find("tab_%d" % i) for i in range(4)]
    app.side_buttons = [app._find("side_%d" % i) for i in range(4)]
    app._build_widget_registry()
    app._connect()
    app.on_split_restore(None)

    after = {
        node["index"]: node["lut"] for node in rb.list_nodes(item)
    }
    print("after_luts", after, flush=True)
    print("status", app._find("primary_status").PlainText, flush=True)
    print("LOG_RESTORE_SMOKE_OK", flush=True)

    app.on_undo(None)
    time.sleep(0.5)
    restored = {
        node["index"]: node["lut"] for node in rb.list_nodes(item)
    }
    print("restored_luts", restored, flush=True)
    app.win.Close()
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

