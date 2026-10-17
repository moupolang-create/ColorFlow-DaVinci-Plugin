import os
import sys
import types


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import DaVinciResolveScript as dvr

from ColorFlowLib.ui_v2 import ColorFlowApp


resolve = dvr.scriptapp("Resolve")
fusion = resolve.Fusion()
bmd = types.SimpleNamespace(UIDispatcher=dvr.UIDispatcher)
app = ColorFlowApp(resolve, fusion, bmd)
app.win = app._build_window()
app.tab_buttons = [app._find("tab_%d" % index) for index in range(4)]
app.side_buttons = [app._find("side_%d" % index) for index in range(4)]
app._connect()
print("BUILD_OK", flush=True)
app.refresh_all()
print("REFRESH_OK", flush=True)
for index in range(4):
    app.switch_tab(index)
print("TABS_OK", flush=True)
print("lut_items", app._find("lut_combo").Count(), flush=True)
print("preset_items", app._find("preset_combo").Count(), flush=True)
print("match_scope", app._find("match_scope").CurrentText, flush=True)
print("preset_scope", app._find("preset_scope").CurrentText, flush=True)
app.win.Close()
print("V2_BUILD_PROBE_DONE", flush=True)

