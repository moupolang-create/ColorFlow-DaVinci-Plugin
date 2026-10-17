import os
import sys
import types


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import DaVinciResolveScript as dvr

from ColorFlowLib.ui import ColorFlowApp


resolve = dvr.scriptapp("Resolve")
fusion = resolve.Fusion()
bmd = types.SimpleNamespace(UIDispatcher=dvr.UIDispatcher)
app = ColorFlowApp(resolve, fusion, bmd)
app.win = app._build_window()
app._connect()
app.win.Show()
app.on_refresh(None)
print("SOURCE", app._find("source_info").Text, flush=True)
print("NODES", app._find("node_combo").CurrentText, flush=True)
app.on_reference(None)
print("REFERENCE_SET", app.reference is not None, flush=True)
if app.reference:
    print("REFERENCE", app.reference["name"], flush=True)
print("REFERENCE_LABEL", app._find("reference_info").Text, flush=True)
print("RESTORE_SCOPE", app._find("scope_restore").CurrentText, flush=True)
print("MATCH_SCOPE", app._find("scope_match").CurrentText, flush=True)
print("LOG", app._find("log").PlainText, flush=True)
app.win.Close()
print("UI_HANDLER_PROBE_DONE", flush=True)

