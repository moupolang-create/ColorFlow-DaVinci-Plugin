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
app.tab_buttons = [app._find("tab_%d" % index) for index in range(4)]
app.side_buttons = [app._find("side_%d" % index) for index in range(4)]
app._build_widget_registry()
app._connect()
for page in app.pages[1:]:
    try:
        app.page_host.RemoveChild(page)
    except Exception:
        pass
app.win.Show()
app.switch_tab(1)
app.refresh_all()
print("V3_VISUAL_READY", app.win.Size(), app.win.Pos(), flush=True)
time.sleep(10.0)
try:
    app.win.Close()
except Exception:
    pass
print("V3_VISUAL_DONE", flush=True)

