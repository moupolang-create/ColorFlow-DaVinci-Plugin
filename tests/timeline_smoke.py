import os
import sys
import time
from datetime import datetime


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import DaVinciResolveScript as dvr

from ColorFlowLib import resolve_bridge as rb


resolve = dvr.scriptapp("Resolve")
context = rb.get_context(resolve)
project = context["project"]
original = context["timeline"]
clips, origin = rb.media_clips(project, True)
print("sources", len(clips), origin, flush=True)
if not clips:
    raise RuntimeError("No media clips")
name = "ColorFlow Timeline Smoke " + datetime.now().strftime("%H%M%S")
result = rb.create_timeline(project, clips, name, "01:00:00:00")
created = result["timeline"]
print("created", created.GetName(), flush=True)
print("summary", result["summary"], flush=True)
print("start tc", created.GetStartTimecode(), flush=True)
print("video tracks", created.GetTrackCount("video"), flush=True)
print("frames", created.GetStartFrame(), created.GetEndFrame(), flush=True)
print("duration", result["duration"], flush=True)
if created.GetName() != name:
    raise RuntimeError("Timeline name mismatch")
if len(clips) < 1:
    raise RuntimeError("No clips appended")
if created.GetTrackCount("video") < 1:
    raise RuntimeError("No video track")
if created.GetStartTimecode() != "01:00:00:00":
    raise RuntimeError("Start timecode was not applied")
try:
    project.SetCurrentTimeline(original)
except Exception:
    pass
time.sleep(0.3)
print("deleted", project.GetMediaPool().DeleteTimelines([created]), flush=True)
print("current", project.GetCurrentTimeline().GetName(), flush=True)
print("TIMELINE_SMOKE_OK", flush=True)

