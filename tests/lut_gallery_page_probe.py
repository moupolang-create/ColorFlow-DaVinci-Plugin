import os
import sys
import types


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import DaVinciResolveScript as dvr

from ColorFlowLib.ui_v3 import ColorFlowApp


resolve = dvr.scriptapp("Resolve")
fusion = resolve.Fusion()
bmd = types.SimpleNamespace(UIDispatcher=dvr.UIDispatcher)
app = ColorFlowApp(resolve, fusion, bmd)
app.win = app._build_window()
app.tab_buttons = [app._find("tab_%d" % index) for index in range(4)]
app.side_buttons = [app._find("side_%d" % index) for index in range(4)]
app._build_widget_registry()
app._connect()
app.language = "en"
app.on_lut_gallery(None)
print("OPEN_PAGE", app._gallery_page_label.Text, flush=True)
app._gallery_category.CurrentIndex = 6
app.on_gallery_category(None)
print(
    "CUSTOM_FILTER",
    len(app._gallery_filtered),
    sorted({entry["category"] for entry in app._gallery_entries}),
    flush=True,
)
print("FILTER_PAGE", app._gallery_page_label.Text, flush=True)
first_before = app._gallery_entries[0]["relative"]
app.on_gallery_next(None)
first_after = app._gallery_entries[0]["relative"] if app._gallery_entries else None
print("NEXT_PAGE", app._gallery_page, first_before, first_after, flush=True)
app.on_gallery_prev(None)
print("PREV_PAGE", app._gallery_page, flush=True)
app.on_gallery_close(None)
app.win.Close()
print("PAGE_PROBE_DONE", flush=True)
