"""LUT thumbnail generation and gallery helpers.

Preview thumbnails are generated in pure Python for .cube LUTs. Other LUT
formats (DCTL, DAT, ILUT) are still listed but may not have a thumbnail.
"""

import hashlib
import os
import tempfile

from . import preview


PREVIEW_DIR = os.path.join(tempfile.gettempdir(), "ColorFlow", "lut_previews")
PREVIEW_VERSION = "3"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STANDARD_RGB_PATH = os.path.join(
    _ROOT, "assets", "lut_reference_480x270.rgb"
)


def synthetic_source(width=160, height=90):
    """A colour-bar + grayscale source used when no clip is available."""
    colors = [
        (235, 235, 235),
        (230, 210, 60),
        (60, 210, 210),
        (60, 200, 80),
        (210, 60, 210),
        (210, 60, 60),
        (60, 70, 210),
    ]
    raw = bytearray()
    for y in range(height):
        for x in range(width):
            if y < int(height * 0.65):
                index = min(len(colors) - 1, int(x * len(colors) / width))
                rgb = colors[index]
            else:
                value = int(18 + (x / max(1, width - 1)) * 220)
                rgb = (value, value, value)
            raw.extend(rgb)
    return width, height, bytes(raw), 3


def source_from_context(context):
    return standard_source()


def standard_source():
    candidates = [
        STANDARD_RGB_PATH,
        os.path.join(
            _ROOT, "ColorFlowLib", "assets", "lut_reference_480x270.rgb"
        ),
        os.path.join(
            _ROOT, "assets", "lut_reference_480x270.rgb"
        ),
    ]
    for path in candidates:
        try:
            raw = open(path, "rb").read()
            if len(raw) == 480 * 270 * 3:
                return 480, 270, raw, 3
        except Exception:
            continue
    return synthetic_source()


def _parse_cube(path):
    size3 = None
    size1 = None
    domain_min = [0.0, 0.0, 0.0]
    domain_max = [1.0, 1.0, 1.0]
    domain_1d = None
    domain_3d = None
    section = None
    data_1d = []
    data_3d = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                tokens = line.split()
                key = tokens[0].upper()
                if key == "LUT_3D_SIZE" and len(tokens) > 1:
                    size3 = int(tokens[1])
                    section = "3d"
                elif key == "LUT_1D_SIZE" and len(tokens) > 1:
                    size1 = int(tokens[1])
                    section = "1d"
                elif key in ("DOMAIN_MIN", "DOMAIN_MAX") and len(tokens) >= 4:
                    values = [float(value) for value in tokens[1:4]]
                    if key == "DOMAIN_MIN":
                        domain_min = values
                    else:
                        domain_max = values
                elif key in (
                    "LUT_1D_INPUT_RANGE",
                    "LUT_3D_INPUT_RANGE",
                ) and len(tokens) >= 2:
                    values = [float(value) for value in tokens[1:]]
                    if len(values) == 1:
                        values = [values[0], values[0]]
                    values = values[:2]
                    if key == "LUT_1D_INPUT_RANGE":
                        domain_1d = values
                    else:
                        domain_3d = values
                elif len(tokens) >= 3:
                    try:
                        values = [float(value) for value in tokens[:3]]
                    except ValueError:
                        continue
                    if section == "1d":
                        data_1d.extend(values)
                    elif section == "3d":
                        data_3d.extend(values)
    except Exception:
        return None
    range_1d = domain_1d or [domain_min[0], domain_max[0]]
    range_3d = domain_3d or [domain_min[0], domain_max[0]]
    if (
        size3
        and size3 > 1
        and len(data_3d) >= size3 ** 3 * 3
        and (not size1 or len(data_1d) >= size1 * 3)
    ):
        return {
            "type": "3d",
            "size": size3,
            "data": data_3d[: size3 ** 3 * 3],
            "shaper_size": size1 if data_1d else None,
            "shaper": (
                data_1d[: size1 * 3] if size1 and data_1d else None
            ),
            "shaper_min": range_1d[0],
            "shaper_max": range_1d[1],
            "min": range_3d[0],
            "max": range_3d[1],
        }
    if size1 and size1 > 1 and len(data_1d) >= size1 * 3:
        return {
            "type": "1d",
            "size": size1,
            "data": data_1d[: size1 * 3],
            "min": range_1d[0],
            "max": range_1d[1],
        }
    return None


def _domain(value, low, high):
    if high == low:
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def _shaper(cube, red, green, blue):
    size = cube.get("shaper_size")
    values = cube.get("shaper")
    if not size or not values:
        return red, green, blue
    low = cube["shaper_min"]
    high = cube["shaper_max"]
    result = []
    for channel, value in enumerate((red, green, blue)):
        value = _domain(value, low, high)
        position = value * (size - 1)
        low_index = int(position)
        high_index = min(size - 1, low_index + 1)
        fraction = position - low_index
        result.append(
            values[low_index * 3 + channel] * (1.0 - fraction)
            + values[high_index * 3 + channel] * fraction
        )
    return result[0], result[1], result[2]


def _lookup_3d(cube, red, green, blue):
    size = cube["size"]
    data = cube["data"]
    if cube.get("shaper"):
        red, green, blue = _shaper(cube, red, green, blue)
    red = _domain(red, cube["min"], cube["max"])
    green = _domain(green, cube["min"], cube["max"])
    blue = _domain(blue, cube["min"], cube["max"])
    last = size - 1
    x = red * last
    y = green * last
    z = blue * last
    x0, y0, z0 = int(x), int(y), int(z)
    x1, y1, z1 = min(last, x0 + 1), min(last, y0 + 1), min(last, z0 + 1)
    fx, fy, fz = x - x0, y - y0, z - z0

    def sample(ri, gi, bi, channel):
        # .cube stores red as the fastest-changing index.
        return data[((bi * size + gi) * size + ri) * 3 + channel]

    values = []
    for channel in range(3):
        c000 = sample(x0, y0, z0, channel)
        c100 = sample(x1, y0, z0, channel)
        c010 = sample(x0, y1, z0, channel)
        c110 = sample(x1, y1, z0, channel)
        c001 = sample(x0, y0, z1, channel)
        c101 = sample(x1, y0, z1, channel)
        c011 = sample(x0, y1, z1, channel)
        c111 = sample(x1, y1, z1, channel)
        c00 = c000 + (c100 - c000) * fx
        c10 = c010 + (c110 - c010) * fx
        c01 = c001 + (c101 - c001) * fx
        c11 = c011 + (c111 - c011) * fx
        c0 = c00 + (c10 - c00) * fy
        c1 = c01 + (c11 - c01) * fy
        values.append(c0 + (c1 - c0) * fz)
    return values


def _lookup_1d(cube, red, green, blue):
    size = cube["size"]
    data = cube["data"]
    positions = []
    for value in (red, green, blue):
        value = _domain(value, cube["min"], cube["max"])
        positions.append(value * (size - 1))
    low = [min(size - 1, int(value)) for value in positions]
    high = [min(size - 1, value + 1) for value in low]
    fractions = [
        value - low[index] for index, value in enumerate(positions)
    ]
    result = []
    for channel in range(3):
        result.append(
            data[low[channel] * 3 + channel]
            * (1.0 - fractions[channel])
            + data[high[channel] * 3 + channel] * fractions[channel]
        )
    return result


def _apply_cube(cube, source, width=160, height=90):
    src_w, src_h, raw, channels = source
    output = bytearray(width * height * 3)
    for y in range(height):
        sy = min(src_h - 1, int(y * src_h / height))
        for x in range(width):
            sx = min(src_w - 1, int(x * src_w / width))
            offset = (sy * src_w + sx) * channels
            red = raw[offset] / 255.0
            green = raw[offset + 1] / 255.0
            blue = raw[offset + 2] / 255.0
            if cube["type"] == "3d":
                rgb = _lookup_3d(cube, red, green, blue)
            else:
                rgb = _lookup_1d(cube, red, green, blue)
            target = (y * width + x) * 3
            output[target] = int(max(0.0, min(1.0, rgb[0])) * 255)
            output[target + 1] = int(max(0.0, min(1.0, rgb[1])) * 255)
            output[target + 2] = int(max(0.0, min(1.0, rgb[2])) * 255)
    return width, height, bytes(output)


def generate_cube_preview(path, source, width=240, height=135):
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    source_hash = hashlib.md5(
        source[2][:8192] + bytes([source[0] % 256, source[1] % 256])
    ).hexdigest()[:10]
    try:
        stat = os.stat(path)
        stamp = "%s-%s" % (stat.st_mtime_ns, stat.st_size)
    except Exception:
        stamp = "0"
    key = hashlib.md5(
        (
            os.path.abspath(path)
            + stamp
            + source_hash
            + PREVIEW_VERSION
            + "%dx%d" % (width, height)
        ).encode("utf-8")
    ).hexdigest()[:16]
    target = os.path.join(PREVIEW_DIR, "lut_%s.png" % key)
    if os.path.exists(target):
        return target
    cube = _parse_cube(path)
    if cube is None:
        return None
    out_width, out_height, rgb = _apply_cube(
        cube, source, width, height
    )
    preview.write_png(target, out_width, out_height, rgb)
    return target


def build_entries(entries, source, limit=48, progress=None):
    selected = entries[:limit]
    result = []
    for index, entry in enumerate(selected):
        preview_path = None
        if entry["absolute"].lower().endswith(".cube"):
            try:
                preview_path = generate_cube_preview(
                    entry["absolute"], source, 240, 135
                )
            except Exception:
                preview_path = None
        item = dict(entry)
        item["preview"] = preview_path
        result.append(item)
        if progress:
            progress(index + 1, len(selected))
    # Keep the temp preview folder bounded.
    try:
        files = sorted(
            (
                os.path.join(PREVIEW_DIR, name)
                for name in os.listdir(PREVIEW_DIR)
                if name.endswith(".png")
            ),
            key=os.path.getmtime,
            reverse=True,
        )
        for old in files[300:]:
            os.remove(old)
    except Exception:
        pass
    return result

