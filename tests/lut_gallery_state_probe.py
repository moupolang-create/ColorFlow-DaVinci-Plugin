import os
import sys
import time
import types


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import DaVinciResolveScript as dvr

from ColorFlowLib.ui_v3 import ColorFlowApp


def describe_item(item):
    if item is None:
        return "None"
    values = []
    for name in ("Text", "ToolTip", "Selected"):
        try:
            values.append("%s=%r" % (name, item[name]))
        except Exception as exc:
            values.append("%s=<%s>" % (name, exc))
    return " | ".join(values)


def item_path(item):
    try:
        return str(item.ToolTip[0])
    except Exception as exc:
        return "<%s>" % exc


resolve = dvr.scriptapp("Resolve")
fusion = resolve.Fusion()
bmd = types.SimpleNamespace(UIDispatcher=dvr.UIDispatcher)
app = ColorFlowApp(resolve, fusion, bmd)
app.win = app._build_window()
app.tab_buttons = [app._find("tab_%d" % index) for index in range(4)]
app.side_buttons = [app._find("side_%d" % index) for index in range(4)]
app._build_widget_registry()
app._connect()
app.on_lut_gallery(None)
tree = app._gallery_tree
time.sleep(1.0)
print("CURRENT", describe_item(tree.CurrentItem()), flush=True)
print("SELECTED", repr(tree.SelectedItems()), flush=True)
try:
    item_count = int(tree.TopLevelItemCount())
except Exception:
    item_count = 4
for index in range(min(4, item_count)):
    print("ROW", index, describe_item(tree.TopLevelItem(index)), flush=True)
    print("ROW_PATH", index, item_path(tree.TopLevelItem(index)), flush=True)
selected = tree.SelectedItems()
if isinstance(selected, dict):
    print("SELECTED_KEYS", list(selected.keys()), flush=True)
    print("SELECTED_VALUES", [describe_item(v) for v in selected.values()], flush=True)
print(
    "APP_SELECTED",
    app._gallery_selected.get("relative") if app._gallery_selected else None,
    flush=True,
)
print(
    "APP_PREVIEW",
    app._gallery_selected.get("preview") if app._gallery_selected else None,
    flush=True,
)
print("PREVIEW_LABEL", app._gallery_preview.Text, flush=True)
print("ENTRY_0", app._gallery_entries[0]["relative"], flush=True)
print("ENTRY_0_PREVIEW", app._gallery_entries[0]["preview"], flush=True)
tree.TopLevelItem(3).Selected = True
app.pump()
print(
    "SELECT_ROW3",
    app._gallery_selected.get("relative") if app._gallery_selected else None,
    flush=True,
)
deadline = time.time() + 7.0
while time.time() < deadline:
    app.pump()
    time.sleep(0.05)
print(
    "AFTER_CLICK",
    app._gallery_selected.get("relative") if app._gallery_selected else None,
    flush=True,
)
time.sleep(2.0)
app.on_gallery_close(None)
app.win.Close()
print("STATE_PROBE_DONE", flush=True)
