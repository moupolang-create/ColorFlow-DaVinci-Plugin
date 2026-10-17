"""Image statistics, corrective colour models and DCTL/CDL generation.

This module intentionally uses only the Python standard library. DaVinci
Resolve ships its own Python runtime, so relying on NumPy, Pillow or OpenCV
inside a Workflow Integration script is fragile.
"""

import base64
import math


PIVOT = 0.18


def ascii_label(value, fallback="correction"):
    """Sanitize DCTL filenames/comments to ASCII for Resolve's CTL compiler."""
    original = str(value or "")
    for chinese, english in (
        ("一键还原", "one_click_restore"),
        ("分节点还原", "split_restore"),
        ("自动白平衡", "auto_white_balance"),
        ("自动黑白场", "auto_black_white"),
        ("自动曝光", "auto_exposure"),
        ("白平衡", "white_balance"),
        ("曝光", "exposure"),
        ("色温", "temperature"),
        ("饱和", "saturation"),
        ("肤色", "skin"),
        ("匹配", "match"),
        ("还原", "restore"),
    ):
        if chinese in original:
            return english
    text = "".join(
        character
        if ord(character) < 128
        and (character.isalnum() or character in "._- ")
        else "_"
        for character in original
    )
    text = " ".join(text.split()).strip("._- ")
    return text[:80] or fallback


def clamp(value, low, high):
    return max(low, min(high, value))


def _finite(value, fallback=0.0):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return fallback
    if math.isnan(value) or math.isinf(value):
        return fallback
    return value


def srgb_to_linear(value):
    value = clamp(_finite(value), 0.0, 1.0)
    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def linear_to_srgb(value):
    value = max(0.0, _finite(value))
    if value <= 0.0031308:
        return 12.92 * value
    return 1.055 * (value ** (1.0 / 2.4)) - 0.055


def luma_linear(red, green, blue):
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _percentile(values, point):
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    index = clamp(point, 0.0, 1.0) * (len(values) - 1)
    low = int(math.floor(index))
    high = int(math.ceil(index))
    if low == high:
        return values[low]
    mix = index - low
    return values[low] * (1.0 - mix) + values[high] * mix


def _median(values):
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) * 0.5


def decode_thumbnail(thumbnail):
    """Return (width, height, raw_rgb_bytes, channels) for a Resolve thumb."""
    if not thumbnail:
        raise ValueError("没有可分析的画面缩略图。")
    width = int(thumbnail.get("width") or 0)
    height = int(thumbnail.get("height") or 0)
    if width <= 0 or height <= 0:
        raise ValueError("画面缩略图尺寸无效。")
    raw = base64.b64decode(thumbnail.get("data") or "")
    pixels = width * height
    if len(raw) == pixels * 3:
        channels = 3
    elif len(raw) == pixels * 4:
        channels = 4
    else:
        raise ValueError(
            "缩略图像素长度不匹配：%d bytes for %dx%d" % (len(raw), width, height)
        )
    return width, height, raw, channels


def analyze_thumbnail(thumbnail):
    width, height, raw, channels = decode_thumbnail(thumbnail)
    return analyze_pixels(width, height, raw, channels)


def analyze_pixels(width, height, raw, channels=3, sample_limit=70000):
    """Measure robust exposure, neutral-axis balance and contrast.

    The thumbnail is display-referred RGB. We decode it to linear light first,
    then use medians/percentiles so a large coloured wall or sky does not
    dominate the white-balance estimate.
    """
    total = width * height
    if total <= 0:
        raise ValueError("画面没有像素。")
    step = max(1, total // max(1000, int(sample_limit)))
    samples = []
    lumas = []
    for index in range(0, total, step):
        offset = index * channels
        red = raw[offset] / 255.0
        green = raw[offset + 1] / 255.0
        blue = raw[offset + 2] / 255.0
        red_lin = srgb_to_linear(red)
        green_lin = srgb_to_linear(green)
        blue_lin = srgb_to_linear(blue)
        y = luma_linear(red_lin, green_lin, blue_lin)
        high = max(red, green, blue)
        low = min(red, green, blue)
        saturation = (high - low) / max(high, 1e-6)
        samples.append((red, green, blue, red_lin, green_lin, blue_lin, y, saturation))
        lumas.append(y)
    if not samples:
        raise ValueError("画面没有可分析像素。")

    ordered_lumas = sorted(lumas)
    p12 = _percentile(ordered_lumas, 0.12)
    p01 = _percentile(ordered_lumas, 0.01)
    p15 = _percentile(ordered_lumas, 0.15)
    p50 = _percentile(ordered_lumas, 0.50)
    p85 = _percentile(ordered_lumas, 0.85)
    p88 = _percentile(ordered_lumas, 0.88)
    p99 = _percentile(ordered_lumas, 0.99)

    middle = [sample for sample in samples if p12 <= sample[6] <= p88]
    if not middle:
        middle = samples
    neutral = [sample for sample in middle if sample[7] <= 0.18]
    min_neutral = max(60, int(len(middle) * 0.025))
    used_neutral = len(neutral) >= min_neutral
    chosen = neutral if used_neutral else middle

    ratios_rg = []
    ratios_bg = []
    for sample in chosen:
        red_lin, green_lin, blue_lin = sample[3], sample[4], sample[5]
        ratios_rg.append(
            math.log2(max(red_lin, 1e-5) / max(green_lin, 1e-5))
        )
        ratios_bg.append(
            math.log2(max(blue_lin, 1e-5) / max(green_lin, 1e-5))
        )

    saturation = _median([sample[7] for sample in middle])
    contrast_stops = math.log2(max(p85, 1e-5) / max(p15, 1e-5))
    neutral_ratio = float(len(neutral)) / float(max(1, len(samples)))
    clipped_high_ratio = float(
        sum(1 for value in lumas if value >= 0.90)
    ) / float(max(1, len(lumas)))
    clipped_low_ratio = float(
        sum(1 for value in lumas if value <= 0.002)
    ) / float(max(1, len(lumas)))
    saturated_high_ratio = float(
        sum(1 for sample in samples if sample[7] >= 0.95)
    ) / float(max(1, len(samples)))
    mean_r = sum(sample[0] for sample in samples) / len(samples)
    mean_g = sum(sample[1] for sample in samples) / len(samples)
    mean_b = sum(sample[2] for sample in samples) / len(samples)

    return {
        "width": width,
        "height": height,
        "samples": len(samples),
        "neutral_samples": len(neutral),
        "neutral_ratio": neutral_ratio,
        "used_neutral": used_neutral,
        "p01": p01,
        "p15": p15,
        "p50": p50,
        "p85": p85,
        "p99": p99,
        "contrast_stops": contrast_stops,
        "rg": _median(ratios_rg),
        "bg": _median(ratios_bg),
        "saturation": saturation,
        "clipped_high_ratio": clipped_high_ratio,
        "clipped_low_ratio": clipped_low_ratio,
        "saturated_high_ratio": saturated_high_ratio,
        "mean_rgb": (mean_r, mean_g, mean_b),
        "mean_rgb_255": (
            int(round(mean_r * 255)),
            int(round(mean_g * 255)),
            int(round(mean_b * 255)),
        ),
    }


def _neutral_confidence(stats):
    if not stats.get("used_neutral"):
        return 0.45
    return clamp(stats.get("neutral_ratio", 0.0) / 0.06, 0.30, 1.0)


def restore_model(stats, strength=0.70, restore_tone=False):
    """Build a neutralising model that removes a cast and normalises exposure."""
    strength = clamp(_finite(strength, 0.70), 0.0, 1.0)
    confidence = _neutral_confidence(stats)
    exposure = clamp(
        math.log2(PIVOT / max(stats.get("p50", PIVOT), 1e-5)), -2.0, 2.0
    )
    white_rg = clamp(-_finite(stats.get("rg")), -0.30, 0.30)
    white_bg = clamp(-_finite(stats.get("bg")), -0.30, 0.30)
    contrast = 1.0
    saturation = 1.0
    if (
        restore_tone
        and _finite(stats.get("p85"), 0.0) > 0.02
        and _finite(stats.get("contrast_stops"), 0.0) > 0.20
    ):
        contrast = clamp(
            4.0 / max(_finite(stats.get("contrast_stops"), 4.0), 2.0),
            1.0,
            1.28,
        )
        saturation = clamp(
            0.22 / max(_finite(stats.get("saturation"), 0.22), 0.05),
            1.0,
            1.22,
        )
    return {
        "kind": "restore",
        "strength": strength,
        "confidence": confidence,
        "exposure_stops": exposure * strength,
        "wb_rg": white_rg * strength * confidence,
        "wb_bg": white_bg * strength * confidence,
        "contrast": 1.0 + (contrast - 1.0) * strength,
        "saturation": 1.0 + (saturation - 1.0) * strength,
        "source_p50": stats.get("p50", 0.0),
        "target_p50": PIVOT,
        "source_rg": stats.get("rg", 0.0),
        "source_bg": stats.get("bg", 0.0),
    }


def exposure_model(stats, strength=0.70):
    """Exposure-only correction used by the one-click exposure stretch."""
    strength = clamp(_finite(strength, 0.70), 0.0, 1.0)
    exposure = clamp(
        math.log2(PIVOT / max(stats.get("p50", PIVOT), 1e-5)), -2.5, 2.5
    )
    return {
        "kind": "exposure",
        "strength": strength,
        "confidence": 1.0,
        "exposure_stops": exposure * strength,
        "wb_rg": 0.0,
        "wb_bg": 0.0,
        "contrast": 1.0,
        "saturation": 1.0,
        "source_p50": stats.get("p50", 0.0),
        "target_p50": PIVOT,
    }


def white_balance_model(stats, strength=0.70):
    """Neutral-axis correction only, for a dedicated temperature node."""
    strength = clamp(_finite(strength, 0.70), 0.0, 1.0)
    confidence = _neutral_confidence(stats)
    return {
        "kind": "white_balance",
        "strength": strength,
        "confidence": confidence,
        "exposure_stops": 0.0,
        "wb_rg": clamp(-_finite(stats.get("rg")), -0.30, 0.30)
        * strength
        * confidence,
        "wb_bg": clamp(-_finite(stats.get("bg")), -0.30, 0.30)
        * strength
        * confidence,
        "contrast": 1.0,
        "saturation": 1.0,
        "source_rg": stats.get("rg", 0.0),
        "source_bg": stats.get("bg", 0.0),
    }


def saturation_model(stats, strength=0.70, restore_tone=True):
    """Saturation and flat-log contrast for a dedicated saturation node."""
    strength = clamp(_finite(strength, 0.70), 0.0, 1.0)
    contrast = 1.0
    saturation = 1.0
    if (
        restore_tone
        and _finite(stats.get("p85"), 0.0) > 0.02
        and _finite(stats.get("contrast_stops"), 0.0) > 0.20
    ):
        contrast = clamp(
            4.0 / max(_finite(stats.get("contrast_stops"), 4.0), 2.0),
            1.0,
            1.28,
        )
        saturation = clamp(
            0.22 / max(_finite(stats.get("saturation"), 0.22), 0.05),
            1.0,
            1.22,
        )
    return {
        "kind": "saturation",
        "strength": strength,
        "confidence": 1.0,
        "exposure_stops": 0.0,
        "wb_rg": 0.0,
        "wb_bg": 0.0,
        "contrast": 1.0 + (contrast - 1.0) * strength,
        "saturation": 1.0 + (saturation - 1.0) * strength,
        "source_saturation": stats.get("saturation", 0.0),
    }


def highlight_guard_model(stats, strength=0.70):
    """Conservative exposure reduction when highlights are near clipping.

    This cannot recover already-clipped source detail; it only reduces the
    chance of adding more clipping downstream.
    """
    strength = clamp(_finite(strength, 0.70), 0.0, 1.0)
    p99 = _finite(stats.get("p99"), 0.0)
    ratio = _finite(stats.get("clipped_high_ratio"), 0.0)
    stops = 0.0
    if p99 >= 0.90 or ratio >= 0.02:
        stops = clamp(math.log2(0.90 / max(p99, 0.90)), -0.80, 0.0)
    return {
        "kind": "highlight_guard",
        "strength": strength,
        "confidence": 1.0,
        "exposure_stops": stops * strength,
        "wb_rg": 0.0,
        "wb_bg": 0.0,
        "contrast": 1.0,
        "saturation": 1.0,
        "source_p99": p99,
        "source_clipped_high_ratio": ratio,
    }


def desaturation_model(stats, strength=0.50):
    """Small conservative saturation reduction for highly saturated frames."""
    strength = clamp(_finite(strength, 0.50), 0.0, 1.0)
    factor = 1.0
    if _finite(stats.get("saturated_high_ratio"), 0.0) >= 0.02:
        factor = 1.0 - 0.12 * strength
    return {
        "kind": "desaturation",
        "strength": strength,
        "confidence": 1.0,
        "exposure_stops": 0.0,
        "wb_rg": 0.0,
        "wb_bg": 0.0,
        "contrast": 1.0,
        "saturation": factor,
        "source_saturated_high_ratio": stats.get("saturated_high_ratio", 0.0),
    }


def combined_warning_model(stats, strength=0.70):
    """Combine technical warning fixes into one model for a blank node."""
    strength = clamp(_finite(strength, 0.70), 0.0, 1.0)
    model = {
        "kind": "warning_fix",
        "strength": strength,
        "confidence": 1.0,
        "exposure_stops": 0.0,
        "wb_rg": 0.0,
        "wb_bg": 0.0,
        "contrast": 1.0,
        "saturation": 1.0,
    }
    high = (
        _finite(stats.get("p99"), 0.0) >= 0.90
        or _finite(stats.get("clipped_high_ratio"), 0.0) >= 0.02
    )
    low = (
        _finite(stats.get("p01"), 1.0) <= 0.002
        or _finite(stats.get("clipped_low_ratio"), 0.0) >= 0.02
    )
    exposure = exposure_model(stats, strength)
    if high:
        model["exposure_stops"] = highlight_guard_model(stats, strength)[
            "exposure_stops"
        ]
    elif low or abs(exposure["exposure_stops"]) > 0.10:
        model["exposure_stops"] = exposure["exposure_stops"]

    white = white_balance_model(stats, strength)
    if abs(white["wb_rg"]) > 0.03 or abs(white["wb_bg"]) > 0.03:
        model["wb_rg"] = white["wb_rg"]
        model["wb_bg"] = white["wb_bg"]

    if _finite(stats.get("saturated_high_ratio"), 0.0) >= 0.02:
        model["saturation"] = desaturation_model(stats, strength)["saturation"]
    elif (
        _finite(stats.get("contrast_stops"), 4.0) < 3.5
        or _finite(stats.get("saturation"), 0.2) < 0.12
    ):
        tone = saturation_model(stats, strength, True)
        model["contrast"] = tone["contrast"]
        model["saturation"] = tone["saturation"]

    model["applied"] = (
        abs(model["exposure_stops"]) > 1e-4
        or abs(model["wb_rg"]) > 1e-4
        or abs(model["wb_bg"]) > 1e-4
        or abs(model["contrast"] - 1.0) > 1e-4
        or abs(model["saturation"] - 1.0) > 1e-4
    )
    return model


def match_model(reference, target, strength=0.70):
    """Match exposure, neutral axis, contrast and saturation to a reference."""
    strength = clamp(_finite(strength, 0.70), 0.0, 1.0)
    ref_conf = _neutral_confidence(reference)
    target_conf = _neutral_confidence(target)
    confidence = min(ref_conf, target_conf)

    exposure = clamp(
        math.log2(
            max(reference.get("p50", PIVOT), 1e-5)
            / max(target.get("p50", PIVOT), 1e-5)
        ),
        -2.0,
        2.0,
    )
    white_rg = clamp(
        _finite(reference.get("rg")) - _finite(target.get("rg")), -0.30, 0.30
    )
    white_bg = clamp(
        _finite(reference.get("bg")) - _finite(target.get("bg")), -0.30, 0.30
    )
    contrast = clamp(
        max(_finite(reference.get("contrast_stops"), 4.0), 0.50)
        / max(_finite(target.get("contrast_stops"), 4.0), 0.50),
        0.80,
        1.25,
    )
    saturation = clamp(
        max(_finite(reference.get("saturation"), 0.10), 0.05)
        / max(_finite(target.get("saturation"), 0.10), 0.05),
        0.80,
        1.25,
    )

    return {
        "kind": "match",
        "strength": strength,
        "confidence": confidence,
        "exposure_stops": exposure * strength,
        "wb_rg": white_rg * strength * confidence,
        "wb_bg": white_bg * strength * confidence,
        "contrast": 1.0 + (contrast - 1.0) * strength,
        "saturation": 1.0 + (saturation - 1.0) * strength,
        "source_p50": target.get("p50", 0.0),
        "target_p50": reference.get("p50", 0.0),
        "source_rg": target.get("rg", 0.0),
        "reference_rg": reference.get("rg", 0.0),
        "source_bg": target.get("bg", 0.0),
        "reference_bg": reference.get("bg", 0.0),
    }


def _white_balance_gains(model):
    red_gain = 2.0 ** _finite(model.get("wb_rg"))
    blue_gain = 2.0 ** _finite(model.get("wb_bg"))
    normal = 0.2126 * red_gain + 0.7152 + 0.0722 * blue_gain
    return red_gain / normal, blue_gain / normal


def model_to_cdl(model, node_index):
    """Convert the model to native ASC CDL values understood by Resolve."""
    exposure_gain = 2.0 ** _finite(model.get("exposure_stops"))
    red_gain, blue_gain = _white_balance_gains(model)
    slope = [
        clamp(exposure_gain * red_gain, 0.05, 8.0),
        clamp(exposure_gain, 0.05, 8.0),
        clamp(exposure_gain * blue_gain, 0.05, 8.0),
    ]
    contrast = clamp(_finite(model.get("contrast"), 1.0), 0.50, 2.0)
    if abs(contrast - 1.0) < 1e-4:
        offset = 0.0
    else:
        offset = PIVOT ** (1.0 / contrast) - PIVOT * slope[1]
    offset = clamp(offset, -0.20, 0.20)
    saturation = clamp(_finite(model.get("saturation"), 1.0), 0.0, 3.0)

    def triple(values):
        return " ".join("%.8f" % value for value in values)

    return {
        "NodeIndex": str(int(node_index)),
        "Slope": triple(slope),
        "Offset": triple([offset, offset, offset]),
        "Power": triple([contrast, contrast, contrast]),
        "Saturation": "%.8f" % saturation,
    }


def _dctl_decode_functions(space):
    if space == "dwg":
        return (
            "__DEVICE__ float cf_decode(float v) { return v > 0.02740668f ? cf_exp2(v / 0.07329248f - 7.0f) - 0.0075f : v / 10.44426855f; }\n"
            "__DEVICE__ float cf_encode(float v) { return v > 0.00262409f ? (cf_log2(v + 0.0075f) + 7.0f) * 0.07329248f : v * 10.44426855f; }\n"
        )
    return (
        "__DEVICE__ float cf_decode(float v) { return cf_pow(cf_max(v, 0.0f), 2.4f); }\n"
        "__DEVICE__ float cf_encode(float v) { return cf_pow(cf_max(v, 0.0f), 0.41666667f); }\n"
    )


def model_to_dctl(model, space="dwg", label=""):
    """Generate a self-contained DCTL for Resolve's node LUT/DCTL route."""
    space = "rec709" if space == "rec709" else "dwg"
    exposure_gain = 2.0 ** _finite(model.get("exposure_stops"))
    red_gain, blue_gain = _white_balance_gains(model)
    contrast = clamp(_finite(model.get("contrast"), 1.0), 0.50, 2.0)
    saturation = clamp(_finite(model.get("saturation"), 1.0), 0.0, 3.0)
    safe_label = ascii_label(label)
    header = [
        "// ColorFlow %s" % ("DWG scene correction" if space == "dwg" else "Rec.709 correction"),
        "// Generated model: exposure %.5f stops, WB(rg) %.5f, WB(bg) %.5f, contrast %.5f, saturation %.5f"
        % (
            _finite(model.get("exposure_stops")),
            _finite(model.get("wb_rg")),
            _finite(model.get("wb_bg")),
            contrast,
            saturation,
        ),
        "// %s" % safe_label,
        "",
        "__DEVICE__ float cf_pow(float a, float b) { return _powf(a, b); }",
        "__DEVICE__ float cf_log2(float v) { return _logf(v) / 0.69314718056f; }",
        "__DEVICE__ float cf_exp2(float v) { return _powf(2.0f, v); }",
        "__DEVICE__ float cf_max(float a, float b) { return a > b ? a : b; }",
        "__DEVICE__ float cf_luma(float3 rgb) { return rgb.x * 0.2126f + rgb.y * 0.7152f + rgb.z * 0.0722f; }",
        _dctl_decode_functions(space).rstrip(),
        "",
        "__DEVICE__ float3 transform(int p_Width, int p_Height, int p_X, int p_Y, float p_R, float p_G, float p_B) {",
        "    float3 linear = make_float3(cf_decode(p_R), cf_decode(p_G), cf_decode(p_B));",
        "    float gain = %.8ff;" % exposure_gain,
        "    float red_gain = %.8ff;" % red_gain,
        "    float blue_gain = %.8ff;" % blue_gain,
        "    float3 out = make_float3(linear.x * gain * red_gain, linear.y * gain, linear.z * gain * blue_gain);",
        "    float contrast = %.8ff;" % contrast,
        "    out.x = 0.18f * cf_pow(cf_max(out.x, 0.0f) / 0.18f, contrast);",
        "    out.y = 0.18f * cf_pow(cf_max(out.y, 0.0f) / 0.18f, contrast);",
        "    out.z = 0.18f * cf_pow(cf_max(out.z, 0.0f) / 0.18f, contrast);",
        "    float y = cf_luma(out);",
        "    float saturation = %.8ff;" % saturation,
        "    out = make_float3(y + (out.x - y) * saturation, y + (out.y - y) * saturation, y + (out.z - y) * saturation);",
        "    return make_float3(cf_encode(out.x), cf_encode(out.y), cf_encode(out.z));",
        "}",
        "",
    ]
    return "\n".join(header)


def tone_stretch_dctl(stats, strength=0.70, space="dwg", label="auto-black-white"):
    """A soft black/white point stretch DCTL."""
    space = "rec709" if space == "rec709" else "dwg"
    strength = clamp(_finite(strength, 0.70), 0.0, 1.0)
    black = clamp(_finite(stats.get("p01"), 0.0), 0.0, 0.25)
    white = clamp(_finite(stats.get("p99"), 1.0), 0.35, 4.0)
    if white - black < 0.08:
        black = clamp(_finite(stats.get("p15"), 0.0), 0.0, 0.25)
        white = clamp(_finite(stats.get("p85"), 1.0), 0.35, 4.0)
    safe_label = ascii_label(label)
    return "\n".join(
        [
            "// ColorFlow auto black/white point",
            "// black %.8f white %.8f strength %.4f" % (black, white, strength),
            "// %s" % safe_label,
            "",
            "__DEVICE__ float cf_pow(float a, float b) { return _powf(a, b); }",
            "__DEVICE__ float cf_log2(float v) { return _logf(v) / 0.69314718056f; }",
            "__DEVICE__ float cf_exp2(float v) { return _powf(2.0f, v); }",
            "__DEVICE__ float cf_max(float a, float b) { return a > b ? a : b; }",
            "__DEVICE__ float cf_mix(float a, float b, float t) { return a + (b - a) * t; }",
            _dctl_decode_functions(space).rstrip(),
            "",
            "__DEVICE__ float3 transform(int p_Width, int p_Height, int p_X, int p_Y, float p_R, float p_G, float p_B) {",
            "    float3 linear = make_float3(cf_decode(p_R), cf_decode(p_G), cf_decode(p_B));",
            "    float black = %.8ff;" % black,
            "    float white = %.8ff;" % white,
            "    float amount = %.8ff;" % strength,
            "    float3 stretched = make_float3("
            "(linear.x - black) / (white - black), "
            "(linear.y - black) / (white - black), "
            "(linear.z - black) / (white - black));",
            "    stretched.x = cf_max(stretched.x, 0.0f);",
            "    stretched.y = cf_max(stretched.y, 0.0f);",
            "    stretched.z = cf_max(stretched.z, 0.0f);",
            "    float3 out = make_float3(cf_mix(linear.x, stretched.x, amount), "
            "cf_mix(linear.y, stretched.y, amount), cf_mix(linear.z, stretched.z, amount));",
            "    return make_float3(cf_encode(out.x), cf_encode(out.y), cf_encode(out.z));",
            "}",
            "",
        ]
    )


def skin_dctl(
    hue_shift=0.0,
    saturation=0.0,
    lightness=0.0,
    background_desat=0.0,
    protect_skin=True,
    space="dwg",
    label="skin",
):
    """Generate a YCbCr skin-selective DCTL.

    Resolve's public API cannot create a native Qualifier node. This DCTL is a
    practical substitute: it detects skin-like chroma in display-referred
    YCbCr, applies a soft mask and can desaturate the rest of the frame.
    """
    space = "rec709" if space == "rec709" else "dwg"
    hue_shift = clamp(_finite(hue_shift), -60.0, 60.0)
    sat_factor = 1.0 + clamp(_finite(saturation), -100.0, 100.0) / 100.0
    light_factor = 1.0 + clamp(_finite(lightness), -100.0, 100.0) / 100.0
    bg = clamp(_finite(background_desat), 0.0, 1.0)
    angle = hue_shift * math.pi / 180.0
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    mask_expr = "skin" if protect_skin else "1.0f"
    safe_label = ascii_label(label)
    return "\n".join(
        [
            "// ColorFlow skin-selective YCbCr correction",
            "// hue %.3f sat %.3f light %.3f background %.3f protect %d"
            % (hue_shift, sat_factor, light_factor, bg, 1 if protect_skin else 0),
            "// %s" % safe_label,
            "",
            "__DEVICE__ float cf_pow(float a, float b) { return _powf(a, b); }",
            "__DEVICE__ float cf_log2(float v) { return _logf(v) / 0.69314718056f; }",
            "__DEVICE__ float cf_exp2(float v) { return _powf(2.0f, v); }",
            "__DEVICE__ float cf_max(float a, float b) { return a > b ? a : b; }",
            "__DEVICE__ float cf_min(float a, float b) { return a < b ? a : b; }",
            "__DEVICE__ float cf_mix(float a, float b, float t) { return a + (b - a) * t; }",
            "__DEVICE__ float cf_smooth(float e0, float e1, float x) { float t = cf_min(1.0f, cf_max(0.0f, (x - e0) / (e1 - e0))); return t * t * (3.0f - 2.0f * t); }",
            _dctl_decode_functions(space).rstrip(),
            "",
            "__DEVICE__ float3 transform(int p_Width, int p_Height, int p_X, int p_Y, float p_R, float p_G, float p_B) {",
            "    float3 lin = make_float3(cf_decode(p_R), cf_decode(p_G), cf_decode(p_B));",
            "    float3 disp = make_float3(cf_pow(cf_max(lin.x, 0.0f), 0.41666667f), cf_pow(cf_max(lin.y, 0.0f), 0.41666667f), cf_pow(cf_max(lin.z, 0.0f), 0.41666667f));",
            "    float y = 0.2126f * disp.x + 0.7152f * disp.y + 0.0722f * disp.z;",
            "    float cb = (disp.z - y) / 1.8556f;",
            "    float cr = (disp.x - y) / 1.5748f;",
            "    float mx = cf_max(disp.x, cf_max(disp.y, disp.z));",
            "    float mn = cf_min(disp.x, cf_min(disp.y, disp.z));",
            "    float sat = (mx - mn) / cf_max(mx, 0.0001f);",
            "    float skin = cf_smooth(0.035f, 0.11f, cr) * (1.0f - cf_smooth(0.32f, 0.43f, cr));",
            "    skin *= cf_smooth(-0.16f, -0.06f, cb) * (1.0f - cf_smooth(0.04f, 0.13f, cb));",
            "    skin *= cf_smooth(0.04f, 0.11f, y) * (1.0f - cf_smooth(0.86f, 0.99f, y));",
            "    skin *= cf_smooth(0.06f, 0.16f, sat) * (1.0f - cf_smooth(0.72f, 0.9f, sat));",
            "    float mask = %s;" % mask_expr,
            "    float cb2 = cb * %.8ff - cr * %.8ff;" % (cos_a, sin_a),
            "    float cr2 = cb * %.8ff + cr * %.8ff;" % (sin_a, cos_a),
            "    cb2 *= %.8ff; cr2 *= %.8ff;" % (sat_factor, sat_factor),
            "    float y2 = y * %.8ff;" % light_factor,
            "    float3 adjusted = make_float3(y2 + 1.5748f * cr2, y2 - 0.187324f * cb2 - 0.468124f * cr2, y2 + 1.8556f * cb2);",
            "    float3 mixed = make_float3(cf_mix(disp.x, adjusted.x, mask), cf_mix(disp.y, adjusted.y, mask), cf_mix(disp.z, adjusted.z, mask));",
            "    float gray = 0.2126f * mixed.x + 0.7152f * mixed.y + 0.0722f * mixed.z;",
            "    float bgAmount = %.5ff * (1.0f - mask);" % bg,
            "    mixed = make_float3(cf_mix(mixed.x, gray, bgAmount), cf_mix(mixed.y, gray, bgAmount), cf_mix(mixed.z, gray, bgAmount));",
            "    float3 outlin = make_float3(cf_pow(cf_max(mixed.x, 0.0f), 2.4f), cf_pow(cf_max(mixed.y, 0.0f), 2.4f), cf_pow(cf_max(mixed.z, 0.0f), 2.4f));",
            "    return make_float3(cf_encode(outlin.x), cf_encode(outlin.y), cf_encode(outlin.z));",
            "}",
            "",
        ]
    )


def apply_model_to_rgb(model, raw, channels=3):
    """Small CPU reference implementation used by the unit tests.

    This mirrors the DCTL maths in display-referred sRGB and is useful for
    checking that a model moves statistics in the intended direction.
    """
    exposure_gain = 2.0 ** _finite(model.get("exposure_stops"))
    red_gain, blue_gain = _white_balance_gains(model)
    contrast = clamp(_finite(model.get("contrast"), 1.0), 0.50, 2.0)
    saturation = clamp(_finite(model.get("saturation"), 1.0), 0.0, 3.0)
    output = bytearray(len(raw))
    for offset in range(0, len(raw), channels):
        linear = [
            srgb_to_linear(raw[offset] / 255.0) * exposure_gain * red_gain,
            srgb_to_linear(raw[offset + 1] / 255.0) * exposure_gain,
            srgb_to_linear(raw[offset + 2] / 255.0) * exposure_gain * blue_gain,
        ]
        linear = [
            PIVOT * (max(value, 0.0) / PIVOT) ** contrast for value in linear
        ]
        y = luma_linear(linear[0], linear[1], linear[2])
        linear = [y + (value - y) * saturation for value in linear]
        for channel in range(3):
            output[offset + channel] = int(
                round(clamp(linear_to_srgb(linear[channel]), 0.0, 1.0) * 255.0)
            )
        if channels == 4:
            output[offset + 3] = raw[offset + 3]
    return bytes(output)


def describe_stats(stats):
    mean = stats.get("mean_rgb_255", (0, 0, 0))
    return (
        "中间调 %.3f · 对比 %.2f stops · 中性轴 R/G %+.2f B/G %+.2f · 饱和 %.2f · 中性像素 %.1f%% · RGB %d/%d/%d"
        % (
            _finite(stats.get("p50")),
            _finite(stats.get("contrast_stops")),
            _finite(stats.get("rg")),
            _finite(stats.get("bg")),
            _finite(stats.get("saturation")),
            _finite(stats.get("neutral_ratio")) * 100.0,
            mean[0],
            mean[1],
            mean[2],
        )
    )


def describe_stats_en(stats):
    mean = stats.get("mean_rgb_255", (0, 0, 0))
    return (
        "Mid %.3f · Contrast %.2f stops · Neutral R/G %+.2f B/G %+.2f · "
        "Sat %.2f · Neutral %.1f%% · RGB %d/%d/%d"
        % (
            _finite(stats.get("p50")),
            _finite(stats.get("contrast_stops")),
            _finite(stats.get("rg")),
            _finite(stats.get("bg")),
            _finite(stats.get("saturation")),
            _finite(stats.get("neutral_ratio")) * 100.0,
            mean[0],
            mean[1],
            mean[2],
        )
    )


def describe_model(model):
    return (
        "曝光 %+.2fEV · 白平衡 R/G %+.3f B/G %+.3f · 对比 %.3f · 饱和 %.3f · 强度 %d%%"
        % (
            _finite(model.get("exposure_stops")),
            _finite(model.get("wb_rg")),
            _finite(model.get("wb_bg")),
            _finite(model.get("contrast"), 1.0),
            _finite(model.get("saturation"), 1.0),
            int(round(_finite(model.get("strength"), 1.0) * 100.0)),
        )
    )

