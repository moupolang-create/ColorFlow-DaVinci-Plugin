"""Pure-Python thumbnail previews for the Resolve panel."""

import os
import struct
import tempfile
import time
import zlib

from . import analysis
from . import resolve_bridge as rb


def _chunk(tag, data):
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def write_png(path, width, height, rgb):
    """Write an 8-bit RGB PNG without external dependencies."""
    stride = width * 3
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        raw.extend(rgb[y * stride : (y + 1) * stride])
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + _chunk(b"IEND", b"")
    )
    with open(path, "wb") as handle:
        handle.write(payload)


def thumbnail_to_png(thumbnail, path, width=360, height=203):
    source_w, source_h, raw, channels = analysis.decode_thumbnail(thumbnail)
    output = bytearray(width * height * 3)
    for y in range(height):
        source_y = min(source_h - 1, int(y * source_h / height))
        for x in range(width):
            source_x = min(source_w - 1, int(x * source_w / width))
            source_offset = (source_y * source_w + source_x) * channels
            target_offset = (y * width + x) * 3
            output[target_offset : target_offset + 3] = raw[
                source_offset : source_offset + 3
            ]
    write_png(path, width, height, output)
    return path


def preview_item(timeline, item, tag="current", width=360, height=203):
    capture = rb.capture_item_thumbnail(timeline, item)
    path = preview_from_capture(capture, tag, width, height)
    return path, capture


def preview_from_capture(capture, tag="current", width=360, height=203):
    folder = os.path.join(tempfile.gettempdir(), "ColorFlow", "previews")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(
        folder,
        "%s_%s.png" % (tag, time.time_ns()),
    )
    thumbnail_to_png(capture["thumbnail"], path, width, height)
    return path


def export_current_frame(project, tag="current", extension=".jpg"):
    """Export the exact frame under the playhead (with the current grade)."""
    folder = os.path.join(tempfile.gettempdir(), "ColorFlow", "frames")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "%s_%s%s" % (tag, time.time_ns(), extension))
    if not project.ExportCurrentFrameAsStill(path):
        raise RuntimeError(
            "Resolve 未能导出时间线当前帧，请确认已切到 Color 页面并停止播放。"
        )
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        raise RuntimeError("当前帧导出文件为空。")
    # Keep the temp preview folder bounded.
    try:
        files = sorted(
            (
                os.path.join(folder, name)
                for name in os.listdir(folder)
                if name.lower().endswith((".jpg", ".jpeg", ".png"))
            ),
            key=os.path.getmtime,
            reverse=True,
        )
        for old in files[30:]:
            os.remove(old)
    except Exception:
        pass
    return path


def preview_html(path, width):
    if not path:
        return '<span style="color:#6d7c8e;">无预览</span>'
    url = "file:///" + os.path.abspath(path).replace("\\", "/")
    return '<img src="%s" width="%d">' % (url, width)

