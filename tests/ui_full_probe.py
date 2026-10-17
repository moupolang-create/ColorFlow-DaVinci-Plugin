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
print("BUILD_START", flush=True)
app.win = app._build_window()
app._connect()
app.win.Show()
app.refresh_all()
app.on_reference(None)
print("BUILD_DONE", flush=True)
app.dispatcher.RunLoop()

