"""ColorFlow — DaVinci Resolve Workflow Integration panel.

Install this file and the ColorFlowLib folder into:
    %PROGRAMDATA%\\Blackmagic Design\\DaVinci Resolve\\Support\\Workflow Integration Plugins

Then open Workspace > Workflow Integrations > ColorFlow.
"""

import os
import sys


def _candidate_roots():
    roots = []

    def add(path):
        if not path:
            return
        try:
            path = os.path.abspath(path)
        except Exception:
            return
        if path not in roots:
            roots.append(path)

    try:
        add(os.path.dirname(os.path.abspath(__file__)))
    except NameError:
        pass
    try:
        add(os.path.dirname(os.path.abspath(sys.argv[0])))
    except Exception:
        pass
    program_data = os.environ.get("PROGRAMDATA") or r"C:\ProgramData"
    add(
        os.path.join(
            program_data,
            "Blackmagic Design",
            "DaVinci Resolve",
            "Support",
            "Workflow Integration Plugins",
        )
    )
    return roots


for _root in reversed(_candidate_roots()):
    if _root not in sys.path:
        sys.path.insert(0, _root)


def _launch():
    from ColorFlowLib.ui_v3 import run

    run(globals())


if "resolve" in globals() and "fusion" in globals() and "bmd" in globals():
    try:
        _launch()
    except Exception:
        import traceback

        traceback.print_exc()
        raise
else:
    print("ColorFlow must be launched from DaVinci Resolve Studio.")
    print("Workspace > Workflow Integrations > ColorFlow")

