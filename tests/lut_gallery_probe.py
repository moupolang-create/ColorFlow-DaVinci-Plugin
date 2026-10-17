import os
import sys
import time
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
app.tab_buttons = [app._find("tab_%d" % i) for i in range(4)]
app.side_buttons = [app._find("side_%d" % i) for i in range(4)]
app._build_widget_registry()
app._connect()
print("GALLERY_BUILD_START", flush=True)
app.on_lut_gallery(None)
print(
    "GALLERY_READY",
    len(app._gallery_entries) if app._gallery_entries else 0,
    flush=True,
)
time.sleep(12.0)
app.on_gallery_close(None)
app.win.Close()
print("GALLERY_PROBE_DONE", flush=True)

