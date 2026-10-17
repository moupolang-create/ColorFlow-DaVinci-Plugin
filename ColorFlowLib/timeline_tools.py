"""Timeline planning helpers kept separate from the Resolve API surface."""

import math
import re
from collections import Counter


_NATURAL_RE = re.compile(r"(\d+)")


def natural_key(value):
    return [
        int(part) if part.isdigit() else part.lower()
        for part in _NATURAL_RE.split(str(value or ""))
    ]


def parse_resolution(value):
    match = re.search(r"(\d+)\s*[xX×]\s*(\d+)", str(value or ""))
    if not match:
        return None
    width = int(match.group(1))
    height = int(match.group(2))
    if width <= 0 or height <= 0:
        return None
    return width, height


def parse_fps(value):
    match = re.search(r"(\d+(?:\.\d+)?)", str(value or ""))
    if not match:
        return None
    try:
        fps = float(match.group(1))
    except ValueError:
        return None
    if not math.isfinite(fps) or fps <= 0 or fps > 240:
        return None
    return fps


def summarize_sources(properties, fallback_fps=25.0):
    """Choose a practical timeline resolution and frame rate.

    `properties` is a list of dicts with optional "resolution" and "fps" keys.
    The largest pixel count wins; the most common frame rate wins. Ties are
    resolved deterministically.
    """
    resolutions = [item.get("resolution") for item in properties if item.get("resolution")]
    rates = [item.get("fps") for item in properties if item.get("fps")]
    if not resolutions:
        raise ValueError("没有检测到可用的视频分辨率。")
    if not rates:
        rates = [float(fallback_fps or 25.0)]

    resolution_counts = Counter(resolutions)
    largest = max(resolutions, key=lambda pair: (pair[0] * pair[1], pair[0], pair[1]))
    rate_counts = Counter(round(rate, 3) for rate in rates)
    most_common_rate, common_count = rate_counts.most_common(1)[0]
    # Deterministic tie handling: prefer the highest rate among equally common.
    tied = [rate for rate, count in rate_counts.items() if count == common_count]
    most_common_rate = max(tied) if tied else most_common_rate

    return {
        "width": largest[0],
        "height": largest[1],
        "fps": most_common_rate,
        "resolution_counts": dict(resolution_counts),
        "fps_counts": dict(rate_counts),
        "mixed_resolution": len(resolution_counts) > 1,
        "mixed_fps": len(rate_counts) > 1,
        "source_count": len(properties),
    }


def _parse_timecode(timecode):
    parts = str(timecode or "00:00:00:00").split(":")
    if len(parts) != 4:
        parts = ["00", "00", "00", "00"]
    try:
        return [int(part) for part in parts]
    except ValueError:
        return [0, 0, 0, 0]


def _drop_count(nominal):
    if nominal == 30:
        return 2
    if nominal == 60:
        return 4
    return 0


def _df_timecode_to_frames(timecode, nominal):
    hours, minutes, seconds, frames = _parse_timecode(timecode)
    drop = _drop_count(nominal)
    total_minutes = hours * 60 + minutes
    return (
        nominal * (hours * 3600 + minutes * 60 + seconds)
        + frames
        - drop * (total_minutes - total_minutes // 10)
    )


def _df_frames_to_timecode(total, nominal):
    drop = _drop_count(nominal)
    if drop == 0:
        return None
    total = max(0, int(total))
    frames_per_minute = nominal * 60 - drop
    frames_per_10_minutes = nominal * 600 - drop * 9
    ten_minutes = total // frames_per_10_minutes
    remainder = total % frames_per_10_minutes
    if remainder < nominal * 60:
        extra_minutes = 0
    else:
        extra_minutes = (remainder - nominal * 60) // frames_per_minute + 1
    total = total + drop * (9 * ten_minutes + extra_minutes)
    hours = total // (nominal * 3600)
    total %= nominal * 3600
    minutes = total // (nominal * 60)
    total %= nominal * 60
    seconds = total // nominal
    frames = total % nominal
    return "%02d:%02d:%02d:%02d" % (hours, minutes, seconds, frames)


def frames_to_timecode(
    frame_offset, fps, start_timecode="00:00:00:00", drop_frame=False
):
    """Convert a timeline frame offset to a Resolve-friendly timecode.

    `frame_offset` is measured from the timeline start frame, not from zero
    timecode. This matters for drop-frame projects whose start TC is not
    midnight.
    """
    nominal = max(1, int(round(float(fps))))
    offset = int(frame_offset)
    if drop_frame and _drop_count(nominal):
        start_frames = _df_timecode_to_frames(start_timecode, nominal)
        return _df_frames_to_timecode(start_frames + offset, nominal)
    hours, minutes, seconds, frames = _parse_timecode(start_timecode)
    start_frames = (
        hours * 3600 * nominal
        + minutes * 60 * nominal
        + seconds * nominal
        + frames
    )
    total = max(0, offset + start_frames)
    hours = total // (nominal * 3600)
    total %= nominal * 3600
    minutes = total // (nominal * 60)
    total %= nominal * 60
    seconds = total // nominal
    frames = total % nominal
    return "%02d:%02d:%02d:%02d" % (hours, minutes, seconds, frames)


def format_duration(frames, fps):
    frames = max(0, int(frames))
    nominal = max(1, int(round(float(fps))))
    seconds = frames / float(nominal)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    remainder = seconds % 60
    return "%02d:%02d:%05.2f" % (hours, minutes, remainder)

