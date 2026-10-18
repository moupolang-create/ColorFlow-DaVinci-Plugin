"""Pure-Python thumbnail previews for the Resolve panel."""

import os
import struct
import tempfile
import time
import zlib
from pathlib import Path

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


def _paeth(left, above, upper_left):
    value = left + above - upper_left
    left_delta = abs(value - left)
    above_delta = abs(value - above)
    upper_left_delta = abs(value - upper_left)
    if left_delta <= above_delta and left_delta <= upper_left_delta:
        return left
    if above_delta <= upper_left_delta:
        return above
    return upper_left


def read_png_rgb(path):
    """Read a non-interlaced PNG and return (width, height, rgb_bytes)."""
    with open(path, "rb") as handle:
        data = handle.read()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("不是有效的 PNG 文件。")
    pos = 8
    width = height = None
    bit_depth = color_type = 0
    interlace = 0
    palette = None
    compressed = bytearray()
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        tag = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if tag == b"IHDR":
            (
                width,
                height,
                bit_depth,
                color_type,
                compression,
                filter_method,
                interlace,
            ) = struct.unpack(">IIBBBBB", chunk)
        elif tag == b"PLTE":
            palette = chunk
        elif tag == b"IDAT":
            compressed.extend(chunk)
        elif tag == b"IEND":
            break
    if not width or not height:
        raise ValueError("PNG 缺少有效尺寸。")
    if interlace:
        raise ValueError("暂不支持隔行 PNG，请另存为标准 PNG。")
    if bit_depth not in (8, 16):
        raise ValueError("暂不支持 %d-bit PNG。" % bit_depth)
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
    if channels is None:
        raise ValueError("暂不支持该 PNG 颜色类型。")
    sample_bytes = bit_depth // 8
    row_bytes = width * channels * sample_bytes
    raw = zlib.decompress(bytes(compressed))
    expected = height * (row_bytes + 1)
    if len(raw) < expected:
        raise ValueError("PNG 像素数据不完整。")
    rows = []
    previous = bytearray(row_bytes)
    offset = 0
    for _ in range(height):
        filter_type = raw[offset]
        offset += 1
        row = bytearray(raw[offset : offset + row_bytes])
        offset += row_bytes
        if filter_type == 1:
            for index in range(row_bytes):
                left = row[index - channels * sample_bytes] if index >= channels * sample_bytes else 0
                row[index] = (row[index] + left) & 0xFF
        elif filter_type == 2:
            for index in range(row_bytes):
                row[index] = (row[index] + previous[index]) & 0xFF
        elif filter_type == 3:
            for index in range(row_bytes):
                left = row[index - channels * sample_bytes] if index >= channels * sample_bytes else 0
                row[index] = (
                    row[index] + ((left + previous[index]) // 2)
                ) & 0xFF
        elif filter_type == 4:
            for index in range(row_bytes):
                left = row[index - channels * sample_bytes] if index >= channels * sample_bytes else 0
                upper_left = (
                    previous[index - channels * sample_bytes]
                    if index >= channels * sample_bytes
                    else 0
                )
                row[index] = (
                    row[index]
                    + _paeth(left, previous[index], upper_left)
                ) & 0xFF
        elif filter_type != 0:
            raise ValueError("PNG 使用了未知行过滤器。")
        rows.append(bytes(row))
        previous = row
    rgb = bytearray(width * height * 3)
    target = 0
    for row in rows:
        for x in range(width):
            index = x * channels * sample_bytes
            if color_type == 3:
                palette_index = row[index]
                if palette is None or palette_index * 3 + 2 >= len(palette):
                    raise ValueError("PNG 调色板数据不完整。")
                red = palette[palette_index * 3]
                green = palette[palette_index * 3 + 1]
                blue = palette[palette_index * 3 + 2]
            elif color_type in (0, 4):
                red = green = blue = row[index]
            else:
                red = row[index]
                green = row[index + sample_bytes]
                blue = row[index + 2 * sample_bytes]
            rgb[target : target + 3] = bytes((red, green, blue))
            target += 3
    return width, height, bytes(rgb)


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
    url = Path(os.path.abspath(path)).as_uri()
    return '<img src="%s" width="%d">' % (url, width)

