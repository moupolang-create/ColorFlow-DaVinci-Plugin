"""Resolve-side operations used by the ColorFlow panel.

The functions in this module are deliberately defensive: the scripting API
varies slightly between Resolve releases, and returning a useful error is more
helpful than silently doing the wrong thing to a grade.
"""

import os
import sys
import time
import uuid
from datetime import datetime

from . import analysis
from .timeline_tools import (
    format_duration,
    frames_to_timecode,
    natural_key,
    parse_fps,
    parse_resolution,
    summarize_sources,
)


class ColorFlowError(Exception):
    pass


def _get(obj, name, default=None):
    try:
        value = getattr(obj, name)
    except Exception:
        return default
    return value


def get_context(resolve):
    if resolve is None:
        raise ColorFlowError("没有连接到 DaVinci Resolve。")
    project_manager = resolve.GetProjectManager()
    if project_manager is None:
        raise ColorFlowError("无法读取项目管理器。")
    project = project_manager.GetCurrentProject()
    if project is None:
        raise ColorFlowError("请先打开一个 Resolve 项目。")
    timeline = project.GetCurrentTimeline()
    clip = None
    if timeline is not None:
        try:
            clip = timeline.GetCurrentVideoItem()
        except Exception:
            clip = None
    return {
        "resolve": resolve,
        "project_manager": project_manager,
        "project": project,
        "timeline": timeline,
        "clip": clip,
    }


def project_color_space(project):
    try:
        value = str(project.GetSetting("colorSpaceTimeline") or "")
    except Exception:
        value = ""
    lowered = value.lower()
    if "davinci" in lowered or "wide gamut" in lowered or "/intermediate" in lowered:
        return "dwg", value or "DaVinci Wide Gamut / Intermediate"
    if "rec.709" in lowered or "rec709" in lowered or "srgb" in lowered:
        return "rec709", value or "Rec.709"
    if not value:
        try:
            mode = str(project.GetSetting("colorScienceMode") or "")
        except Exception:
            mode = ""
        if "managed" not in mode.lower():
            return "rec709", "Rec.709（非色彩管理项目）"
    return "rec709", value or "未识别，按 Rec.709 处理"


def clip_properties(clip):
    try:
        return clip.GetClipProperty() or {}
    except Exception:
        return {}


def _clip_is_video(clip):
    if clip is None:
        return False
    try:
        if clip.GetTimeline() is not None:
            return False
    except Exception:
        pass
    properties = clip_properties(clip)
    resolution = parse_resolution(properties.get("Resolution"))
    if not resolution:
        return False
    duration = str(properties.get("Duration") or "")
    if duration and set(duration.replace(":", "")) <= {"0"}:
        return False
    return True


def _walk_folder(folder, include_subfolders, seen):
    clips = []
    if folder is None:
        return clips
    try:
        items = folder.GetClipList() or []
    except Exception:
        items = []
    for clip in items:
        key = None
        try:
            key = clip.GetUniqueId()
        except Exception:
            pass
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        if _clip_is_video(clip):
            clips.append(clip)
    if include_subfolders:
        try:
            children = folder.GetSubFolderList() or []
        except Exception:
            children = []
        for child in children:
            clips.extend(_walk_folder(child, True, seen))
    return clips


def media_clips(project, include_subfolders=False):
    media_pool = project.GetMediaPool()
    selected = []
    try:
        selected = media_pool.GetSelectedClips() or []
    except Exception:
        selected = []
    selected = [clip for clip in selected if _clip_is_video(clip)]
    if selected:
        selected.sort(key=lambda clip: natural_key(clip.GetName()))
        return selected, "媒体池选中素材"
    folder = media_pool.GetCurrentFolder()
    clips = _walk_folder(folder, include_subfolders, set())
    clips.sort(key=lambda clip: natural_key(clip.GetName()))
    name = folder.GetName() if folder is not None else "当前媒体池"
    return clips, name


def source_summary(clips, fallback_fps=25.0):
    properties = []
    for clip in clips:
        props = clip_properties(clip)
        properties.append(
            {
                "name": clip.GetName(),
                "resolution": parse_resolution(props.get("Resolution")),
                "fps": parse_fps(props.get("FPS")),
                "codec": props.get("Video Codec") or "",
                "duration": props.get("Duration") or "",
            }
        )
    summary = summarize_sources(properties, fallback_fps=fallback_fps)
    summary["clips"] = properties
    return summary


def create_timeline(project, clips, name, start_timecode=None):
    if not clips:
        raise ColorFlowError("没有可放入时间线的视频素材。")
    fallback_fps = 25.0
    try:
        fallback_fps = float(project.GetSetting("timelineFrameRate") or 25.0)
    except Exception:
        pass
    summary = source_summary(clips, fallback_fps=fallback_fps)
    settings = {
        "timelineResolutionWidth": str(summary["width"]),
        "timelineResolutionHeight": str(summary["height"]),
        "timelineFrameRate": ("%.3f" % summary["fps"]).rstrip("0").rstrip("."),
        "timelinePlaybackFrameRate": str(int(round(summary["fps"]))),
    }
    for key, value in settings.items():
        try:
            project.SetSetting(key, value)
        except Exception:
            pass

    media_pool = project.GetMediaPool()
    timeline = None
    try:
        timeline = media_pool.CreateTimelineFromClips(name, clips)
    except Exception:
        timeline = None
    if timeline is None:
        timeline = media_pool.CreateEmptyTimeline(name)
        if timeline is None:
            raise ColorFlowError("Resolve 未能创建时间线。请确认当前媒体池允许写入。")
        appended = media_pool.AppendToTimeline(clips) or []
        if not appended:
            raise ColorFlowError("时间线已创建，但素材追加失败。")

    if start_timecode:
        try:
            timeline.SetStartTimecode(start_timecode)
        except Exception:
            pass
    try:
        project.SetCurrentTimeline(timeline)
    except Exception:
        pass

    fps = summary["fps"]
    duration_frames = 0
    try:
        duration_frames = int(timeline.GetEndFrame()) - int(timeline.GetStartFrame())
    except Exception:
        pass
    return {
        "timeline": timeline,
        "name": timeline.GetName(),
        "summary": summary,
        "duration": format_duration(duration_frames, fps),
    }


def video_items(timeline, scope="timeline", current_clip=None):
    if timeline is None:
        raise ColorFlowError("当前没有打开的时间线。")
    if scope == "current":
        if current_clip is None:
            current_clip = timeline.GetCurrentVideoItem()
        if current_clip is None:
            raise ColorFlowError("请先把播放头放在一个视频镜头上。")
        return [current_clip]
    if scope == "selected":
        items = timeline.GetSelectedClips() or []
        items = [item for item in items if _item_is_video(item)]
        if not items:
            # The Color page usually has no Edit-page selection; the shot under
            # the playhead is the effective "selected" shot. This also covers
            # trimmed/split timeline segments.
            try:
                current = current_clip or timeline.GetCurrentVideoItem()
            except Exception:
                current = current_clip
            if current is not None and _item_is_video(current):
                items = [current]
        if not items:
            raise ColorFlowError(
                "没有选中的时间线视频镜头，且播放头不在视频镜头上。"
            )
        return items
    items = []
    seen = set()
    try:
        track_count = int(timeline.GetTrackCount("video") or 0)
    except Exception:
        track_count = 0
    for track_index in range(1, track_count + 1):
        for item in timeline.GetItemListInTrack("video", track_index) or []:
            if not _item_is_video(item):
                continue
            key = item.GetUniqueId()
            if key in seen:
                continue
            seen.add(key)
            items.append(item)
    if not items:
        raise ColorFlowError("时间线上没有视频镜头。")
    items.sort(key=lambda item: (int(item.GetStart()), natural_key(item.GetName())))
    return items


def _item_is_video(item):
    try:
        track_type, _ = item.GetTrackTypeAndIndex()
        return str(track_type).lower().startswith("video") or str(track_type) == "视频"
    except Exception:
        return True


def _timeline_rate(timeline):
    try:
        return float(timeline.GetSetting("timelineFrameRate") or 25.0)
    except Exception:
        return 25.0


def _timeline_start_frame(timeline):
    try:
        return int(timeline.GetStartFrame() or 0)
    except Exception:
        return 0


def _timeline_start_timecode(timeline):
    try:
        return str(timeline.GetStartTimecode() or "00:00:00:00")
    except Exception:
        return "00:00:00:00"


def _drop_frame(timeline):
    try:
        return str(timeline.GetSetting("timelineDropFrameTimecode") or "0") == "1"
    except Exception:
        return False


def _frame_for_item(timeline, item):
    start = int(item.GetStart())
    end = int(item.GetEnd())
    if end <= start:
        return start
    return start + max(0, min(1, (end - start) // 2))


def _timecode_for_frame(timeline, frame):
    return frames_to_timecode(
        int(frame) - _timeline_start_frame(timeline),
        _timeline_rate(timeline),
        _timeline_start_timecode(timeline),
        _drop_frame(timeline),
    )


def capture_item_thumbnail(timeline, item):
    """Capture the Resolve thumbnail associated with one timeline item."""
    original = None
    try:
        original = timeline.GetCurrentTimecode()
    except Exception:
        pass
    frame = _frame_for_item(timeline, item)
    target = _timecode_for_frame(timeline, frame)
    try:
        try:
            if not timeline.SetCurrentTimecode(target):
                raise ColorFlowError("无法把播放头移动到镜头中间帧。")
        except ColorFlowError:
            raise
        except Exception as exc:
            raise ColorFlowError("无法移动播放头：%s" % exc)

        time.sleep(0.15)
        current = None
        try:
            current = timeline.GetCurrentVideoItem()
        except Exception:
            current = None
        expected = None
        actual = None
        try:
            expected = item.GetUniqueId()
            actual = current.GetUniqueId() if current is not None else None
        except Exception:
            pass
        if expected and actual and expected != actual:
            raise ColorFlowError(
                "抓帧时播放头落在另一条图层或转场上（期望 %s，实际 %s）。"
                % (item.GetName(), current.GetName() if current is not None else "无")
            )

        thumbnail = None
        last_error = None
        for _attempt in range(5):
            try:
                thumbnail = timeline.GetCurrentClipThumbnailImage()
            except Exception as exc:
                last_error = exc
                thumbnail = None
            if thumbnail and thumbnail.get("data"):
                break
            time.sleep(0.15)
        if not thumbnail or not thumbnail.get("data"):
            raise ColorFlowError(
                "Resolve 没有返回镜头缩略图。请切换到 Color 页面并选中该镜头后重试。%s"
                % ((" 最后错误：%s" % last_error) if last_error else "")
            )
        stats = analysis.analyze_thumbnail(thumbnail)
        return {
            "item": item,
            "name": item.GetName(),
            "frame": frame,
            "timecode": target,
            "thumbnail": thumbnail,
            "stats": stats,
        }
    finally:
        if original:
            try:
                timeline.SetCurrentTimecode(original)
            except Exception:
                pass


def list_nodes(clip):
    graph = clip.GetNodeGraph()
    if graph is None:
        raise ColorFlowError("当前镜头没有节点图。")
    count = int(graph.GetNumNodes() or 0)
    nodes = []
    for index in range(1, count + 1):
        tools = None
        label = ""
        lut = ""
        try:
            tools = graph.GetToolsInNode(index)
        except Exception:
            tools = None
        try:
            label = str(graph.GetNodeLabel(index) or "")
        except Exception:
            label = ""
        try:
            lut = str(graph.GetLUT(index) or "")
        except Exception:
            lut = ""
        if isinstance(tools, str):
            tools_list = [tools]
        else:
            tools_list = list(tools or [])
        likely_empty = not tools_list and not lut.strip()
        managed = "colorflow" in lut.replace("\\", "/").lower()
        nodes.append(
            {
                "index": index,
                "label": label,
                "tools": tools_list,
                "lut": lut,
                "likely_empty": likely_empty,
                "managed": managed,
            }
        )
    return nodes


def node_label(node):
    bits = ["%02d" % node["index"]]
    if node.get("likely_empty"):
        bits.append("疑似空白")
    elif node.get("managed"):
        bits.append("ColorFlow 文件")
    elif node.get("tools"):
        bits.append("%d 个工具" % len(node["tools"]))
    if node.get("lut"):
        bits.append("已有 LUT")
    if node.get("label"):
        bits.append(node["label"])
    return " · ".join(bits)


def lut_root():
    if sys.platform == "darwin":
        root = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT"
    elif os.name == "nt":
        program_data = os.environ.get("PROGRAMDATA") or r"C:\ProgramData"
        root = os.path.join(
            program_data, "Blackmagic Design", "DaVinci Resolve", "Support", "LUT"
        )
    else:
        root = "/opt/resolve/LUT"
    return root


def colorflow_lut_dir():
    directory = os.path.join(lut_root(), "ColorFlow")
    os.makedirs(directory, exist_ok=True)
    return directory


def write_dctl(text, label):
    safe = analysis.ascii_label(label, "correction").replace(" ", "_")[:60]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    filename = "colorflow-%s-%s-%s.dctl" % (
        safe or "match",
        stamp,
        uuid.uuid4().hex[:8],
    )
    path = os.path.join(colorflow_lut_dir(), filename)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path, "ColorFlow/" + filename


def _same_lut(assigned, relative):
    assigned = str(assigned or "").replace("\\", "/")
    relative = str(relative or "").replace("\\", "/")
    return assigned.endswith(relative) or relative.endswith(assigned) or assigned == relative


def apply_lut(project, clip, node_index, absolute_path, relative_path):
    previous = ""
    try:
        graph = clip.GetNodeGraph()
        previous = str(graph.GetLUT(int(node_index)) or "")
    except Exception:
        graph = clip.GetNodeGraph()
    # A LUT on a disabled node has no visible effect. Enabling the target node
    # is part of the write; the pre-write colour version restores the state.
    try:
        graph.SetNodeEnabled(int(node_index), True)
    except Exception:
        pass
    try:
        refreshed = project.RefreshLUTList()
    except Exception:
        refreshed = False
    if not refreshed:
        raise ColorFlowError("Resolve 未能刷新 LUT 列表。")

    applied = False
    # Resolve's TimelineItem.SetLUT is the most reliable route for layer 1.
    try:
        applied = bool(clip.SetLUT(int(node_index), relative_path))
    except Exception:
        applied = False
    assigned = ""
    try:
        assigned = str(clip.GetLUT(int(node_index)) or "")
    except Exception:
        assigned = ""
    if not applied or not _same_lut(assigned, relative_path):
        try:
            applied = bool(graph.SetLUT(int(node_index), relative_path))
        except Exception:
            applied = False
        try:
            assigned = str(graph.GetLUT(int(node_index)) or "")
        except Exception:
            assigned = ""
    if not applied and not _same_lut(assigned, relative_path):
        raise ColorFlowError(
            "Resolve 拒绝把生成文件写入 %02d 号节点。请在 Color 页面准备一个空白串行节点。"
            % int(node_index)
        )
    return {
        "previous": previous,
        "assigned": assigned,
        "relative": relative_path,
        "absolute": absolute_path,
    }


def apply_cdl(clip, node_index, values):
    try:
        clip.GetNodeGraph().SetNodeEnabled(int(node_index), True)
    except Exception:
        pass
    if not clip.SetCDL(values):
        raise ColorFlowError(
            "Resolve 未能向 %02d 号节点写入 CDL。请换一个空白节点重试。"
            % int(node_index)
        )
    return values


def reset_grade(clip):
    graph = clip.GetNodeGraph()
    if graph is None:
        raise ColorFlowError("当前镜头没有节点图。")
    if not graph.ResetAllGrades():
        raise ColorFlowError("Resolve 未能重置当前节点层。")
    return True


def current_version(clip):
    try:
        return clip.GetCurrentVersion() or {}
    except Exception:
        return {}


def create_backup_version(clip, label):
    previous = current_version(clip)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = "ColorFlow · %s · %s · %s" % (
        label,
        stamp,
        uuid.uuid4().hex[:6],
    )
    if not clip.AddVersion(name, 0):
        raise ColorFlowError("无法创建调色版本备份，已停止写入。")
    if not clip.LoadVersionByName(name, 0):
        raise ColorFlowError("调色版本已创建，但无法载入，已停止写入。")
    return previous, name


def restore_version(clip, name, version_type=0):
    if not name:
        return False
    return bool(clip.LoadVersionByName(name, int(version_type)))


def save_project(project_manager):
    try:
        return bool(project_manager.SaveProject())
    except Exception:
        return False

