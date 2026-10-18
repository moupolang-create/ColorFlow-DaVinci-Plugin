"""Higher-level ColorFlow features built on top of the Resolve bridge."""

import glob
import hashlib
import html
import base64
import json
import os
import re
import shutil
import tempfile
import time
from datetime import datetime

from . import analysis
from . import preview
from . import resolve_bridge as rb
from .timeline_tools import parse_fps, parse_resolution


DOCUMENTS = os.path.join(os.path.expanduser("~"), "Documents", "ColorFlow")
PRESET_DIR = os.path.join(DOCUMENTS, "Presets")
REPORT_DIR = os.path.join(DOCUMENTS, "Reports")
TEMPLATE_DIR = os.path.join(DOCUMENTS, "Templates")
ACTIVE_TEMPLATE_PATH = os.path.join(TEMPLATE_DIR, "active_template.txt")
LABELED_TEMPLATE_DIR = os.path.join(TEMPLATE_DIR, ".labeled")
BACKUP_DIR = os.path.join(DOCUMENTS, "Backups")
LAST_BATCH_PATH = os.path.join(BACKUP_DIR, "last_batch.json")
INDEX_PATH = os.path.join(PRESET_DIR, "index.json")
REFERENCE_DIR = os.path.join(tempfile.gettempdir(), "ColorFlow", "reference")
GALLERY_REFERENCE_ALBUM = "ColorFlow References"
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROGRAM_DATA = os.environ.get("PROGRAMDATA") or r"C:\ProgramData"
GRADEPILOT_TEMPLATE = os.path.join(
    PROGRAM_DATA,
    "Blackmagic Design",
    "DaVinci Resolve",
    "Support",
    "Workflow Integration Plugins",
    "com.onv13.gradepilot",
    "assets",
    "node-templates",
    "onv13_five_node_template.drx",
)


def _ensure_dirs():
    for directory in (PRESET_DIR, REPORT_DIR, TEMPLATE_DIR, BACKUP_DIR):
        os.makedirs(directory, exist_ok=True)


def _safe_name(value):
    text = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", str(value or "")).strip("_")
    return text[:60] or "ColorFlow"


def _meta_items(props, meta):
    items = []
    for source in (props, meta):
        if not source:
            continue
        for key, value in source.items():
            if value in (None, "", 0, "0"):
                continue
            items.append((str(key), str(value)))
    return items


def _find_value(props, meta, needles):
    for key, value in _meta_items(props, meta):
        lowered = ("%s %s" % (key, value)).lower()
        if any(needle in lowered for needle in needles):
            return value
    return ""


def detect_log(props, meta, name=""):
    text = " ".join(
        [name]
        + ["%s %s" % (key, value) for key, value in _meta_items(props, meta)]
    ).lower()
    patterns = [
        ("SLog3", ("slog3", "s-log3", "slog 3")),
        ("SLog2", ("slog2", "s-log2", "slog 2")),
        ("ARRI LogC3", ("logc3", "logc 3", "log c3")),
        ("ARRI LogC4", ("logc4", "logc 4")),
        ("ARRI LogC", ("arri logc", "logc")),
        ("HLG", ("hlg", "hybrid log")),
        ("CLog3", ("clog3", "c-log3", "canon log 3", "canon-log-3")),
        ("CLog2", ("clog2", "c-log2", "canon log 2", "canon-log-2")),
        ("CLog", ("clog", "c-log", "canon log")),
        ("VLog", ("vlog", "v-log")),
        ("DLog", ("dlog", "d-log")),
        ("Log", ("log",)),
    ]
    for label, needles in patterns:
        if any(needle in text for needle in needles):
            return {"name": label, "recognized": True, "source": "元数据/文件名"}
    if "rec.709" in text or "rec709" in text or "gamma 2.4" in text:
        return {"name": "Rec.709", "recognized": True, "source": "元数据"}
    return {"name": "未识别", "recognized": False, "source": "元数据"}


def timeline_mismatch(timeline, props):
    messages = []
    if timeline is None:
        return messages
    try:
        timeline_w = int(timeline.GetSetting("timelineResolutionWidth") or 0)
        timeline_h = int(timeline.GetSetting("timelineResolutionHeight") or 0)
    except Exception:
        timeline_w = timeline_h = 0
    source = parse_resolution(props.get("Resolution"))
    if source and timeline_w and timeline_h and source != (timeline_w, timeline_h):
        messages.append(
            "素材 %dx%d 与时间线 %dx%d 不一致" % (source[0], source[1], timeline_w, timeline_h)
        )
    try:
        timeline_fps = float(timeline.GetSetting("timelineFrameRate") or 0.0)
    except Exception:
        timeline_fps = 0.0
    source_fps = parse_fps(props.get("FPS"))
    if source_fps and timeline_fps and abs(source_fps - timeline_fps) > 0.01:
        messages.append(
            "素材 %.3f fps 与时间线 %.3f fps 不一致" % (source_fps, timeline_fps)
        )
    return messages


def clip_info(clip, timeline=None, thumbnail=None):
    try:
        props = clip.GetClipProperty() or {}
    except Exception:
        props = {}
    try:
        meta = clip.GetMetadata() or {}
    except Exception:
        meta = {}
    resolution = props.get("Resolution") or _find_value(props, meta, ("resolution",))
    fps = props.get("FPS") or _find_value(props, meta, ("frame rate", "fps"))
    codec = props.get("Video Codec") or _find_value(props, meta, ("codec", "format"))
    bit_depth = _find_value(
        props, meta, ("bit depth", "bit-depth", "color depth", "bits per")
    )
    white_balance = _find_value(
        props,
        meta,
        ("white balance", "color temperature", "colour temperature", "wb ", " kelvin"),
    )
    log = detect_log(props, meta, clip.GetName())
    warnings = timeline_mismatch(timeline, props)
    stats = None
    if thumbnail:
        try:
            stats = analysis.analyze_thumbnail(thumbnail)
        except Exception:
            stats = None
    if stats:
        if stats.get("p99", 0.0) >= 0.90 or stats.get("clipped_high_ratio", 0.0) >= 0.02:
            warnings.append("高光接近裁切")
        if stats.get("p01", 1.0) <= 0.002 or stats.get("clipped_low_ratio", 0.0) >= 0.02:
            warnings.append("暗部接近裁切")
        if stats.get("saturated_high_ratio", 0.0) >= 0.02:
            warnings.append("高饱和/色域越界风险")
    return {
        "name": clip.GetName(),
        "resolution": str(resolution or "—"),
        "fps": str(fps or "—"),
        "codec": str(codec or "—"),
        "bit_depth": str(bit_depth or "—"),
        "white_balance": str(white_balance or "—"),
        "log": log,
        "warnings": warnings,
        "stats": stats,
        "props": props,
        "meta": meta,
    }


def current_clip_info(app_context):
    timeline = app_context.get("timeline")
    item = app_context.get("clip")
    if timeline is None or item is None:
        raise rb.ColorFlowError("请先打开时间线并选中一个视频镜头。")
    media = None
    try:
        media = item.GetMediaPoolItem()
    except Exception:
        media = None
    capture = rb.capture_item_thumbnail(timeline, item)
    return clip_info(media or item, timeline, capture.get("thumbnail"))


def scan_luts(limit=1800):
    root = rb.lut_root()
    extensions = (".cube", ".dat", ".dctl", ".ilut", ".olut", ".3dl")
    results = []
    for base, dirs, files in os.walk(root):
        depth = base[len(root):].count(os.sep)
        if depth > 4:
            dirs[:] = []
            continue
        dirs[:] = [name for name in dirs if not name.startswith(".")]
        for filename in files:
            if not filename.lower().endswith(extensions):
                continue
            absolute = os.path.join(base, filename)
            relative = os.path.relpath(absolute, root).replace("\\", "/")
            lowered = relative.lower()
            if "slog" in lowered or "s-log" in lowered or "sony" in lowered:
                category = "SLog3"
            elif "arri" in lowered or "logc" in lowered:
                category = "ARRI"
            elif "hlg" in lowered:
                category = "HLG"
            elif "clog" in lowered or "canon" in lowered:
                category = "CLog"
            elif "rec709" in lowered or "rec.709" in lowered:
                category = "Rec.709"
            else:
                category = "自定义"
            results.append(
                {
                    "name": filename,
                    "relative": relative,
                    "absolute": absolute,
                    "category": category,
                }
            )
            if len(results) >= limit:
                return results
    results.sort(key=lambda item: (item["category"], item["relative"].lower()))
    return results


def import_lut(path):
    root = rb.lut_root()
    absolute = os.path.abspath(path)
    try:
        relative = os.path.relpath(absolute, root).replace("\\", "/")
        if not relative.startswith(".."):
            return absolute, relative
    except Exception:
        pass
    target_dir = os.path.join(root, "ColorFlow", "UserLUTs")
    os.makedirs(target_dir, exist_ok=True)
    target = os.path.join(target_dir, os.path.basename(absolute))
    shutil.copy2(absolute, target)
    return target, "ColorFlow/UserLUTs/" + os.path.basename(absolute)


def clear_lut(clip, node_index):
    graph = clip.GetNodeGraph()
    if graph is None:
        raise rb.ColorFlowError("当前镜头没有节点图。")
    graph.SetNodeEnabled(int(node_index), True)
    try:
        graph.SetLUT(int(node_index), "")
    except Exception as exc:
        raise rb.ColorFlowError("移除 LUT 失败：%s" % exc)
    if str(graph.GetLUT(int(node_index)) or "").strip():
        raise rb.ColorFlowError("Resolve 未确认移除 LUT。")
    return True


def auto_node_index(clip, role="primary"):
    nodes = rb.list_nodes(clip)
    if not nodes:
        raise rb.ColorFlowError("当前镜头没有节点。")
    if role == "match":
        empty = [node for node in nodes if node.get("likely_empty")]
        if empty:
            return empty[-1]["index"]
        managed = [node for node in nodes if node.get("managed")]
        if managed:
            return managed[-1]["index"]
        return nodes[-1]["index"]
    role_index = {
        "input": 1,
        "denoise": 1,
        "exposure": 2,
        "temperature": 3,
        "saturation": 4,
        "primary": 3,
        "skin": 4,
        "style": 5,
    }.get(role)
    if role_index and len(nodes) >= role_index:
        return role_index
    empty = [node for node in nodes if node.get("likely_empty")]
    if empty:
        return empty[-1]["index"]
    managed = [node for node in nodes if node.get("managed")]
    if managed:
        return managed[-1]["index"]
    return nodes[-1]["index"]


def apply_dctl_text(project, clip, node_index, text, label):
    path, relative = rb.write_dctl(text, label)
    return rb.apply_lut(project, clip, int(node_index), path, relative)


def warning_fix_node_index(clip):
    """Pick a blank node at/after 05, leaving the last blank for matching."""
    nodes = rb.list_nodes(clip)
    blanks = [
        node
        for node in nodes
        if node.get("likely_empty") and int(node["index"]) >= 5
    ]
    if not blanks:
        raise rb.ColorFlowError(
            "警告修复需要空白节点。请在 Color 页面 04 之后添加一个空白节点；"
            "如果还要做匹配，请再保留最后一个空白节点。"
        )
    return blanks[0]["index"], len(blanks)


def apply_model(project, clip, node_index, model, space_key, label):
    if space_key == "dwg":
        text = analysis.model_to_dctl(model, "dwg", label)
        return apply_dctl_text(project, clip, node_index, text, label)
    cdl = analysis.model_to_cdl(model, int(node_index))
    try:
        return rb.apply_cdl(clip, int(node_index), cdl)
    except Exception:
        text = analysis.model_to_dctl(model, "rec709", label)
        return apply_dctl_text(project, clip, node_index, text, label)


def apply_tone_stretch(project, clip, node_index, stats, strength, space_key, label):
    text = analysis.tone_stretch_dctl(stats, strength, space_key, label)
    return apply_dctl_text(project, clip, node_index, text, label)


def apply_skin(project, clip, node_index, hue, saturation, lightness, bg_desat, space_key, label):
    text = analysis.skin_dctl(
        hue,
        saturation,
        lightness,
        bg_desat,
        True,
        space_key,
        label,
    )
    return apply_dctl_text(project, clip, node_index, text, label)


def _load_index():
    _ensure_dirs()
    try:
        with open(INDEX_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def _save_index(entries):
    _ensure_dirs()
    with open(INDEX_PATH, "w", encoding="utf-8") as handle:
        json.dump(entries, handle, ensure_ascii=False, indent=2)


def list_presets():
    entries = _load_index()
    for entry in entries:
        entry["exists"] = os.path.exists(entry.get("file", ""))
    return entries


def save_preset_with_project(project, timeline, name, category):
    _ensure_dirs()
    safe = _safe_name(name)
    still = timeline.GrabStill()
    if still is None:
        raise rb.ColorFlowError("无法抓取当前镜头静帧，请先切换到 Color 页面。")
    gallery = project.GetGallery()
    album = gallery.GetCurrentStillAlbum()
    if album is None:
        album = gallery.CreateGalleryStillAlbum()
    if album is None:
        raise rb.ColorFlowError("无法创建静帧相册，DRX 预设保存失败。")
    before = set(glob.glob(os.path.join(PRESET_DIR, "*.drx")))
    if not album.ExportStills([still], PRESET_DIR, safe, "drx"):
        raise rb.ColorFlowError("Resolve 未能导出 DRX 预设。")
    after = set(glob.glob(os.path.join(PRESET_DIR, "*.drx")))
    created = sorted(after - before, key=os.path.getmtime)
    if not created:
        candidates = sorted(
            glob.glob(os.path.join(PRESET_DIR, safe + "*.drx")),
            key=os.path.getmtime,
        )
        if candidates:
            created = [candidates[-1]]
    if not created:
        raise rb.ColorFlowError("没有找到导出的 DRX 文件。")
    path = created[-1]
    entries = _load_index()
    entries = [entry for entry in entries if entry.get("file") != path]
    entry = {
        "key": os.path.basename(path),
        "name": name or safe,
        "category": category or "未分类",
        "favorite": False,
        "file": path,
        "created": datetime.now().isoformat(timespec="seconds"),
    }
    entries.append(entry)
    _save_index(entries)
    return entry


def toggle_favorite(key):
    entries = _load_index()
    for entry in entries:
        if entry.get("key") == key:
            entry["favorite"] = not bool(entry.get("favorite"))
    _save_index(entries)
    return list_presets()


def save_batch_manifest(operation, timeline, backups):
    """Persist a batch rollback manifest outside the Resolve UI session."""
    _ensure_dirs()
    entries = []
    for clip, version_name, version_type in backups:
        if not version_name:
            continue
        try:
            entries.append(
                {
                    "clip_id": clip.GetUniqueId(),
                    "name": clip.GetName(),
                    "version": version_name,
                    "type": int(version_type or 0),
                }
            )
        except Exception:
            continue
    if not entries:
        return None
    data = {
        "operation": operation,
        "created": datetime.now().isoformat(timespec="seconds"),
        "timeline_id": timeline.GetUniqueId() if timeline else "",
        "timeline_name": timeline.GetName() if timeline else "",
        "entries": entries,
    }
    with open(LAST_BATCH_PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    return data


def load_batch_manifest():
    try:
        with open(LAST_BATCH_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict) and isinstance(data.get("entries"), list):
            return data
    except Exception:
        pass
    return None


def clear_batch_manifest():
    try:
        os.remove(LAST_BATCH_PATH)
    except Exception:
        pass


def restore_batch_manifest(timeline, data):
    """Restore the previous versions listed in a persisted batch manifest."""
    if not data:
        raise rb.ColorFlowError("没有可回退的批量匹配记录。")
    entries = data.get("entries") or []
    if not entries:
        raise rb.ColorFlowError("批量回退记录为空。")
    items = rb.video_items(timeline, "timeline", None)
    by_id = {}
    for item in items:
        try:
            by_id[item.GetUniqueId()] = item
        except Exception:
            pass
    restored = []
    failed = []
    for entry in entries:
        item = by_id.get(entry.get("clip_id"))
        if item is None:
            failed.append((entry.get("name", "未知镜头"), "当前时间线找不到该片段"))
            continue
        try:
            if rb.restore_version(item, entry.get("version"), entry.get("type", 0)):
                restored.append(entry.get("name", item.GetName()))
            else:
                failed.append((entry.get("name", item.GetName()), "Resolve 未载入该版本"))
        except Exception as exc:
            failed.append((entry.get("name", item.GetName()), str(exc)))
    return restored, failed


def save_template_preserve(project, timeline, name="ColorFlow_5node"):
    """Save the current node chain (including denoise/tools) as a template.

    Unlike create_template_from_timeline(), this does not reset grades. The
    user must prepare node 1 as denoise and nodes 2-5 as the desired structure
    before saving.
    """
    _ensure_dirs()
    safe = _safe_name(name) + "_" + datetime.now().strftime("%H%M%S")
    still = timeline.GrabStill()
    if still is None:
        raise rb.ColorFlowError("无法抓取当前节点链，请先切换到 Color 页面。")
    gallery = project.GetGallery()
    album = gallery.GetCurrentStillAlbum()
    if album is None:
        album = gallery.CreateGalleryStillAlbum()
    if album is None:
        raise rb.ColorFlowError("无法创建静帧相册，节点模板保存失败。")
    before = set(glob.glob(os.path.join(TEMPLATE_DIR, "*.drx")))
    if not album.ExportStills([still], TEMPLATE_DIR, safe, "drx"):
        raise rb.ColorFlowError("Resolve 未能导出节点模板。")
    after = set(glob.glob(os.path.join(TEMPLATE_DIR, "*.drx")))
    created = sorted(after - before, key=os.path.getmtime)
    if not created:
        candidates = sorted(
            glob.glob(os.path.join(TEMPLATE_DIR, safe + "*.drx")),
            key=os.path.getmtime,
        )
        if candidates:
            created = [candidates[-1]]
    if not created:
        raise rb.ColorFlowError("没有找到导出的模板 DRX 文件。")
    set_active_template(created[-1])
    return created[-1]


def delete_preset(key):
    entries = _load_index()
    removed = None
    keep = []
    for entry in entries:
        if entry.get("key") == key:
            removed = entry
        else:
            keep.append(entry)
    if removed and removed.get("file") and os.path.exists(removed["file"]):
        os.remove(removed["file"])
    _save_index(keep)
    return list_presets()


def apply_preset(project, clip, path):
    if not os.path.exists(path):
        raise rb.ColorFlowError("预设文件不存在：%s" % path)
    graph = clip.GetNodeGraph()
    if graph is None:
        raise rb.ColorFlowError("当前镜头没有节点图。")
    if not graph.ApplyGradeFromDRX(path, 0):
        raise rb.ColorFlowError("Resolve 未能应用 DRX 预设。")
    return True


def find_template():
    _ensure_dirs()
    candidates = []
    try:
        with open(ACTIVE_TEMPLATE_PATH, "r", encoding="utf-8") as handle:
            active = handle.read().strip()
        if active and os.path.isfile(active):
            candidates.append(active)
    except Exception:
        pass
    user_templates = sorted(
        glob.glob(os.path.join(TEMPLATE_DIR, "*.drx")),
        key=os.path.getmtime,
        reverse=True,
    )
    preferred = [
        path
        for path in user_templates
        if "5node" in os.path.basename(path).lower()
        or "five_node" in os.path.basename(path).lower()
    ]
    candidates.extend(preferred)
    candidates.extend(user_templates)
    candidates.extend(
        sorted(
            glob.glob(
                os.path.join(PLUGIN_ROOT, "assets", "node-templates", "*.drx")
            ),
            key=os.path.getmtime,
            reverse=True,
        )
    )
    candidates.append(GRADEPILOT_TEMPLATE)
    seen = set()
    for path in candidates:
        absolute = os.path.abspath(path)
        if absolute in seen or not os.path.isfile(absolute):
            continue
        seen.add(absolute)
        return absolute
    return None


def set_active_template(path):
    _ensure_dirs()
    with open(ACTIVE_TEMPLATE_PATH, "w", encoding="utf-8") as handle:
        handle.write(os.path.abspath(path))


def _read_varint(data, pos):
    value = 0
    shift = 0
    while pos < len(data):
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, pos
        shift += 7
    raise ValueError("invalid varint")


def _encode_varint(value):
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _split_proto_fields(data):
    fields = []
    pos = 0
    while pos < len(data):
        start = pos
        key = data[pos]
        pos += 1
        wire = key & 7
        if wire == 0:
            _, pos = _read_varint(data, pos)
        elif wire == 2:
            length, pos = _read_varint(data, pos)
            pos += length
        elif wire == 1:
            pos += 8
        elif wire == 5:
            pos += 4
        else:
            raise ValueError("unsupported protobuf wire type")
        if pos > len(data):
            raise ValueError("truncated protobuf field")
        fields.append((key, data[start:pos]))
    return fields


def _template_payload(body):
    fields = _split_proto_fields(body)
    if not fields or fields[0][0] != 0x0A:
        raise ValueError("unexpected template body")
    encoded = fields[0][1]
    length, start = _read_varint(encoded, 1)
    payload = encoded[start:]
    if len(payload) != length:
        raise ValueError("template body length mismatch")
    return payload


def _template_node_count(body):
    return sum(
        1 for key, _ in _split_proto_fields(_template_payload(body)) if key == 0x3A
    )


def default_restore_labels(node_count):
    labels = {
        1: "01 降噪",
        2: "02 曝光",
        3: "03 色温",
        4: "04 饱和",
    }
    for index in range(5, int(node_count) + 1):
        labels[index] = (
            "%02d 匹配" % index
            if index == int(node_count)
            else "%02d 备用" % index
        )
    return labels


def _relabel_template_body(body, labels):
    payload = _template_payload(body)
    rebuilt = []
    node_index = 0
    for key, encoded in _split_proto_fields(payload):
        if key != 0x3A:
            rebuilt.append(encoded)
            continue
        node_index += 1
        length, start = _read_varint(encoded, 1)
        node = encoded[start:]
        if len(node) != length:
            raise ValueError("node body length mismatch")
        node_fields = [
            item for item in _split_proto_fields(node) if item[0] != 0x32
        ]
        label = labels.get(node_index)
        if label:
            raw_label = str(label).encode("utf-8")
            node_fields.append(
                (
                    0x32,
                    b"\x32"
                    + _encode_varint(len(raw_label))
                    + raw_label,
                )
            )
        new_node = b"".join(item for _, item in node_fields)
        rebuilt.append(
            b"\x3a" + _encode_varint(len(new_node)) + new_node
        )
    new_payload = b"".join(rebuilt)
    return b"\x0a" + _encode_varint(len(new_payload)) + new_payload


def prepare_labeled_template(path, labels=None):
    """Return a cached DRX copy whose node labels match ColorFlow roles."""
    if not path or not os.path.isfile(path):
        return path
    try:
        import zstandard
    except Exception:
        return path
    try:
        data = open(path, "rb").read()
        match = re.search(rb"<Body>([0-9a-fA-F]+)</Body>", data)
        if not match:
            return path
        raw = bytes.fromhex(match.group(1).decode("ascii"))
        body = zstandard.ZstdDecompressor().decompress(
            raw[1:], max_output_size=10 * 1024 * 1024
        )
        node_count = _template_node_count(body)
        if node_count < 1:
            return path
        chosen = labels or default_restore_labels(node_count)
        os.makedirs(LABELED_TEMPLATE_DIR, exist_ok=True)
        stamp = "%s-%s" % (os.path.getmtime(path), os.path.getsize(path))
        key = hashlib.md5(
            (
                os.path.abspath(path)
                + stamp
                + json.dumps(chosen, sort_keys=True)
            ).encode("utf-8")
        ).hexdigest()[:12]
        target = os.path.join(
            LABELED_TEMPLATE_DIR,
            "%s_%s.drx" % (_safe_name(os.path.basename(path))[:40], key),
        )
        if os.path.isfile(target):
            return target
        new_body = _relabel_template_body(body, chosen)
        compressed = b"\x81" + zstandard.ZstdCompressor().compress(new_body)
        data = (
            data[: match.start(1)]
            + compressed.hex().encode("ascii")
            + data[match.end(1) :]
        )
        with open(target, "wb") as handle:
            handle.write(data)
        return target
    except Exception:
        return path


def create_template_from_timeline(project, timeline, name="ColorFlow_5node"):
    """Create an empty node-graph template from a duplicated timeline.

    This uses the user's existing multi-node graph as the structure, resets all
    grades on a duplicate, exports a DRX and deletes the duplicate. It never
    modifies the original timeline.
    """
    _ensure_dirs()
    duplicate = timeline.DuplicateTimeline(
        "ColorFlow Template " + datetime.now().strftime("%H%M%S")
    )
    if duplicate is None:
        raise rb.ColorFlowError("无法复制时间线来生成节点模板。")
    original_tc = None
    try:
        project.SetCurrentTimeline(duplicate)
        item = duplicate.GetCurrentVideoItem()
        if item is None:
            items = rb.video_items(duplicate, "timeline", None)
            item = items[0]
        graph = item.GetNodeGraph()
        if graph is None or int(graph.GetNumNodes() or 0) < 3:
            raise rb.ColorFlowError("当前镜头节点数少于 3，无法作为节点模板。")
        backup, version = rb.create_backup_version(item, "模板前")
        try:
            if not graph.ResetAllGrades():
                raise rb.ColorFlowError("无法清空副本节点调色。")
            still = duplicate.GrabStill()
            if still is None:
                raise rb.ColorFlowError("无法抓取模板静帧。")
            gallery = project.GetGallery()
            album = gallery.GetCurrentStillAlbum() or gallery.CreateGalleryStillAlbum()
            safe = _safe_name(name)
            before = set(glob.glob(os.path.join(TEMPLATE_DIR, "*.drx")))
            if not album.ExportStills([still], TEMPLATE_DIR, safe, "drx"):
                raise rb.ColorFlowError("Resolve 未能导出模板 DRX。")
            after = set(glob.glob(os.path.join(TEMPLATE_DIR, "*.drx")))
            created = sorted(after - before, key=os.path.getmtime)
            if not created:
                candidates = sorted(
                    glob.glob(os.path.join(TEMPLATE_DIR, safe + "*.drx")),
                    key=os.path.getmtime,
                )
                if candidates:
                    created = [candidates[-1]]
            if not created:
                raise rb.ColorFlowError("没有找到模板 DRX 文件。")
            set_active_template(created[-1])
            fresh_graph = item.GetNodeGraph()
            return created[-1], int(
                (fresh_graph.GetNumNodes() if fresh_graph else 0) or 0
            )
        finally:
            previous_name = (backup or {}).get("versionName")
            if previous_name:
                try:
                    rb.restore_version(item, previous_name, (backup or {}).get("versionType", 0))
                except Exception:
                    pass
    finally:
        try:
            project.SetCurrentTimeline(timeline)
        except Exception:
            pass
        time.sleep(0.2)
        try:
            project.GetMediaPool().DeleteTimelines([duplicate])
        except Exception:
            pass


def apply_template(project, clip, path, label_nodes=False):
    if not path or not os.path.exists(path):
        raise rb.ColorFlowError(
            "还没有节点模板。请先在 Color 页面准备 5 个串行节点，"
            "然后在“预设与批量”页生成模板。"
        )
    if label_nodes:
        path = prepare_labeled_template(path)
    graph = clip.GetNodeGraph()
    if graph is None:
        raise rb.ColorFlowError("当前镜头没有节点图。")
    if not graph.ApplyGradeFromDRX(path, 0):
        raise rb.ColorFlowError("Resolve 未能套用节点模板。")
    # Applying a DRX replaces the node graph and invalidates the old proxy.
    graph = clip.GetNodeGraph()
    if graph is None:
        raise rb.ColorFlowError("模板套用后无法读取节点图。")
    nodes = int(graph.GetNumNodes() or 0)
    if nodes < 3:
        raise rb.ColorFlowError("模板套用后节点数异常：%d" % nodes)
    return nodes


def _export_still_png(album, still, prefix):
    os.makedirs(REFERENCE_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    prefix = "%s_%s" % (prefix, stamp)
    before = set(glob.glob(os.path.join(REFERENCE_DIR, prefix + "*.png")))
    if not album.ExportStills([still], REFERENCE_DIR, prefix, "png"):
        raise rb.ColorFlowError("Resolve 未能导出参考静帧。")
    after = set(glob.glob(os.path.join(REFERENCE_DIR, prefix + "*.png")))
    created = sorted(after - before, key=os.path.getmtime)
    if not created:
        candidates = sorted(
            glob.glob(os.path.join(REFERENCE_DIR, prefix + "*.png")),
            key=os.path.getmtime,
        )
        if candidates:
            created = [candidates[-1]]
    if not created or not os.path.isfile(created[-1]):
        raise rb.ColorFlowError("没有找到导出的参考静帧。")
    return created[-1]


def _reference_from_png(path, name, source):
    width, height, rgb = preview.read_png_rgb(path)
    return {
        "name": name,
        "stats": analysis.analyze_pixels(width, height, rgb, 3),
        "clip_id": None,
        "thumbnail": {
            "width": width,
            "height": height,
            "data": base64.b64encode(rgb).decode("ascii"),
        },
        "preview": path,
        "source": source,
    }


def list_gallery_stills(project):
    """Return selectable gallery stills with album names and display labels."""
    gallery = project.GetGallery()
    if gallery is None:
        raise rb.ColorFlowError("当前项目没有画廊。")
    entries = []
    for album in gallery.GetGalleryStillAlbums() or []:
        stills = album.GetStills() or []
        if not stills:
            continue
        album_name = gallery.GetAlbumName(album) or "相册"
        for index, still in enumerate(stills, 1):
            entries.append(
                {
                    "album": album,
                    "album_name": album_name,
                    "index": index,
                    "still": still,
                    "label": "%s · 静帧 %d" % (album_name, index),
                }
            )
    return entries


def reference_from_gallery_still(project, entry):
    path = _export_still_png(entry["album"], entry["still"], "gallery")
    name = "%s / 静帧 %d" % (entry["album_name"], entry["index"])
    return _reference_from_png(path, name, "gallery")


def _reference_album(gallery):
    for album in gallery.GetGalleryStillAlbums() or []:
        if gallery.GetAlbumName(album) == GALLERY_REFERENCE_ALBUM:
            return album
    album = gallery.CreateGalleryStillAlbum()
    if album is None:
        raise rb.ColorFlowError("无法创建参考静帧相册。")
    gallery.SetAlbumName(album, GALLERY_REFERENCE_ALBUM)
    return album


def reference_from_local_file(project, file_path):
    if not file_path or not os.path.isfile(file_path):
        raise rb.ColorFlowError("参考画面文件不存在。")
    gallery = project.GetGallery()
    if gallery is None:
        raise rb.ColorFlowError("当前项目没有画廊。")
    album = _reference_album(gallery)
    before = len(album.GetStills() or [])
    if not album.ImportStills([file_path]):
        raise rb.ColorFlowError("Resolve 未能导入这张参考图。")
    stills = album.GetStills() or []
    if len(stills) <= before:
        raise rb.ColorFlowError("导入后没有找到参考静帧。")
    still = stills[-1]
    label = os.path.splitext(os.path.basename(file_path))[0]
    try:
        album.SetLabel(still, label)
    except Exception:
        pass
    path = _export_still_png(album, still, "local")
    return _reference_from_png(path, "本地：%s" % label, "local")


def report_timeline(project, timeline, progress=None):
    _ensure_dirs()
    items = rb.video_items(timeline, "timeline", None)
    rows = []
    for index, item in enumerate(items):
        if progress:
            progress(index, len(items), item.GetName())
        try:
            capture = rb.capture_item_thumbnail(timeline, item)
            media = item.GetMediaPoolItem()
            info = clip_info(media, timeline, capture.get("thumbnail")) if media else {
                "name": item.GetName(),
                "resolution": "—",
                "fps": "—",
                "codec": "—",
                "bit_depth": "—",
                "white_balance": "—",
                "log": {"name": "未识别", "recognized": False},
                "warnings": [],
                "stats": capture.get("stats"),
            }
            rows.append(
                {
                    "name": item.GetName(),
                    "info": info,
                    "stats": capture.get("stats"),
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "name": item.GetName(),
                    "info": {
                        "name": item.GetName(),
                        "resolution": "—",
                        "fps": "—",
                        "codec": "—",
                        "bit_depth": "—",
                        "white_balance": "—",
                        "log": {"name": "读取失败", "recognized": False},
                        "warnings": [str(exc)],
                        "stats": None,
                    },
                    "stats": None,
                }
            )
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(REPORT_DIR, "ColorFlow_Report_%s.html" % stamp)
    write_report_html(path, project.GetName(), timeline.GetName(), rows)
    return path, rows


def write_report_html(path, project_name, timeline_name, rows):
    warning_count = sum(1 for row in rows if row["info"].get("warnings"))
    body_rows = []
    for index, row in enumerate(rows, 1):
        info = row["info"]
        stats = row.get("stats") or {}
        warnings = "；".join(info.get("warnings") or [])
        body_rows.append(
            "<tr>"
            "<td>%d</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
            "<td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
            "</tr>"
            % (
                index,
                html.escape(str(row.get("name", ""))),
                html.escape(str(info.get("resolution", "—"))),
                html.escape(str(info.get("fps", "—"))),
                html.escape(str(info.get("codec", "—"))),
                html.escape(str(info.get("bit_depth", "—"))),
                html.escape(str(info.get("white_balance", "—"))),
                html.escape(str((info.get("log") or {}).get("name", "—"))),
                html.escape(
                    "中间调 %.3f · 对比 %.2f stops"
                    % (stats.get("p50", 0.0), stats.get("contrast_stops", 0.0))
                    if stats
                    else "—"
                ),
                html.escape(warnings or "正常"),
            )
        )
    document = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>ColorFlow 调色报告</title>
<style>
body{background:#0b0d10;color:#e7edf5;font-family:Segoe UI,Microsoft YaHei,sans-serif;padding:28px;}
h1{font-size:24px;margin:0 0 6px;} p{color:#8b98a8;}
table{border-collapse:collapse;width:100%%;margin-top:20px;font-size:13px;}
th,td{border-bottom:1px solid #232b35;padding:9px 10px;text-align:left;}
th{color:#22d3ee;font-weight:600;} tr:hover{background:#14181e;}
.warn{color:#fbbf24;} .ok{color:#6ee7b7;}
</style></head><body>
<h1>ColorFlow 调色报告</h1>
<p>项目：%s · 时间线：%s · 镜头数：%d · 警告镜头：%d</p>
<table><thead><tr><th>#</th><th>镜头</th><th>分辨率</th><th>帧率</th><th>编码</th>
<th>位深</th><th>白平衡</th><th>Log</th><th>影调</th><th>警告</th></tr></thead>
<tbody>%s</tbody></table>
</body></html>""" % (
        html.escape(str(project_name)),
        html.escape(str(timeline_name)),
        len(rows),
        warning_count,
        "".join(body_rows),
    )
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(document)
    return path

