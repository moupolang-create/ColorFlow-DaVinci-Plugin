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
app.tab_buttons = [app._find("tab_%d" % i) for i in range(4)]
app.side_buttons = [app._find("side_%d" % i) for i in range(4)]
app._build_widget_registry()
app._connect()
print("ZH", app._find("tab_0").Text, app._find("btn_one_click_restore").Text, flush=True)
app.language = "en"
app.apply_language()
print(
    "EN",
    app._find("tab_0").Text,
    app._find("btn_one_click_restore").Text,
    app._find("btn_undo_match").Text,
    flush=True,
)
print("TITLE", app._find("title_normalize").Text, flush=True)
print("CTX", app._find("ctx_project").Text, flush=True)
print("WARN", app._find("analysis_warning").Text, flush=True)
print("STATUS", app._find("analysis_status").Text, flush=True)
print("LANG_ITEMS", app._find("lang_combo").Count(), flush=True)
app.language = "zh"
app.apply_language()
print("BACK", app._find("tab_0").Text, app._find("btn_one_click_restore").Text, flush=True)
app.win.Close()
print("LANGUAGE_PROBE_DONE", flush=True)

