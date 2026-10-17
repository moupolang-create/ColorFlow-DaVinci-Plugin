"""The Resolve-native Qt panel for ColorFlow."""

import html
import time
import traceback
import uuid
from datetime import datetime

from . import analysis
from . import resolve_bridge as rb


WIN_ID_PREFIX = "com.colorflow.resolve.panel"
STYLE = """
QWidget {
    background-color: #17191d;
    color: #d7dce3;
    font-family: 'Segoe UI';
    font-size: 10pt;
}
QLabel { background: transparent; }
QComboBox, QSpinBox, QLineEdit {
    background-color: #23272e;
    border: 1px solid #343a44;
    border-radius: 4px;
    padding: 4px 6px;
    color: #e6ebf2;
}
QComboBox::drop-down { border: 0; }
QPushButton {
    background-color: #2a3039;
    border: 1px solid #3a424e;
    border-radius: 4px;
    padding: 6px 12px;
    color: #e6ebf2;
}
QPushButton:hover { background-color: #343c47; }
QPushButton:pressed { background-color: #20252c; }
QCheckBox { spacing: 6px; }
QTextEdit {
    background-color: #0e1013;
    border: 1px solid #2a3039;
    border-radius: 4px;
    color: #b9c3cf;
}
QScrollBar:vertical { background: #17191d; width: 10px; }
QScrollBar::handle:vertical { background: #3a424e; border-radius: 5px; }
"""


def _section(title, subtitle, children):
    return {
        "title": title,
        "subtitle": subtitle,
        "children": children,
    }


class ColorFlowApp(object):
    def __init__(self, resolve, fusion, bmd):
        self.resolve = resolve
        self.fusion = fusion
        self.bmd = bmd
        self.ui = fusion.UIManager
        self.dispatcher = bmd.UIDispatcher(self.ui)
        self.window_id = "%s.%s" % (WIN_ID_PREFIX, uuid.uuid4().hex[:8])
        self.win = None
        self.reference = None
        self.nodes = []
        self.last_backups = []
        self.source_clips = []
        self.source_origin = ""
        self.summary = None
        self._closing = False
        self._cancel_requested = False

    # ------------------------------------------------------------------ UI
    def _build_window(self):
        title_font = self.ui.Font({"Family": "Segoe UI", "PointSize": 18, "Bold": True})
        kicker_font = self.ui.Font({"Family": "Segoe UI", "PointSize": 8, "Bold": True})
        body_font = self.ui.Font({"Family": "Segoe UI", "PointSize": 9})
        mono_font = self.ui.Font({"Family": "Consolas", "PixelSize": 11})

        header = self.ui.HGroup(
            {"Spacing": 10, "Weight": 0},
            [
                self.ui.VGroup(
                    {"Spacing": 1, "Weight": 1},
                    [
                        self.ui.Label(
                            {
                                "Text": "COLORFLOW · RESOLVE STUDIO",
                                "Font": kicker_font,
                                "StyleSheet": "color:#6ea8fe; letter-spacing:2px;",
                            }
                        ),
                        self.ui.Label(
                            {
                                "Text": "把建线、还原与镜头匹配收进一个面板",
                                "Font": title_font,
                                "StyleSheet": "color:#f2f5f8;",
                            }
                        ),
                    ],
                ),
                self.ui.HGap(0, 1),
                self.ui.Label(
                    {
                        "Text": "本地处理 · 不上传素材",
                        "StyleSheet": "color:#8b95a5;",
                    }
                ),
            ],
        )

        context_row = self.ui.HGroup(
            {"Spacing": 14, "Weight": 0},
            [
                self.ui.Label({"ID": "ctx_project", "Text": "项目：—", "Font": body_font}),
                self.ui.Label({"ID": "ctx_timeline", "Text": "时间线：—", "Font": body_font}),
                self.ui.Label({"ID": "ctx_clip", "Text": "当前镜头：—", "Font": body_font}),
                self.ui.Label({"ID": "ctx_space", "Text": "色彩空间：—", "Font": body_font}),
            ],
        )

        build_section = self.ui.VGroup(
            {"Spacing": 4, "Weight": 0},
            [
                self.ui.Label(
                    {
                        "Text": '<b>01 · 智能建线</b> <span style="color:#7f8a99;">按素材分辨率与帧率创建时间线</span>',
                        "Font": body_font,
                    }
                ),
                self.ui.Label(
                    {
                        "ID": "source_info",
                        "Text": "正在读取当前媒体池…",
                        "WordWrap": True,
                        "Font": body_font,
                    }
                ),
                self.ui.HGroup(
                    {"Spacing": 8, "Weight": 0},
                    [
                        self.ui.CheckBox(
                            {
                                "ID": "chk_recursive",
                                "Text": "含子文件夹",
                                "Checked": True,
                            }
                        ),
                        self.ui.CheckBox(
                            {
                                "ID": "chk_start_tc",
                                "Text": "起始 01:00:00:00",
                                "Checked": True,
                            }
                        ),
                    ],
                ),
                self.ui.HGroup(
                    {"Spacing": 8, "Weight": 0},
                    [
                        self.ui.Button(
                            {
                                "ID": "btn_build",
                                "Text": "创建匹配时间线",
                                "MinimumSize": [0, 30],
                            }
                        ),
                        self.ui.Button(
                            {
                                "ID": "btn_refresh",
                                "Text": "刷新素材",
                                "MinimumSize": [0, 30],
                            }
                        ),
                    ],
                ),
                self.ui.Label(
                    {
                        "ID": "build_status",
                        "Text": "",
                        "WordWrap": True,
                        "Font": body_font,
                    }
                ),
            ],
        )

        restore_section = self.ui.VGroup(
            {"Spacing": 4, "Weight": 0},
            [
                self.ui.Label(
                    {
                        "Text": '<b>02 · 一键还原</b> <span style="color:#7f8a99;">先备份版本，再还原或去色偏</span>',
                        "Font": body_font,
                    }
                ),
                self.ui.Label(
                    {
                        "Text": "“还原原始”会清空当前节点层；只修曝光/白平衡请用“智能去色偏”。",
                        "WordWrap": True,
                        "Font": body_font,
                        "StyleSheet": "color:#8b95a5;",
                    }
                ),
                self.ui.HGroup(
                    {"Spacing": 8, "Weight": 0},
                    [
                        self.ui.Button(
                            {
                                "ID": "btn_reset",
                                "Text": "备份并还原原始",
                                "MinimumSize": [0, 30],
                            }
                        ),
                        self.ui.Button(
                            {
                                "ID": "btn_neutral",
                                "Text": "智能去色偏",
                                "MinimumSize": [0, 30],
                            }
                        ),
                    ],
                ),
                self.ui.CheckBox(
                    {
                        "ID": "chk_restore_tone",
                        "Text": "同时恢复对比与饱和（适合灰片/Log）",
                        "Checked": True,
                    }
                ),
                self.ui.HGroup(
                    {"Spacing": 8, "Weight": 0},
                    [
                        self.ui.Label({"Text": "强度", "Font": body_font}),
                        self.ui.SpinBox(
                            {
                                "ID": "spin_restore",
                                "Value": 70,
                                "Minimum": 0,
                                "Maximum": 100,
                                "SingleStep": 5,
                                "Suffix": " %",
                                "MinimumSize": [110, 0],
                            }
                        ),
                        self.ui.HGap(8),
                        self.ui.Label({"Text": "范围", "Font": body_font}),
                        self.ui.ComboBox(
                            {
                                "ID": "scope_restore",
                                "ItemText": ["当前镜头", "选中镜头", "整条时间线"],
                                "CurrentIndex": 0,
                                "MinimumSize": [160, 0],
                            }
                        ),
                    ],
                ),
                self.ui.Label(
                    {
                        "ID": "restore_status",
                        "Text": "",
                        "WordWrap": True,
                        "Font": body_font,
                    }
                ),
            ],
        )

        match_section = self.ui.VGroup(
            {"Spacing": 4, "Weight": 0},
            [
                self.ui.Label(
                    {
                        "Text": '<b>03 · 颜色匹配</b> <span style="color:#7f8a99;">统计匹配曝光、白平衡、对比与饱和</span>',
                        "Font": body_font,
                    }
                ),
                self.ui.HGroup(
                    {"Spacing": 8, "Weight": 0},
                    [
                        self.ui.Button(
                            {
                                "ID": "btn_reference",
                                "Text": "以当前镜头为参考",
                                "MinimumSize": [0, 30],
                            }
                        ),
                        self.ui.Label(
                            {
                                "ID": "reference_info",
                                "Text": "尚未设置参考镜头",
                                "WordWrap": True,
                                "Font": body_font,
                                "StyleSheet": "color:#8b95a5;",
                            }
                        ),
                    ],
                ),
                self.ui.HGroup(
                    {"Spacing": 8, "Weight": 0},
                    [
                        self.ui.Label({"Text": "强度", "Font": body_font}),
                        self.ui.SpinBox(
                            {
                                "ID": "spin_match",
                                "Value": 70,
                                "Minimum": 0,
                                "Maximum": 100,
                                "SingleStep": 5,
                                "Suffix": " %",
                                "MinimumSize": [110, 0],
                            }
                        ),
                        self.ui.HGap(8),
                        self.ui.Label({"Text": "范围", "Font": body_font}),
                        self.ui.ComboBox(
                            {
                                "ID": "scope_match",
                                "ItemText": ["当前镜头", "选中镜头", "整条时间线"],
                                "CurrentIndex": 1,
                                "MinimumSize": [160, 0],
                            }
                        ),
                    ],
                ),
                self.ui.Button(
                    {
                        "ID": "btn_match",
                        "Text": "匹配到目标镜头",
                        "MinimumSize": [0, 30],
                    }
                ),
                self.ui.Label(
                    {
                        "ID": "match_status",
                        "Text": "",
                        "WordWrap": True,
                        "Font": body_font,
                    }
                ),
            ],
        )

        safety_section = self.ui.VGroup(
            {"Spacing": 4, "Weight": 0},
            [
                self.ui.Label(
                    {
                        "Text": '<b>写入节点与安全</b> <span style="color:#7f8a99;">CDL / DCTL 只写到已有节点</span>',
                        "Font": body_font,
                    }
                ),
                self.ui.ComboBox(
                    {
                        "ID": "node_combo",
                        "ItemText": ["正在读取节点…"],
                        "CurrentIndex": 0,
                    }
                ),
                self.ui.HGroup(
                    {"Spacing": 8, "Weight": 0},
                    [
                        self.ui.CheckBox(
                            {
                                "ID": "chk_auto_node",
                                "Text": "自动找末尾空白节点",
                                "Checked": True,
                            }
                        ),
                        self.ui.CheckBox(
                            {
                                "ID": "chk_backup",
                                "Text": "写入前建版本",
                                "Checked": True,
                            }
                        ),
                    ],
                ),
                self.ui.HGroup(
                    {"Spacing": 8, "Weight": 0},
                    [
                        self.ui.CheckBox(
                            {
                                "ID": "chk_allow_nonempty",
                                "Text": "允许写非空节点",
                                "Checked": False,
                            }
                        ),
                        self.ui.Button(
                            {
                                "ID": "btn_nodes",
                                "Text": "刷新节点",
                                "MinimumSize": [0, 26],
                            }
                        ),
                        self.ui.Button(
                            {
                                "ID": "btn_undo",
                                "Text": "撤销上次写入",
                                "MinimumSize": [0, 26],
                            }
                        ),
                    ],
                ),
                self.ui.Label(
                    {
                        "ID": "node_status",
                        "Text": "",
                        "WordWrap": True,
                        "Font": body_font,
                    }
                ),
            ],
        )

        log_section = self.ui.VGroup(
            {"Spacing": 4, "Weight": 1},
            [
                self.ui.Label(
                    {
                        "Text": '<b>运行日志</b> <span style="color:#7f8a99;">每一步都可核对</span>',
                        "Font": body_font,
                    }
                ),
                self.ui.TextEdit(
                    {
                        "ID": "log",
                        "ReadOnly": True,
                        "Font": mono_font,
                        "TextColor": "#c9d1d9",
                        "TextBackgroundColor": "#0e1013",
                        "LineWrapMode": "WidgetWidth",
                        "MinimumSize": [0, 240],
                        "Weight": 1,
                    }
                ),
            ],
        )

        left = self.ui.VGroup(
            {"Spacing": 8, "Weight": 1.2},
            [build_section, restore_section, match_section],
        )
        right = self.ui.VGroup(
            {"Spacing": 8, "Weight": 0.8},
            [safety_section, log_section],
        )
        body = self.ui.HGroup({"Spacing": 12, "Weight": 1}, [left, right])
        footer = self.ui.HGroup(
            {"Spacing": 8, "Weight": 0},
            [
                self.ui.Label(
                    {
                        "Text": "提示：公开脚本接口不能新建节点。请先在 Color 页面准备一个空白串行节点；插件会优先写入末尾的疑似空白节点。",
                        "WordWrap": True,
                        "Font": body_font,
                        "StyleSheet": "color:#7f8a99;",
                        "Weight": 1,
                    }
                ),
                self.ui.Button(
                    {
                        "ID": "btn_close",
                        "Text": "关闭面板",
                        "MinimumSize": [90, 28],
                    }
                ),
            ],
        )

        window = self.dispatcher.AddWindow(
            {
                "ID": self.window_id,
                "Geometry": [110, 80, 1040, 780],
                "WindowTitle": "ColorFlow · 达芬奇调色助手",
                "StyleSheet": STYLE,
            },
            self.ui.VGroup(
                {"Spacing": 8, "Weight": 1},
                [header, context_row, body, footer],
            ),
        )
        window.On[self.window_id].Close = self.on_close
        return window

    def _connect(self):
        for widget_id, items, index in (
            (
                "scope_restore",
                ["当前镜头", "选中镜头", "整条时间线"],
                0,
            ),
            (
                "scope_match",
                ["当前镜头", "选中镜头", "整条时间线"],
                1,
            ),
        ):
            combo = self._find(widget_id)
            combo.Clear()
            combo.AddItems(items)
            combo.CurrentIndex = index
        self.win.On["btn_build"].Clicked = self.on_build
        self.win.On["btn_refresh"].Clicked = self.on_refresh
        self.win.On["btn_reset"].Clicked = self.on_reset
        self.win.On["btn_neutral"].Clicked = self.on_neutralize
        self.win.On["btn_reference"].Clicked = self.on_reference
        self.win.On["btn_match"].Clicked = self.on_match
        self.win.On["btn_nodes"].Clicked = self.on_refresh_nodes
        self.win.On["btn_undo"].Clicked = self.on_undo
        self.win.On["btn_close"].Clicked = self.on_close
        self.win.On["node_combo"].CurrentIndexChanged = self.on_node_changed

    # ------------------------------------------------------------- utilities
    def _find(self, widget_id):
        return self.win.Find(widget_id)

    def _set(self, widget_id, text, color="#9ca3af"):
        widget = self._find(widget_id)
        if widget is None:
            return
        widget.Text = '<span style="color:%s;">%s</span>' % (
            color,
            html.escape(str(text)),
        )
        self.pump()

    def _log(self, text):
        stamp = datetime.now().strftime("%H:%M:%S")
        try:
            self._find("log").Append("[%s] %s" % (stamp, text))
            self._find("log").EnsureCursorVisible()
        except Exception:
            pass
        self.pump()

    def pump(self):
        # StepLoop processes pending Qt events (including the window close
        # button) without blocking the Resolve API work.
        try:
            self.dispatcher.StepLoop()
        except Exception:
            pass
        try:
            self.win.Update()
            self.win.Repaint()
        except Exception:
            pass

    def _scope(self, widget_id):
        index = int(self._find(widget_id).CurrentIndex)
        return ["current", "selected", "timeline"][max(0, min(2, index))]

    def _strength(self, widget_id):
        return max(0.0, min(1.0, float(self._find(widget_id).Value) / 100.0))

    def _context(self):
        return rb.get_context(self.resolve)

    def _refresh_context_labels(self):
        try:
            context = self._context()
        except Exception as exc:
            self._set("ctx_project", "项目：%s" % exc, "#f87171")
            return None
        project = context["project"]
        timeline = context["timeline"]
        clip = context["clip"]
        space_key, space_label = rb.project_color_space(project)
        self._set("ctx_project", "项目：%s" % project.GetName(), "#d7dce3")
        self._set(
            "ctx_timeline",
            "时间线：%s" % (timeline.GetName() if timeline is not None else "未打开"),
            "#d7dce3",
        )
        self._set(
            "ctx_clip",
            "当前镜头：%s" % (clip.GetName() if clip is not None else "无"),
            "#d7dce3",
        )
        self._set(
            "ctx_space",
            "色彩空间：%s" % space_label,
            "#6ee7b7" if space_key == "dwg" else "#fbbf24",
        )
        return context

    # -------------------------------------------------------------- refresh
    def refresh_all(self):
        context = self._refresh_context_labels()
        if context is None:
            return
        try:
            recursive = bool(self._find("chk_recursive").Checked)
            clips, origin = rb.media_clips(context["project"], recursive)
            self.source_clips = clips
            self.source_origin = origin
            if clips:
                summary = rb.source_summary(clips)
                self.summary = summary
                warning = ""
                if summary["mixed_resolution"]:
                    warning += " · 分辨率不一致，将按最大分辨率建线"
                if summary["mixed_fps"]:
                    warning += " · 帧率不一致，将按最常见帧率建线"
                self._set(
                    "source_info",
                    "%s · %d 个视频素材 · %dx%d · %.3f fps%s"
                    % (
                        origin,
                        len(clips),
                        summary["width"],
                        summary["height"],
                        summary["fps"],
                        warning,
                    ),
                    "#fbbf24" if warning else "#d7dce3",
                )
            else:
                self.summary = None
                self._set(
                    "source_info",
                    "当前媒体池没有可用的视频素材。",
                    "#f87171",
                )
        except Exception as exc:
            self._set("source_info", "读取素材失败：%s" % exc, "#f87171")
        self.refresh_nodes()

    def refresh_nodes(self):
        try:
            context = self._context()
        except Exception as exc:
            self.nodes = []
            self._set("node_status", str(exc), "#f87171")
            return
        clip = context["clip"]
        if clip is None:
            self.nodes = []
            combo = self._find("node_combo")
            combo.Clear()
            combo.AddItem("没有当前镜头")
            self._set("node_status", "请先把播放头放在一个视频镜头上。", "#fbbf24")
            return
        try:
            nodes = rb.list_nodes(clip)
        except Exception as exc:
            self.nodes = []
            self._set("node_status", "读取节点失败：%s" % exc, "#f87171")
            return
        self.nodes = nodes
        combo = self._find("node_combo")
        combo.Clear()
        combo.AddItems([rb.node_label(node) for node in nodes])
        if not nodes:
            self._set("node_status", "当前镜头没有节点。", "#f87171")
            return
        index = 0
        if bool(self._find("chk_auto_node").Checked):
            empty = [position for position, node in enumerate(nodes) if node["likely_empty"]]
            index = empty[-1] if empty else len(nodes) - 1
        combo.CurrentIndex = index
        self.update_node_status()

    def update_node_status(self):
        if not self.nodes:
            return
        index = int(self._find("node_combo").CurrentIndex)
        index = max(0, min(len(self.nodes) - 1, index))
        node = self.nodes[index]
        if node["likely_empty"]:
            text = "将写入 %02d 号节点：没有检测到工具或 LUT；写入时会自动启用该节点。" % node["index"]
            color = "#6ee7b7"
        elif node.get("managed"):
            text = (
                "将写入 %02d 号节点：已有 ColorFlow 文件，可直接替换；"
                "写入前版本会保留，写入时会自动启用节点。" % node["index"]
            )
            color = "#6ee7b7"
        else:
            text = (
                "将写入 %02d 号节点：已有工具或 LUT。CDL/DCTL 可能覆盖或叠加原有调色，"
                "建议换空白节点；写入时会自动启用节点。" % node["index"]
            )
            color = "#fbbf24"
        if node["label"]:
            text += " 节点标签：%s" % node["label"]
        self._set("node_status", text, color)

    # --------------------------------------------------------------- build
    def on_refresh(self, event):
        self.refresh_all()
        self._log("已刷新素材与节点信息。")

    def on_refresh_nodes(self, event):
        self.refresh_nodes()
        self._log("已刷新当前镜头的节点列表。")

    def on_node_changed(self, event):
        self.update_node_status()

    def on_build(self, event):
        try:
            context = self._context()
            project = context["project"]
            recursive = bool(self._find("chk_recursive").Checked)
            clips, origin = rb.media_clips(project, recursive)
            if not clips:
                raise rb.ColorFlowError("当前媒体池没有可用的视频素材。")
            try:
                fallback_fps = float(project.GetSetting("timelineFrameRate") or 25.0)
            except Exception:
                fallback_fps = 25.0
            summary = rb.source_summary(clips, fallback_fps)
            if summary["mixed_fps"]:
                self._log(
                    "检测到混合帧率 %s，按最常见帧率 %.3f 建线。"
                    % (summary["fps_counts"], summary["fps"])
                )
            stamp = datetime.now().strftime("%m%d-%H%M%S")
            name = "ColorFlow · %s · %s" % (origin, stamp)
            start_tc = "01:00:00:00" if bool(self._find("chk_start_tc").Checked) else None
            self._set("build_status", "正在创建时间线…", "#fbbf24")
            self.pump()
            result = rb.create_timeline(project, clips, name, start_tc)
            try:
                context["project_manager"].SaveProject()
            except Exception:
                pass
            self._set(
                "build_status",
                "已创建“%s”：%d 个素材 · %dx%d · %.3f fps · 时长 %s"
                % (
                    result["name"],
                    len(clips),
                    summary["width"],
                    summary["height"],
                    summary["fps"],
                    result["duration"],
                ),
                "#6ee7b7",
            )
            self._log(
                "建线完成：%s（%d 个素材，%dx%d，%.3f fps，%s）。"
                % (
                    result["name"],
                    len(clips),
                    summary["width"],
                    summary["height"],
                    summary["fps"],
                    result["duration"],
                )
            )
            if summary["mixed_resolution"]:
                self._log("分辨率不一致：已按最大分辨率建线，其余素材按项目缩放设置适配。")
            if summary["mixed_fps"]:
                self._log("帧率不一致：已按最常见帧率建线，个别素材可能被 Resolve 做帧率适配。")
            self.refresh_all()
        except Exception as exc:
            self._set("build_status", "建线失败：%s" % exc, "#f87171")
            self._log("建线失败：%s" % exc)
            self._log(traceback.format_exc())

    # -------------------------------------------------------------- targets
    def _targets(self, scope):
        context = self._context()
        timeline = context["timeline"]
        if timeline is None:
            raise rb.ColorFlowError("当前没有打开的时间线。")
        items = rb.video_items(timeline, scope, context["clip"])
        return context, items

    # --------------------------------------------------------------- write
    def _choose_node(self, clip):
        nodes = rb.list_nodes(clip)
        if not nodes:
            raise rb.ColorFlowError("当前镜头没有节点，无法写入。")
        auto = bool(self._find("chk_auto_node").Checked)
        allow_nonempty = bool(self._find("chk_allow_nonempty").Checked)
        if auto:
            empty = [node for node in nodes if node["likely_empty"]]
            managed = [node for node in nodes if node.get("managed")]
            if empty:
                node = empty[-1]
            elif managed:
                node = managed[-1]
            else:
                node = nodes[-1]
            if not empty and not managed and not allow_nonempty:
                raise rb.ColorFlowError(
                    "当前镜头没有疑似空白节点，也没有 ColorFlow 文件。请在 Color 页面添加一个串行节点，"
                    "或勾选“允许写非空节点”。"
                )
            return node
        index = int(self._find("node_combo").CurrentIndex) + 1
        node = next((item for item in nodes if item["index"] == index), None)
        if node is None:
            raise rb.ColorFlowError("选中的节点在当前镜头上不存在。")
        if not node["likely_empty"] and not allow_nonempty:
            raise rb.ColorFlowError(
                "选中的 %02d 号节点已有工具或 LUT。请换空白节点，"
                "或勾选“允许写非空节点”。" % index
            )
        return node

    def _write_model(self, context, clip, model, label):
        project = context["project"]
        space_key, space_label = rb.project_color_space(project)
        node = self._choose_node(clip)
        backup = None
        version_name = None
        if bool(self._find("chk_backup").Checked):
            backup, version_name = rb.create_backup_version(clip, label)

        engine = None
        detail = None
        try:
            if space_key == "dwg" or node.get("lut"):
                text = analysis.model_to_dctl(
                    model, "dwg" if space_key == "dwg" else "rec709", label
                )
                path, relative = rb.write_dctl(text, label)
                detail = rb.apply_lut(project, clip, node["index"], path, relative)
                engine = "DCTL"
            else:
                cdl = analysis.model_to_cdl(model, node["index"])
                try:
                    rb.apply_cdl(clip, node["index"], cdl)
                    engine = "CDL"
                    detail = cdl
                except Exception:
                    text = analysis.model_to_dctl(model, "rec709", label)
                    path, relative = rb.write_dctl(text, label)
                    detail = rb.apply_lut(project, clip, node["index"], path, relative)
                    engine = "DCTL fallback"
        except Exception:
            if backup is not None:
                previous_name = backup.get("versionName")
                previous_type = backup.get("versionType", 0)
                if previous_name:
                    try:
                        rb.restore_version(clip, previous_name, previous_type)
                    except Exception:
                        pass
            raise
        return {
            "node": node,
            "engine": engine,
            "detail": detail,
            "space": space_label,
            "backup": backup,
            "version_name": version_name,
            "model": model,
        }

    def _remember_backup(self, clip, backup):
        if not backup:
            return
        name = backup.get("versionName")
        if not name:
            return
        self.last_backups.append(
            (clip, name, int(backup.get("versionType", 0) or 0))
        )

    # --------------------------------------------------------------- reset
    def on_reset(self, event):
        try:
            scope = self._scope("scope_restore")
            context, items = self._targets(scope)
            if not items:
                raise rb.ColorFlowError("没有可处理的镜头。")
            self._set("restore_status", "正在备份并还原 %d 个镜头…" % len(items), "#fbbf24")
            self.pump()
            successes = 0
            failures = []
            for item in items:
                if self._cancel_requested:
                    break
                backup = None
                try:
                    backup, version_name = rb.create_backup_version(item, "还原前")
                    rb.reset_grade(item)
                    self._remember_backup(item, backup)
                    successes += 1
                    self._log("已还原原始：%s（备份版本 %s）。" % (item.GetName(), version_name))
                except Exception as exc:
                    if backup:
                        previous_name = backup.get("versionName")
                        previous_type = backup.get("versionType", 0)
                        if previous_name:
                            try:
                                rb.restore_version(item, previous_name, previous_type)
                            except Exception:
                                pass
                    failures.append((item.GetName(), str(exc)))
                    self._log("还原失败：%s：%s" % (item.GetName(), exc))
                self.pump()
            try:
                context["project_manager"].SaveProject()
            except Exception:
                pass
            if failures:
                self._set(
                    "restore_status",
                    "完成 %d 个，失败 %d 个。首个错误：%s"
                    % (successes, len(failures), failures[0][1]),
                    "#f87171",
                )
            else:
                self._set(
                    "restore_status",
                    "已备份并还原 %d 个镜头的原始状态。" % successes,
                    "#6ee7b7",
                )
            self.refresh_nodes()
        except Exception as exc:
            self._set("restore_status", "还原失败：%s" % exc, "#f87171")
            self._log("还原失败：%s" % exc)

    # ----------------------------------------------------------- neutralize
    def on_neutralize(self, event):
        try:
            scope = self._scope("scope_restore")
            strength = self._strength("spin_restore")
            context, items = self._targets(scope)
            self._set(
                "restore_status",
                "正在分析并去色偏 %d 个镜头…" % len(items),
                "#fbbf24",
            )
            self.pump()
            successes = 0
            failures = []
            for item in items:
                if self._cancel_requested:
                    break
                try:
                    capture = rb.capture_item_thumbnail(context["timeline"], item)
                    model = analysis.restore_model(
                        capture["stats"],
                        strength,
                        bool(self._find("chk_restore_tone").Checked),
                    )
                    result = self._write_model(
                        context, item, model, "还原-%s" % item.GetName()
                    )
                    self._remember_backup(item, result["backup"])
                    successes += 1
                    self._log(
                        "%s → %02d 号节点（%s，%s）：%s｜%s"
                        % (
                            item.GetName(),
                            result["node"]["index"],
                            result["engine"],
                            result["space"],
                            analysis.describe_model(model),
                            analysis.describe_stats(capture["stats"]),
                        )
                    )
                except Exception as exc:
                    failures.append((item.GetName(), str(exc)))
                    self._log("去色偏失败：%s：%s" % (item.GetName(), exc))
                self.pump()
            try:
                context["project_manager"].SaveProject()
            except Exception:
                pass
            if failures:
                self._set(
                    "restore_status",
                    "完成 %d 个，失败 %d 个。首个错误：%s"
                    % (successes, len(failures), failures[0][1]),
                    "#f87171",
                )
            else:
                self._set(
                    "restore_status",
                    "已对 %d 个镜头做曝光/白平衡还原，写入前均已建版本。"
                    % successes,
                    "#6ee7b7",
                )
            self.refresh_nodes()
        except Exception as exc:
            self._set("restore_status", "去色偏失败：%s" % exc, "#f87171")
            self._log("去色偏失败：%s" % exc)
            self._log(traceback.format_exc())

    # ------------------------------------------------------------- reference
    def on_reference(self, event):
        try:
            context = self._context()
            if context["timeline"] is None or context["clip"] is None:
                raise rb.ColorFlowError("请先把播放头放在一个视频镜头上。")
            capture = rb.capture_item_thumbnail(
                context["timeline"], context["clip"]
            )
            self.reference = {
                "name": capture["name"],
                "stats": capture["stats"],
                "clip_id": context["clip"].GetUniqueId(),
                "thumbnail": capture["thumbnail"],
            }
            self._set(
                "reference_info",
                "参考：%s（已锁定）" % capture["name"],
                "#6ee7b7",
            )
            self._log(
                "参考镜头已锁定：%s｜%s"
                % (capture["name"], analysis.describe_stats(capture["stats"]))
            )
        except Exception as exc:
            self._set("reference_info", "设置参考失败：%s" % exc, "#f87171")
            self._log("设置参考失败：%s" % exc)

    # ----------------------------------------------------------------- match
    def on_match(self, event):
        try:
            if self.reference is None:
                raise rb.ColorFlowError(
                    "请先把播放头放在参考镜头上，点击“以当前镜头为参考”。"
                )
            scope = self._scope("scope_match")
            strength = self._strength("spin_match")
            context, items = self._targets(scope)
            targets = []
            for item in items:
                try:
                    if item.GetUniqueId() == self.reference["clip_id"]:
                        continue
                except Exception:
                    pass
                targets.append(item)
            if not targets:
                raise rb.ColorFlowError("目标镜头为空，或只选中了参考镜头本身。")
            self._set(
                "match_status",
                "正在匹配 %d 个镜头到“%s”…"
                % (len(targets), self.reference["name"]),
                "#fbbf24",
            )
            self.pump()
            successes = 0
            failures = []
            for item in targets:
                if self._cancel_requested:
                    break
                try:
                    capture = rb.capture_item_thumbnail(context["timeline"], item)
                    model = analysis.match_model(
                        self.reference["stats"], capture["stats"], strength
                    )
                    result = self._write_model(
                        context, item, model, "匹配-%s" % item.GetName()
                    )
                    self._remember_backup(item, result["backup"])
                    successes += 1
                    self._log(
                        "%s → %02d 号节点（%s）：%s｜目标 %s｜参考 %s"
                        % (
                            item.GetName(),
                            result["node"]["index"],
                            result["engine"],
                            analysis.describe_model(model),
                            analysis.describe_stats(capture["stats"]),
                            self.reference["name"],
                        )
                    )
                except Exception as exc:
                    failures.append((item.GetName(), str(exc)))
                    self._log("匹配失败：%s：%s" % (item.GetName(), exc))
                self.pump()
            try:
                context["project_manager"].SaveProject()
            except Exception:
                pass
            if failures:
                self._set(
                    "match_status",
                    "完成 %d 个，失败 %d 个。首个错误：%s"
                    % (successes, len(failures), failures[0][1]),
                    "#f87171",
                )
            else:
                self._set(
                    "match_status",
                    "已匹配 %d 个镜头到参考“%s”。"
                    % (successes, self.reference["name"]),
                    "#6ee7b7",
                )
            self.refresh_nodes()
        except Exception as exc:
            self._set("match_status", "匹配失败：%s" % exc, "#f87171")
            self._log("匹配失败：%s" % exc)
            self._log(traceback.format_exc())

    # ------------------------------------------------------------------ undo
    def on_undo(self, event):
        if not self.last_backups:
            self._set("node_status", "没有可撤销的本次写入记录。", "#fbbf24")
            return
        restored = 0
        for clip, name, version_type in reversed(self.last_backups):
            try:
                if rb.restore_version(clip, name, version_type):
                    restored += 1
                    self._log("已恢复版本：%s → %s" % (clip.GetName(), name))
            except Exception as exc:
                self._log("恢复版本失败：%s：%s" % (clip.GetName(), exc))
        self.last_backups = []
        try:
            context = self._context()
            context["project_manager"].SaveProject()
        except Exception:
            pass
        self._set(
            "node_status",
            "已恢复 %d 个镜头的写入前版本。" % restored,
            "#6ee7b7" if restored else "#f87171",
        )
        self.refresh_nodes()

    # ---------------------------------------------------------------- lifecycle
    def on_close(self, event):
        if self._closing:
            return
        self._closing = True
        self._cancel_requested = True
        try:
            self.dispatcher.ExitLoop()
        except Exception:
            pass

    def show(self):
        existing = self.ui.FindWindow(self.window_id)
        if existing is not None:
            existing.Show()
            existing.Raise()
            return
        self.win = self._build_window()
        self._connect()
        self.win.Show()
        self.refresh_all()
        self._log("ColorFlow 已启动。素材与节点只会写入本机 Resolve 项目。")
        self.dispatcher.RunLoop()
        # ExitLoop only stops the dispatcher. The remote UIManager window must
        # be closed explicitly after the loop returns, otherwise Resolve keeps
        # an unresponsive ghost window around.
        try:
            closed = self.win.Close()
        except Exception:
            closed = False
        if not closed:
            try:
                self.win.Hide()
            except Exception:
                pass


def run(globals_dict):
    resolve = globals_dict.get("resolve")
    fusion = globals_dict.get("fusion")
    bmd = globals_dict.get("bmd")
    if resolve is None or fusion is None or bmd is None:
        raise RuntimeError(
            "ColorFlow 需要从 DaVinci Resolve 的 Workspace > Workflow Integrations 启动。"
        )
    app = ColorFlowApp(resolve, fusion, bmd)
    app.show()

