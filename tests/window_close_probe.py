import time
import types

import DaVinciResolveScript as dvr


resolve = dvr.scriptapp("Resolve")
fusion = resolve.Fusion()
bmd = types.SimpleNamespace(UIDispatcher=dvr.UIDispatcher)
ui = fusion.UIManager
dispatcher = bmd.UIDispatcher(ui)
window = dispatcher.AddWindow(
    {"ID": "close_probe_window", "WindowTitle": "ColorFlow close probe"},
    [ui.Label({"Text": "close probe"})],
)
window.Show()
for _ in range(8):
    dispatcher.StepLoop()
    time.sleep(0.05)
print(
    "FUNCTIONS",
    [
        name
        for name in dir(window)
        if any(
            key in name.lower()
            for key in ("close", "hide", "delete", "visible")
        )
    ],
    flush=True,
)
try:
    print("VISIBLE_BEFORE", bool(window.Visible), flush=True)
except Exception as exc:
    print("VISIBLE_BEFORE_ERR", exc, flush=True)
try:
    print("HIDE_RESULT", window.Hide(), flush=True)
except Exception as exc:
    print("HIDE_ERR", exc, flush=True)
for _ in range(8):
    dispatcher.StepLoop()
    time.sleep(0.05)
try:
    print("VISIBLE_AFTER_HIDE", bool(window.Visible), flush=True)
except Exception as exc:
    print("VISIBLE_AFTER_HIDE_ERR", exc, flush=True)
try:
    print("CLOSE_RESULT", window.Close(), flush=True)
except Exception as exc:
    print("CLOSE_ERR", exc, flush=True)
for _ in range(8):
    dispatcher.StepLoop()
    time.sleep(0.05)
print("DONE", flush=True)
