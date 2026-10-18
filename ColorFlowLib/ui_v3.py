"""ColorFlow v3 — flat, preview-first Resolve panel.

UIManager's deeply nested layouts are fragile. This version uses a flat
single-column page structure and puts preview images plus metadata into one
HTML label, which renders reliably.
"""

import html
import os
import time

from . import analysis
from . import features
from . import lut_gallery
from . import preview
from . import resolve_bridge as rb
from .version import VERSION, BUILD_DATE
from .ui_v2 import (
    ColorFlowApp as V2App,
    STYLE,
    SIDE_ACTIVE,
    SIDE_IDLE,
    TAB_ACTIVE,
    TAB_IDLE,
)


def _guarded(method):
    """Prevent re-entrant long operations from nested UI events."""

    def wrapper(self, event=None):
        if getattr(self, "_busy", False):
            self._log("正在处理上一个操作，请稍候。")
            return
        self._busy = True
        try:
            return method(self, event)
        finally:
            self._busy = False

    return wrapper


TITLES = {
    "title_analysis": ("素材与预览", "元数据 · Log · 裁切风险", "Footage & Preview", "Metadata · Log · clipping risks"),
    "title_normalize": ("技术归一", "黑白场 · 白平衡 · 曝光 · LUT", "Technical Normalize", "Levels · white balance · exposure · LUT"),
    "title_match": ("参考匹配", "参考 → 目标 → 结果", "Reference Match", "Reference → target → result"),
    "title_skin": ("肤色限定", "YCbCr 遮罩 · 背景降饱和", "Skin Qualifier", "YCbCr mask · background desaturation"),
    "title_batch": ("预设与批量", "DRX · 批量套用 · QC 报告", "Presets & Batch", "DRX · batch apply · QC report"),
    "title_tree": ("节点树", "DRX 模板", "Node Tree", "DRX template"),
    "title_auto": ("自动校正", "黑白场 / 白平衡 / 曝光", "Auto Correction", "Levels / white balance / exposure"),
    "title_save_preset": ("保存预设", "当前节点链 → DRX", "Save Preset", "Current node chain → DRX"),
    "title_preset_lib": ("预设库", "收藏 / 删除 / 批量", "Preset Library", "Favorite / delete / batch"),
    "title_report": ("报告", "QC / 不匹配 / 裁切", "Report", "QC / mismatch / clipping"),
}

BUTTON_TEXTS = {
    "tab_0": ("素材分析", "Analysis"),
    "tab_1": ("技术归一", "Normalize"),
    "tab_2": ("参考匹配", "Match"),
    "tab_3": ("批量报告", "Batch"),
    "btn_refresh_analysis": ("刷新当前帧", "Refresh Frame"),
    "btn_fix_warnings": ("一键处理警告", "Fix Warnings"),
    "btn_refresh_nodes_top": ("刷新节点", "Refresh Nodes"),
    "btn_build": ("按素材建线", "Build Timeline"),
    "btn_refresh_media": ("刷新媒体池", "Refresh Media"),
    "btn_make_tree": ("套用节点模板", "Apply Node Template"),
    "btn_make_template": ("从当前节点链生成模板", "Generate Template"),
    "btn_save_template_preserve": ("保存当前链为模板", "Save as Template"),
    "btn_one_click_restore": ("一键还原", "One-Click Restore"),
    "btn_auto_bw": ("自动黑白场", "Auto Black/White"),
    "btn_auto_wb": ("自动白平衡", "Auto White Balance"),
    "btn_auto_exposure": ("曝光拉伸", "Exposure Stretch"),
    "btn_reset": ("还原原始（清空）", "Reset Original"),
    "btn_undo": ("撤销", "Undo"),
    "btn_refresh_luts": ("刷新", "Refresh"),
    "btn_browse_lut": ("浏览", "Browse"),
    "btn_lut_gallery": ("LUT 图库", "LUT Gallery"),
    "btn_gallery_prev": ("上一页", "Previous"),
    "btn_gallery_next": ("下一页", "Next"),
    "btn_apply_lut": ("套用", "Apply"),
    "btn_remove_lut": ("移除", "Remove"),
    "btn_reference": ("拾取当前帧", "Pick Current Frame"),
    "btn_reference_gallery": ("从画廊引用", "From Gallery"),
    "btn_reference_file": ("本地单帧", "Local Frame"),
    "btn_gallery_ref_use": ("使用所选静帧", "Use Selected Still"),
    "btn_gallery_ref_cancel": ("取消", "Cancel"),
    "btn_match": ("匹配参考色调", "Match Reference"),
    "btn_undo_match": ("撤销本次匹配", "Undo Match"),
    "btn_skin": ("生成肤色限定", "Create Skin Qualifier"),
    "btn_save_preset": ("保存 DRX", "Save DRX"),
    "btn_presets_refresh": ("刷新", "Refresh"),
    "btn_preset_fav": ("收藏", "Favorite"),
    "btn_preset_delete": ("删除", "Delete"),
    "btn_apply_preset": ("应用到当前", "Apply to Current"),
    "btn_batch_preset": ("批量应用", "Batch Apply"),
    "btn_report": ("校验时间线并输出报告", "Validate & Report"),
    "btn_close": ("关闭面板", "Close Panel"),
}

COMBO_TEXTS = {
    "lut_category": (
        ["全部", "SLog3", "ARRI", "HLG", "CLog", "Rec.709", "自定义"],
        ["All", "SLog3", "ARRI", "HLG", "CLog", "Rec.709", "Custom"],
    ),
    "match_scope": (
        ["当前镜头", "选中/当前镜头", "整条时间线"],
        ["Current", "Selected/Current", "Whole Timeline"],
    ),
    "restore_scope": (
        ["当前镜头", "选中/当前镜头", "整条时间线"],
        ["Current", "Selected/Current", "Whole Timeline"],
    ),
    "preset_scope": (
        ["当前镜头", "选中/当前镜头", "整条时间线"],
        ["Current", "Selected/Current", "Whole Timeline"],
    ),
    "preset_filter": (
        ["全部预设", "收藏预设"],
        ["All Presets", "Favorites"],
    ),
    "preset_category": (
        ["外景", "室内", "漫剧夜景", "自定义"],
        ["Exterior", "Interior", "Drama Night", "Custom"],
    ),
}

LUT_CATEGORY_KEYS = (
    "全部",
    "SLog3",
    "ARRI",
    "HLG",
    "CLog",
    "Rec.709",
    "自定义",
)
LUT_CATEGORY_EN = {
    "全部": "All",
    "自定义": "Custom",
}

LABEL_TEXTS = {
    "调色助手": "Color Assistant",
    "本地处理 · 不上传素材": "Local processing · no uploads",
    "运行日志": "Run Log",
    "尚未设置参考": "No reference selected",
    "选择画廊静帧": "Select Gallery Still",
    "没有可用的画廊静帧": "No gallery stills",
    "尚未生成报告": "No report yet",
    "还原范围": "Restore Scope",
    "分节点顺序：01 降噪 → 02 曝光 → 03 色温 → 04 饱和 → 最后空白节点留给匹配": "Node order: 01 Denoise → 02 Exposure → 03 Temperature → 04 Saturation → Last blank for match",
    "强度": "Strength",
    "节点": "Node",
    "范围": "Range",
    "色相": "Hue",
    "饱和": "Saturation",
    "亮度": "Lightness",
    "含子文件夹": "Include Subfolders",
    "按角色选节点": "Select by Role",
    "建版本": "Create Version",
    "允许非空": "Allow Non-empty",
    "背景降饱和": "Desaturate Background",
    "无预览": "No preview",
    "未打开时间线": "No timeline",
}
EN_TO_ZH = {value: key for key, value in LABEL_TEXTS.items()}


class ColorFlowApp(V2App):
    def __init__(self, resolve, fusion, bmd):
        super().__init__(resolve, fusion, bmd)
        self._busy = False
        self._pumping = False
        self.language = "zh"
        self._translating = False
        self._gallery_win = None
        self._gallery_entries = []
        self._gallery_filtered = []
        self._gallery_selected = None
        self._gallery_page = 0
        self._gallery_page_size = 24
        self._gallery_source = None
        self._gallery_tree = None
        self._gallery_by_name = {}
        self._gallery_by_path = {}
        self._gallery_category = None
        self._gallery_status = None
        self._gallery_preview = None
        self._gallery_info = None
        self._gallery_page_label = None
        self._gallery_prev = None
        self._gallery_next = None
        self._gallery_highlight_item = None
        self._gallery_highlight_entry = None
        self._gallery_selecting = False
        self._ref_picker_win = None
        self._ref_picker_entries = []
        self._ref_picker_combo = None

    def pump(self):
        # StepLoop is useful for keeping the close button responsive, but it
        # must never be entered recursively from inside a dispatched event.
        if getattr(self, "_pumping", False):
            return
        self._pumping = True
        try:
            try:
                self.dispatcher.StepLoop()
            except Exception:
                pass
            try:
                self.win.Update()
                self.win.Repaint()
            except Exception:
                pass
        finally:
            self._pumping = False

    def _build_widget_registry(self):
        self.widgets = {}
        self.all_widgets = []

        def walk(widget, depth=0):
            if depth > 6:
                return
            try:
                items = widget.GetItems() or {}
            except Exception:
                return
            for key, child in items.items():
                if key:
                    self.widgets[str(key)] = child
                self.all_widgets.append(child)
                walk(child, depth + 1)

        walk(self.win)

    def _connect(self):
        super()._connect()
        self.win.On["btn_one_click_restore"].Clicked = self.on_split_restore
        self.win.On["btn_save_template_preserve"].Clicked = self.on_save_template_preserve
        self.win.On["btn_undo_match"].Clicked = self.on_undo_match
        self.win.On["btn_fix_warnings"].Clicked = self.on_fix_warnings
        self.win.On["btn_lut_gallery"].Clicked = self.on_lut_gallery
        self.win.On["btn_reference_gallery"].Clicked = self.on_reference_gallery
        self.win.On["btn_reference_file"].Clicked = self.on_reference_file
        lang = self._find("lang_combo")
        lang.Clear()
        lang.AddItems(["中文", "English"])
        lang.CurrentIndex = 0
        lang.CurrentIndexChanged = self.on_language_changed

    def on_language_changed(self, event):
        if getattr(self, "_translating", False):
            return
        self.language = (
            "en" if int(self._find("lang_combo").CurrentIndex) == 1 else "zh"
        )
        self.apply_language()

    def apply_language(self):
        if getattr(self, "_translating", False):
            return
        self._translating = True
        try:
            if self._gallery_win is not None:
                self.on_gallery_close(None)
            if self._ref_picker_win is not None:
                self.on_reference_picker_close(None)
            lang = self.language
            for widget_id, (zh, en) in BUTTON_TEXTS.items():
                widget = self._find(widget_id)
                if widget is not None:
                    try:
                        widget.Text = en if lang == "en" else zh
                    except Exception:
                        pass
            for widget_id in TITLES:
                widget = self._find(widget_id)
                if widget is None:
                    continue
                zh_text, zh_sub, en_text, en_sub = TITLES[widget_id]
                text, sub = (
                    (en_text, en_sub) if lang == "en" else (zh_text, zh_sub)
                )
                widget.Text = (
                    '<span style="color:#22d3ee;font-weight:700;">%s</span>'
                    '<span style="color:#6d7c8e;">  %s</span>'
                    % (text, sub)
                )
            for widget in getattr(self, "all_widgets", []):
                try:
                    text = widget.Text
                except Exception:
                    continue
                if not isinstance(text, str):
                    continue
                try:
                    if lang == "en" and text in LABEL_TEXTS:
                        widget.Text = LABEL_TEXTS[text]
                    elif lang == "zh" and text in EN_TO_ZH:
                        widget.Text = EN_TO_ZH[text]
                except Exception:
                    pass
            for widget_id, (zh_items, en_items) in COMBO_TEXTS.items():
                combo = self._find(widget_id)
                if combo is None:
                    continue
                index = int(combo.CurrentIndex)
                combo.Clear()
                combo.AddItems(en_items if lang == "en" else zh_items)
                combo.CurrentIndex = index
            try:
                self._find("preset_name").PlaceholderText = self._t(
                    "预设名称", "Preset name"
                )
            except Exception:
                pass
            for widget_id in (
                "build_status",
                "tree_status",
                "primary_status",
                "lut_status",
                "match_status",
                "skin_status",
                "preset_status",
                "report_status",
            ):
                self._set(widget_id, "", "#8b98a8")
            self.refresh_context()
            self.refresh_analysis()
            self.refresh_media()
            self.refresh_nodes()
            if self.reference:
                self._set(
                    "reference_info",
                    self._t(
                        "参考：%s（已锁定）", "Reference: %s (locked)"
                    )
                    % self.reference.get("name", ""),
                    "#6ee7b7",
                )
            else:
                self._set(
                    "reference_info",
                    self._t("尚未设置参考", "No reference selected"),
                    "#8b98a8",
                )
            self._update_match_visual()
        finally:
            self._translating = False

    def refresh_context(self):
        try:
            context = self._context()
        except Exception as exc:
            self._set(
                "ctx_project",
                self._t("项目：", "Project: ") + str(exc),
                "#f87171",
            )
            return None
        project = context["project"]
        timeline = context["timeline"]
        clip = context["clip"]
        space_key, space_label = self._space(context)
        self._set(
            "ctx_project",
            self._t("项目：", "Project: ") + project.GetName(),
            "#d7dce3",
        )
        self._set(
            "ctx_timeline",
            self._t("时间线：", "Timeline: ")
            + (timeline.GetName() if timeline else self._t("未打开", "None")),
            "#d7dce3",
        )
        self._set(
            "ctx_clip",
            self._t("当前镜头：", "Clip: ")
            + (clip.GetName() if clip else self._t("无", "None")),
            "#d7dce3",
        )
        self._set(
            "ctx_space",
            self._t("色彩空间：", "Color Space: ") + space_label,
            "#6ee7b7" if space_key == "dwg" else "#fbbf24",
        )
        return context

    def refresh_media(self):
        try:
            context = self._context()
            recursive = bool(self._find("chk_recursive").Checked)
            clips, origin = rb.media_clips(context["project"], recursive)
            if not clips:
                self._set(
                    "source_info",
                    self._t(
                        "当前媒体池文件夹没有视频素材。",
                        "No video clips in the current media pool folder.",
                    ),
                    "#fbbf24",
                )
                return
            summary = rb.source_summary(clips)
            warning = ""
            if summary["mixed_resolution"]:
                warning += self._t(" · 分辨率不一致", " · mixed resolutions")
            if summary["mixed_fps"]:
                warning += self._t(" · 帧率不一致", " · mixed frame rates")
            if self.language == "en":
                text = "%s · %d clips · %dx%d · %.3f fps%s" % (
                    origin,
                    len(clips),
                    summary["width"],
                    summary["height"],
                    summary["fps"],
                    warning,
                )
            else:
                text = "%s · %d 个素材 · %dx%d · %.3f fps%s" % (
                    origin,
                    len(clips),
                    summary["width"],
                    summary["height"],
                    summary["fps"],
                    warning,
                )
            self._set(
                "source_info", text, "#fbbf24" if warning else "#d7dce3"
            )
        except Exception as exc:
            self._set(
                "source_info",
                self._t("读取素材失败：%s", "Media read failed: %s") % exc,
                "#f87171",
            )

    def _node_label_lang(self, node):
        label = rb.node_label(node)
        if self.language == "en":
            label = (
                label.replace("疑似空白", "likely empty")
                .replace("ColorFlow 文件", "ColorFlow file")
                .replace("已有 LUT", "has LUT")
                .replace("个工具", "tools")
            )
        return label

    def refresh_nodes(self):
        try:
            context = self._require_clip()
            nodes = self._nodes(context["clip"])
        except Exception as exc:
            nodes = []
            self._set(
                "primary_status",
                self._t(str(exc), "No current clip or nodes."),
                "#fbbf24",
            )
        combo = self._find("node_combo")
        combo.Clear()
        if not nodes:
            combo.AddItem(self._t("没有可用节点", "No available nodes"))
            return
        combo.AddItems([self._node_label_lang(node) for node in nodes])
        empty = [
            index
            for index, node in enumerate(nodes)
            if node.get("likely_empty")
        ]
        index = empty[-1] if empty else len(nodes) - 1
        combo.CurrentIndex = index
        self._set(
            "primary_status",
            self._t("节点：%s", "Node: %s")
            % self._node_label_lang(nodes[index]),
            "#6ee7b7" if nodes[index].get("likely_empty") else "#fbbf24",
        )

    def _warning_text(self, warnings):
        if self.language != "en":
            return " · ".join(warnings)
        translated = []
        for warning in warnings:
            if warning.startswith("素材 ") and "与时间线" in warning:
                translated.append(
                    "Source/timeline FPS mismatch"
                    if "fps" in warning
                    else "Source/timeline resolution mismatch"
                )
            elif "高光" in warning:
                translated.append("Highlights near clipping")
            elif "暗部" in warning:
                translated.append("Shadows near clipping")
            elif "高饱和" in warning or "色域" in warning:
                translated.append("High saturation / gamut risk")
            else:
                translated.append(warning)
        return " · ".join(translated)

    # ------------------------------------------------------------- LUT gallery
    @_guarded
    def on_lut_gallery(self, event):
        try:
            if self._gallery_win is not None:
                self._gallery_win.Show()
                self._gallery_win.Raise()
                return
            if not self.lut_entries:
                self.refresh_luts()
            self._gallery_source = lut_gallery.standard_source()
            self._open_lut_gallery()
        except Exception as exc:
            self._set(
                "lut_status",
                self._t("打开 LUT 图库失败：%s", "Open LUT gallery failed: %s")
                % exc,
                "#f87171",
            )

    def on_close(self, event):
        if self._gallery_win is not None:
            try:
                self._gallery_win.Hide()
            except Exception:
                pass
            self._release_gallery_refs()
        if self._ref_picker_win is not None:
            try:
                self._ref_picker_win.Hide()
            except Exception:
                pass
            self._ref_picker_win = None
        super().on_close(event)

    def _open_lut_gallery(self):
        category_items = COMBO_TEXTS["lut_category"][
            1 if self.language == "en" else 0
        ]
        gallery_id = self.window_id + ".lutgallery"
        self._gallery_tree = self.ui.Tree(
            {
                "ID": "gallery_tree",
                "ColumnCount": 1,
                "HeaderHidden": True,
                "IconSize": [160, 90],
                "MinimumSize": [540, 500],
                "AlternatingRowColors": True,
                "RootIsDecorated": False,
                "SelectionMode": "SingleSelection",
                "SortingEnabled": False,
            }
        )
        self._gallery_category = self.ui.ComboBox(
            {
                "ID": "gallery_category",
                "ItemText": category_items,
                "CurrentIndex": 0,
                "MinimumSize": [130, 30],
            }
        )
        self._gallery_category.Clear()
        self._gallery_category.AddItems(category_items)
        self._gallery_category.CurrentIndex = 0
        self._gallery_status = self.ui.Label(
            {
                "ID": "gallery_status",
                "Text": "",
                "WordWrap": True,
                "MaximumSize": [520, 30],
                "StyleSheet": "color:#8b98a8;",
            }
        )
        self._gallery_preview = self.ui.Label(
            {
                "ID": "gallery_preview",
                "Text": self._t("选择 LUT 查看预览", "Select a LUT"),
                "Alignment": "AlignCenter",
                "MinimumSize": [340, 200],
                "MaximumSize": [340, 200],
                "StyleSheet": "background-color:#11151b;border:1px solid #2b333f;border-radius:8px;color:#6d7c8e;",
            }
        )
        self._gallery_info = self.ui.Label(
            {
                "ID": "gallery_info",
                "Text": "",
                "WordWrap": True,
                "MaximumSize": [340, 90],
                "StyleSheet": "color:#c7d4e3;",
            }
        )
        apply_button = self.ui.Button(
            {
                "ID": "btn_gallery_apply",
                "Text": self._t("套用 LUT", "Apply LUT"),
                "MinimumSize": [110, 32],
                "MaximumSize": [120, 32],
                "StyleSheet": TAB_ACTIVE,
            }
        )
        close_button = self.ui.Button(
            {
                "ID": "btn_gallery_close",
                "Text": self._t("关闭", "Close"),
                "MinimumSize": [80, 32],
                "MaximumSize": [90, 32],
            }
        )
        self._gallery_prev = self.ui.Button(
            {
                "ID": "btn_gallery_prev",
                "Text": self._t("上一页", "Previous"),
                "MinimumSize": [82, 30],
                "MaximumSize": [92, 30],
            }
        )
        self._gallery_page_label = self.ui.Label(
            {
                "ID": "gallery_page",
                "Text": "",
                "Alignment": "AlignCenter",
                "MinimumSize": [120, 30],
                "MaximumSize": [140, 30],
                "StyleSheet": "color:#8b98a8;",
            }
        )
        self._gallery_next = self.ui.Button(
            {
                "ID": "btn_gallery_next",
                "Text": self._t("下一页", "Next"),
                "MinimumSize": [82, 30],
                "MaximumSize": [92, 30],
            }
        )
        root = self.ui.VGroup(
            {"Spacing": 8, "Weight": 1},
            [
                self.ui.HGroup(
                    {"Spacing": 8},
                    [
                        self.ui.Label(
                            {
                                "Text": self._t("LUT 图库", "LUT Gallery"),
                                "StyleSheet": "color:#22d3ee;font-size:14pt;font-weight:700;",
                            }
                        ),
                        self._gallery_category,
                        self._gallery_status,
                    ],
                ),
                self.ui.HGroup(
                    {"Spacing": 10, "Weight": 1},
                    [
                        self._gallery_tree,
                        self.ui.VGroup(
                            {"Spacing": 6},
                            [
                                self.ui.Label(
                                    {
                                        "Text": self._t(
                                            "选中预览", "Selected preview"
                                        ),
                                        "StyleSheet": "color:#7d8b9d;",
                                    }
                                ),
                                self._gallery_preview,
                                self._gallery_info,
                                self.ui.HGroup(
                                    {"Spacing": 6},
                                    [
                                        self._gallery_prev,
                                        self._gallery_page_label,
                                        self._gallery_next,
                                        self.ui.HGap(0, 1),
                                    ],
                                ),
                                self.ui.HGroup(
                                    {"Spacing": 6},
                                    [
                                        apply_button,
                                        close_button,
                                        self.ui.HGap(0, 1),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        )
        gallery_win = self.dispatcher.AddWindow(
            {
                "ID": gallery_id,
                "Geometry": [220, 90, 980, 720],
                "WindowTitle": self._t(
                    "ColorFlow · LUT 图库", "ColorFlow · LUT Gallery"
                ),
                "StyleSheet": STYLE,
            },
            root,
        )
        self._gallery_win = gallery_win
        gallery_win.On[gallery_id].Close = self.on_gallery_close
        gallery_win.On["gallery_category"].CurrentIndexChanged = (
            self.on_gallery_category
        )
        gallery_win.On["gallery_tree"].CurrentItemChanged = (
            self.on_gallery_tree_changed
        )
        gallery_win.On["gallery_tree"].ItemDoubleClicked = (
            self.on_gallery_double_click
        )
        gallery_win.On["btn_gallery_apply"].Clicked = self.on_gallery_apply
        gallery_win.On["btn_gallery_close"].Clicked = self.on_gallery_close
        gallery_win.On["btn_gallery_prev"].Clicked = self.on_gallery_prev
        gallery_win.On["btn_gallery_next"].Clicked = self.on_gallery_next
        gallery_win.Show()
        self._reload_gallery()

    def _reload_gallery(self):
        if self._gallery_win is None:
            return
        try:
            category_index = int(self._gallery_category.CurrentIndex)
        except Exception:
            category_index = 0
        category = LUT_CATEGORY_KEYS[
            max(0, min(len(LUT_CATEGORY_KEYS) - 1, category_index))
        ]
        if category == "全部":
            filtered = list(self.lut_entries)
        else:
            filtered = [
                entry
                for entry in self.lut_entries
                if entry["category"] == category
            ]
        if not filtered:
            self._gallery_tree.Clear()
            self._gallery_entries = []
            self._gallery_filtered = []
            self._gallery_page = 0
            self._gallery_status.Text = self._t(
                "没有匹配的 LUT", "No matching LUTs"
            )
            self._gallery_preview.Text = self._t(
                "无可用 LUT", "No available LUTs"
            )
            self._gallery_info.Text = ""
            self._update_gallery_page_label()
            return
        filtered.sort(
            key=lambda entry: (
                0
                if entry["absolute"].lower().endswith(".cube")
                else 1,
                entry["category"],
                entry["name"].lower(),
            )
        )
        self._gallery_filtered = filtered
        page_count = max(
            1,
            (len(filtered) + self._gallery_page_size - 1)
            // self._gallery_page_size,
        )
        self._gallery_page = max(0, min(self._gallery_page, page_count - 1))
        start = self._gallery_page * self._gallery_page_size
        end = min(len(filtered), start + self._gallery_page_size)
        page_entries = filtered[start:end]
        self._gallery_status.Text = self._t(
            "正在生成预览…", "Generating previews…"
        )
        self._gallery_pump()

        def progress(done, total):
            if done % 4 == 0 or done == total:
                self._gallery_status.Text = self._t(
                    "正在生成预览 %d/%d…", "Generating previews %d/%d…"
                ) % (done, total)

        entries = lut_gallery.build_entries(
            page_entries,
            self._gallery_source,
            limit=self._gallery_page_size,
            progress=progress,
        )
        self._gallery_entries = entries
        self._gallery_by_name = {
            entry["name"]: entry for entry in entries
        }
        self._gallery_by_path = {
            entry["relative"]: entry for entry in entries
        }
        self._populate_gallery_tree(entries)
        try:
            self._gallery_tree.SetColumnWidth(0, 540)
        except Exception:
            pass
        self._gallery_status.Text = self._t(
            "显示 %d–%d / %d（缩略图仅支持 .cube）",
            "Showing %d–%d / %d (thumbnails for .cube only)",
        ) % (start + 1 if entries else 0, end, len(filtered))
        self._update_gallery_page_label()
        if entries:
            top_item = self._gallery_tree.TopLevelItem(0)
            top_entry = entries[0]
            try:
                top_relative = str(top_item.ToolTip[0])
                top_entry = self._gallery_by_path.get(
                    top_relative, entries[0]
                )
            except Exception:
                pass
            self._highlight_gallery_item(top_item, top_entry)
            try:
                self._gallery_tree.ScrollToItem(top_item)
            except Exception:
                pass
        else:
            self._gallery_preview.Text = self._t(
                "无可用 LUT", "No available LUTs"
            )
            self._gallery_info.Text = ""
        self._gallery_pump()

    def _populate_gallery_tree(self, entries):
        """Create one row per gallery entry with a 16:9 preview icon."""
        self._gallery_tree.Clear()
        self._gallery_highlight_item = None
        self._gallery_highlight_entry = None
        for entry in entries:
            item = self._gallery_tree.NewItem()
            try:
                item.Text[0] = self._gallery_item_text(entry)
            except Exception:
                try:
                    item.Text = self._gallery_item_text(entry)
                except Exception:
                    pass
            try:
                item.ToolTip[0] = entry["relative"]
            except Exception:
                pass
            if entry.get("preview"):
                try:
                    item.Icon[0] = self.ui.Icon({"File": entry["preview"]})
                except Exception:
                    try:
                        item.Icon = [
                            self.ui.Icon({"File": entry["preview"]})
                        ]
                    except Exception:
                        pass
            self._gallery_tree.AddTopLevelItem(item)

    def _gallery_item_text(self, entry, marked=False):
        prefix = "▶  " if marked else ""
        return "%s%s\n%s" % (
            prefix,
            entry["name"],
            self._lut_category_label(entry["category"]),
        )

    def _highlight_gallery_item(self, item, entry):
        previous_item = self._gallery_highlight_item
        previous_entry = self._gallery_highlight_entry
        if (
            previous_item is not None
            and previous_item is not item
            and previous_entry is not None
        ):
            try:
                previous_item.Text[0] = self._gallery_item_text(
                    previous_entry
                )
            except Exception:
                pass
        self._gallery_highlight_item = item
        self._gallery_highlight_entry = entry
        try:
            item.Text[0] = self._gallery_item_text(entry, marked=True)
        except Exception:
            pass
        self._show_gallery_entry(entry)

    def _update_gallery_page_label(self):
        if self._gallery_page_label is None:
            return
        total = len(self._gallery_filtered)
        page_count = max(
            1,
            (total + self._gallery_page_size - 1) // self._gallery_page_size,
        )
        self._gallery_page_label.Text = self._t(
            "第 %d / %d 页", "Page %d / %d"
        ) % (self._gallery_page + 1, page_count)
        try:
            self._gallery_prev.Enabled = self._gallery_page > 0
            self._gallery_next.Enabled = self._gallery_page + 1 < page_count
        except Exception:
            pass

    def _lut_category_label(self, category):
        if self.language == "en":
            return LUT_CATEGORY_EN.get(category, category)
        return category

    def _gallery_pump(self):
        self.pump()
        try:
            self._gallery_win.Update()
            self._gallery_win.Repaint()
        except Exception:
            pass

    def _show_gallery_entry(self, entry):
        self._gallery_selected = entry
        preview_path = entry.get("preview")
        self._gallery_preview.Text = (
            preview.preview_html(preview_path, 320)
            if preview_path
            else self._t(
                "该格式暂无缩略图", "No thumbnail for this format"
            )
        )
        self._gallery_info.Text = "%s\n%s\n%s" % (
            html.escape(entry.get("name", "")),
            html.escape(
                self._lut_category_label(entry.get("category", ""))
            ),
            html.escape(entry.get("relative", "")),
        )
        self._gallery_pump()

    def on_gallery_category(self, event):
        self._gallery_page = 0
        self._reload_gallery()

    def on_gallery_prev(self, event):
        if self._gallery_page <= 0:
            return
        self._gallery_page -= 1
        self._reload_gallery()

    def on_gallery_next(self, event):
        total = len(self._gallery_filtered)
        page_count = max(
            1,
            (total + self._gallery_page_size - 1) // self._gallery_page_size,
        )
        if self._gallery_page + 1 >= page_count:
            return
        self._gallery_page += 1
        self._reload_gallery()

    def _gallery_event_item(self, event):
        if self._gallery_tree is None:
            return None
        item = None
        if event is not None and hasattr(event, "ToolTip"):
            item = event
        if item is None:
            for key in ("item", "Item"):
                try:
                    candidate = event[key]
                except Exception:
                    continue
                if candidate is not None and hasattr(candidate, "ToolTip"):
                    item = candidate
                    break
        try:
            if item is None:
                selected = self._gallery_tree.SelectedItems()
                if isinstance(selected, dict):
                    item = next(iter(selected.values()), None)
                elif selected:
                    item = selected[0]
        except Exception:
            item = None
        return item

    def _gallery_entry_for_item(self, item):
        if item is None:
            return None
        try:
            entry = self._gallery_by_path.get(str(item.ToolTip[0]))
        except Exception:
            entry = None
        if entry is None:
            try:
                name = (
                    str(item.Text[0])
                    .split("\n")[0]
                    .replace("▶", "", 1)
                    .strip()
                )
                entry = self._gallery_by_name.get(name)
            except Exception:
                entry = None
        return entry

    def _select_gallery_event(self, event):
        item = self._gallery_event_item(event)
        entry = self._gallery_entry_for_item(item)
        if item is None or entry is None or self._gallery_selecting:
            return entry
        self._gallery_selecting = True
        try:
            # Resolve paints a selected Tree row's icon at a fixed 90x90,
            # ignoring IconSize. Clear the native selection immediately and
            # use the text marker for the active row instead.
            try:
                item.Selected = False
            except Exception:
                pass
            self._highlight_gallery_item(item, entry)
        finally:
            self._gallery_selecting = False
        return entry

    def on_gallery_tree_changed(self, event):
        self._select_gallery_event(event)

    def on_gallery_double_click(self, event):
        self._select_gallery_event(event)
        self.on_gallery_apply(event)

    def on_gallery_apply(self, event):
        entry = self._gallery_selected
        if not entry:
            self._gallery_status.Text = self._t(
                "请先选择一个 LUT", "Select a LUT first"
            )
            return
        try:
            self._apply_lut_path(entry["absolute"], entry["relative"])
            self._gallery_status.Text = self._t(
                "已套用：%s", "Applied: %s"
            ) % entry["name"]
            self._gallery_pump()
        except Exception as exc:
            self._gallery_status.Text = self._t(
                "套用失败：%s", "Apply failed: %s"
            ) % exc
            self._gallery_pump()

    def on_gallery_close(self, event):
        window = self._gallery_win
        if window is None:
            return
        # Resolve's UIManager Window.Close() returns False and leaves the
        # window visible. Hide() is the reliable user-facing close.
        try:
            window.Hide()
        except Exception:
            pass
        self._release_gallery_refs()
        try:
            window.Close()
        except Exception:
            pass

    def _release_gallery_refs(self):
        self._gallery_win = None
        self._gallery_tree = None
        self._gallery_category = None
        self._gallery_status = None
        self._gallery_preview = None
        self._gallery_info = None
        self._gallery_entries = []
        self._gallery_filtered = []
        self._gallery_page = 0
        self._gallery_page_label = None
        self._gallery_prev = None
        self._gallery_next = None
        self._gallery_by_name = {}
        self._gallery_by_path = {}
        self._gallery_selected = None

    # ------------------------------------------------------------- HTML blocks
    def _visual_html(self, path, title, lines, width=360):
        image = preview.preview_html(path, width)
        body = "<br>".join(html.escape(str(line)) for line in lines if line)
        return (
            '<table cellspacing="10"><tr>'
            '<td valign="top">%s</td>'
            '<td valign="top">'
            '<div style="font-size:14pt;font-weight:700;color:#f5f8fc;">%s</div>'
            '<div style="color:#c7d4e3;">%s</div>'
            "</td></tr></table>"
        ) % (image, html.escape(str(title)), body)

    def _match_html(self, reference, target, result):
        captions = (
            ("REFERENCE", "TARGET", "RESULT")
            if self.language == "en"
            else ("参考帧", "目标当前帧", "结果当前帧")
        )

        def cell(path, caption):
            return (
                '<td align="center" valign="top">'
                '<div style="color:#7d8b9d;">%s</div>%s</td>'
                % (caption, preview.preview_html(path, 250))
            )

        return (
            '<table cellspacing="8"><tr>%s%s%s</tr></table>'
            % (
                cell(reference, captions[0]),
                cell(target, captions[1]),
                cell(result, captions[2]),
            )
        )

    def _visual_label(self, widget_id, width=880, height=230):
        return self.ui.Label(
            {
                "ID": widget_id,
                "Text": "无预览",
                "Alignment": "AlignCenter",
                "MinimumSize": [width, height],
                "MaximumSize": [width, height],
                "StyleSheet": "background-color:#11151b;border:1px solid #2b333f;border-radius:8px;color:#6d7c8e;",
            }
        )

    def _title(self, text, subtitle="", widget_id=None):
        if widget_id in TITLES:
            zh_text, zh_sub, en_text, en_sub = TITLES[widget_id]
            text, subtitle = (
                (en_text, en_sub)
                if self.language == "en"
                else (zh_text, zh_sub)
            )
        props = {
            "Text": '<span style="color:#22d3ee;font-weight:700;">%s</span>'
            '<span style="color:#6d7c8e;">  %s</span>' % (text, subtitle),
            "MaximumSize": [880, 24],
        }
        if widget_id:
            props["ID"] = widget_id
        return self.ui.Label(props)

    def _t(self, zh, en):
        return en if self.language == "en" else zh

    def _status(self, widget_id, height=36):
        return self.ui.Label(
            {
                "ID": widget_id,
                "Text": "",
                "WordWrap": True,
                "StyleSheet": "color:#8b98a8;",
                "MaximumSize": [880, height],
            }
        )

    # ------------------------------------------------------------------ window
    def _build_window(self):
        self.title_font = self.ui.Font(
            {"Family": "Segoe UI", "PointSize": 18, "Bold": True}
        )
        self.body_font = self.ui.Font({"Family": "Segoe UI", "PointSize": 9})
        self.small_font = self.ui.Font({"Family": "Segoe UI", "PointSize": 8})
        self.mono_font = self.ui.Font({"Family": "Consolas", "PixelSize": 10})

        header = self.ui.HGroup(
            {"Spacing": 9, "MaximumSize": [1040, 30]},
            [
                self.ui.Label({"Text": "DaVinci", "StyleSheet": "color:#8b98a8;font-size:9pt;"}),
                self.ui.Label({"Text": "ColorFlow", "StyleSheet": "color:#f5f8fc;font-size:17pt;font-weight:700;"}),
                self.ui.Label({"Text": "调色助手", "StyleSheet": "color:#7d8b9d;font-size:10pt;"}),
                self.ui.Label({
                    "Text": "v%s" % VERSION,
                    "StyleSheet": "color:#6d7c8e;font-size:8pt;",
                    "MaximumSize": [56, 20],
                    "ToolTip": "ColorFlow v%s · %s" % (VERSION, BUILD_DATE),
                }),
                self.ui.HGap(0, 2),
                self.ui.Label({"Text": "本地处理 · 不上传素材", "StyleSheet": "color:#22d3ee;font-size:9pt;"}),
                self.ui.ComboBox({
                    "ID": "lang_combo",
                    "ItemText": ["中文", "English"],
                    "CurrentIndex": 0,
                    "MinimumSize": [92, 26],
                    "MaximumSize": [104, 26],
                }),
            ],
        )
        context_row = self.ui.HGroup(
            {"Spacing": 14, "MaximumSize": [1040, 24]},
            [
                self.ui.Label({"ID": "ctx_project", "Text": "项目：—", "MaximumSize": [250, 24]}),
                self.ui.Label({"ID": "ctx_timeline", "Text": "时间线：—", "MaximumSize": [230, 24]}),
                self.ui.Label({"ID": "ctx_clip", "Text": "当前镜头：—", "MaximumSize": [250, 24]}),
                self.ui.Label({"ID": "ctx_space", "Text": "色彩空间：—", "MaximumSize": [250, 24]}),
            ],
        )

        sidebar = self.ui.VGroup(
            {
                "Spacing": 6,
                "MinimumSize": [96, 0],
                "MaximumSize": [96, 800],
                "StyleSheet": "background-color:#0e1116;border:1px solid #1d242d;border-radius:10px;",
            },
            [
                self.ui.Label(
                    {
                        "Text": "CF",
                        "StyleSheet": "color:#22d3ee;font-size:13pt;font-weight:700;",
                        "Alignment": "AlignCenter",
                        "MaximumSize": [82, 24],
                    }
                ),
                self.ui.VGap(6),
                self.ui.Button({"ID": "side_0", "Text": "分析", "FixedSize": [82, 40], "StyleSheet": SIDE_ACTIVE}),
                self.ui.Button({"ID": "side_1", "Text": "归一", "FixedSize": [82, 40], "StyleSheet": SIDE_IDLE}),
                self.ui.Button({"ID": "side_2", "Text": "匹配", "FixedSize": [82, 40], "StyleSheet": SIDE_IDLE}),
                self.ui.Button({"ID": "side_3", "Text": "批量", "FixedSize": [82, 40], "StyleSheet": SIDE_IDLE}),
                self.ui.VGap(0, 1),
                self.ui.Label(
                    {
                        "Text": "v3",
                        "StyleSheet": "color:#4b5a6c;font-size:9pt;",
                        "Alignment": "AlignCenter",
                        "MaximumSize": [82, 20],
                    }
                ),
            ],
        )

        tabs = self.ui.HGroup(
            {"Spacing": 8, "MaximumSize": [900, 38]},
            [
                self.ui.Button({"ID": "tab_0", "Text": "素材分析", "Checkable": True, "Checked": True, "MinimumSize": [0, 38], "StyleSheet": TAB_ACTIVE}),
                self.ui.Button({"ID": "tab_1", "Text": "技术归一", "Checkable": True, "MinimumSize": [0, 38], "StyleSheet": TAB_IDLE}),
                self.ui.Button({"ID": "tab_2", "Text": "参考匹配", "Checkable": True, "MinimumSize": [0, 38], "StyleSheet": TAB_IDLE}),
                self.ui.Button({"ID": "tab_3", "Text": "批量报告", "Checkable": True, "MinimumSize": [0, 38], "StyleSheet": TAB_IDLE}),
            ],
        )

        self.pages = [
            self._build_analysis_page(),
            self._build_normalize_page(),
            self._build_match_page(),
            self._build_batch_page(),
        ]
        self.page_host = self.ui.VGroup({"Spacing": 0, "Weight": 1}, [*self.pages])
        content = self.ui.VGroup(
            {"Spacing": 8, "Weight": 1},
            [tabs, self.page_host],
        )
        body = self.ui.HGroup({"Spacing": 0, "Weight": 1}, [content])

        log_card = self.ui.VGroup(
            {"Spacing": 2, "MaximumSize": [1040, 92]},
            [
                self.ui.Label({"Text": "运行日志", "StyleSheet": "color:#7d8b9d;", "MaximumSize": [880, 18]}),
                self.ui.TextEdit(
                    {
                        "ID": "log",
                        "ReadOnly": True,
                        "Font": self.mono_font,
                        "TextColor": "#b9c6d6",
                        "TextBackgroundColor": "#0d1015",
                        "MinimumSize": [0, 62],
                        "MaximumSize": [900, 84],
                    }
                ),
            ],
        )
        footer = self.ui.HGroup(
            {"Spacing": 8, "MaximumSize": [1040, 30]},
            [
                self.ui.Label(
                    {
                        "Text": "写入前默认创建调色版本；节点树通过 DRX 模板套用。",
                        "WordWrap": True,
                        "StyleSheet": "color:#7f8a99;",
                        "MaximumSize": [880, 26],
                        "Weight": 1,
                    }
                ),
                self.ui.Button({"ID": "btn_close", "Text": "关闭面板", "MinimumSize": [90, 28]}),
            ],
        )

        window = self.dispatcher.AddWindow(
            {
                "ID": self.window_id,
                "Geometry": [110, 30, 1000, 900],
                "WindowTitle": "ColorFlow · 达芬奇调色助手",
                "StyleSheet": STYLE,
            },
            self.ui.VGroup(
                {"Spacing": 6, "Weight": 1},
                [header, context_row, body, log_card, footer],
            ),
        )
        window.On[self.window_id].Close = self.on_close
        return window

    # ------------------------------------------------------------------- pages
    def _build_analysis_page(self):
        return self.ui.VGroup(
            {"Spacing": 6},
            [
                self._title("素材与预览", "元数据 · Log · 裁切风险", "title_analysis"),
                self._visual_label("analysis_visual", 880, 230),
                self._status("analysis_warning", 42),
                self._status("analysis_status", 30),
                self.ui.HGroup(
                    {"Spacing": 6, "MaximumSize": [880, 34]},
                    [
                        self.ui.Button({"ID": "btn_refresh_analysis", "Text": "刷新当前帧", "MinimumSize": [130, 32]}),
                        self.ui.Button({"ID": "btn_fix_warnings", "Text": "一键处理警告", "MinimumSize": [140, 32], "StyleSheet": TAB_ACTIVE, "ToolTip": "处理曝光/白平衡/高饱和/高光裁切风险；不改变分辨率和 Log 设置"}),
                        self.ui.Button({"ID": "btn_refresh_nodes_top", "Text": "刷新节点", "MinimumSize": [90, 32]}),
                        self.ui.Button({"ID": "btn_build", "Text": "按素材建线", "MinimumSize": [110, 32]}),
                        self.ui.Button({"ID": "btn_refresh_media", "Text": "刷新媒体池", "MinimumSize": [100, 32]}),
                        self.ui.CheckBox({"ID": "chk_recursive", "Text": "含子文件夹", "Checked": True}),
                        self.ui.CheckBox({"ID": "chk_start_tc", "Text": "01:00:00:00", "Checked": True}),
                    ],
                ),
                self.ui.Label({"ID": "source_info", "Text": "正在读取当前媒体池…", "WordWrap": True, "MaximumSize": [880, 34]}),
                self._status("build_status", 30),
            ],
        )

    def _build_normalize_page(self):
        return self.ui.VGroup(
            {"Spacing": 6},
            [
                self._title("技术归一", "黑白场 · 白平衡 · 曝光 · LUT", "title_normalize"),
                self._visual_label("normalize_visual", 880, 230),
                self.ui.HGroup(
                    {"Spacing": 6, "MaximumSize": [880, 34]},
                    [
                        self.ui.Button({"ID": "btn_make_tree", "Text": "套用节点模板", "MinimumSize": [120, 32]}),
                        self.ui.Button({"ID": "btn_make_template", "Text": "从当前节点链生成模板", "MinimumSize": [170, 32]}),
                        self.ui.Button({"ID": "btn_save_template_preserve", "Text": "保存当前链为模板", "MinimumSize": [150, 32]}),
                    ],
                ),
                self._status("tree_status", 34),
                self.ui.HGroup(
                    {"Spacing": 6, "MaximumSize": [880, 40]},
                    [
                        self.ui.Button({"ID": "btn_one_click_restore", "Text": "一键还原", "MinimumSize": [130, 36], "StyleSheet": TAB_ACTIVE, "ToolTip": "优先套用当前节点模板，并命名 01 降噪 / 02 曝光 / 03 色温 / 04 饱和 / 匹配；写入前建版本"}),
                        self.ui.Button({"ID": "btn_auto_bw", "Text": "自动黑白场", "MinimumSize": [110, 34]}),
                        self.ui.Button({"ID": "btn_auto_wb", "Text": "自动白平衡", "MinimumSize": [110, 34]}),
                        self.ui.Button({"ID": "btn_auto_exposure", "Text": "曝光拉伸", "MinimumSize": [90, 34]}),
                    ],
                ),
                self.ui.HGroup(
                    {"Spacing": 6, "MaximumSize": [880, 34]},
                    [
                        self.ui.Label({"Text": "还原范围", "StyleSheet": "color:#8b98a8;"}),
                        self.ui.ComboBox({"ID": "restore_scope", "ItemText": ["当前镜头"], "MinimumSize": [150, 32]}),
                        self.ui.Button({"ID": "btn_reset", "Text": "还原原始（清空）", "MinimumSize": [150, 32]}),
                    ],
                ),
                self.ui.Label({
                    "Text": "分节点顺序：01 降噪 → 02 曝光 → 03 色温 → 04 饱和 → 最后空白节点留给匹配",
                    "WordWrap": True,
                    "StyleSheet": "color:#7d8b9d;",
                    "MaximumSize": [880, 22],
                }),
                self.ui.HGroup(
                    {"Spacing": 6, "MaximumSize": [880, 42]},
                    [
                        self.ui.Label({"Text": "强度", "StyleSheet": "color:#8b98a8;"}),
                        self.ui.SpinBox({"ID": "primary_strength", "Value": 70, "Minimum": 0, "Maximum": 100, "SingleStep": 5, "Suffix": " %", "MinimumSize": [120, 36]}),
                        self.ui.Label({"Text": "节点", "StyleSheet": "color:#8b98a8;"}),
                        self.ui.ComboBox({"ID": "node_combo", "ItemText": ["读取中…"], "MinimumSize": [210, 30]}),
                        self.ui.CheckBox({"ID": "chk_auto_node", "Text": "按角色选节点", "Checked": True}),
                        self.ui.CheckBox({"ID": "chk_backup", "Text": "建版本", "Checked": True}),
                        self.ui.CheckBox({"ID": "chk_allow_nonempty", "Text": "允许非空", "Checked": False}),
                        self.ui.Button({"ID": "btn_undo", "Text": "撤销", "MinimumSize": [60, 30]}),
                    ],
                ),
                self.ui.HGroup(
                    {"Spacing": 6, "MaximumSize": [880, 32]},
                    [
                        self.ui.Label({"Text": "LUT", "StyleSheet": "color:#8b98a8;"}),
                        self.ui.ComboBox({"ID": "lut_category", "ItemText": ["全部"], "MinimumSize": [100, 30]}),
                        self.ui.ComboBox({"ID": "lut_combo", "ItemText": ["点击刷新"], "MinimumSize": [280, 30]}),
                        self.ui.Button({"ID": "btn_refresh_luts", "Text": "刷新", "MinimumSize": [55, 30]}),
                        self.ui.Button({"ID": "btn_browse_lut", "Text": "浏览", "MinimumSize": [55, 30]}),
                        self.ui.Button({"ID": "btn_lut_gallery", "Text": "LUT 图库", "MinimumSize": [80, 30]}),
                        self.ui.Button({"ID": "btn_apply_lut", "Text": "套用", "MinimumSize": [55, 30], "StyleSheet": TAB_ACTIVE}),
                        self.ui.Button({"ID": "btn_remove_lut", "Text": "移除", "MinimumSize": [55, 30]}),
                    ],
                ),
                self._status("primary_status", 34),
                self._status("lut_status", 30),
            ],
        )

    def _build_match_page(self):
        return self.ui.VGroup(
            {"Spacing": 6},
            [
                self._title("参考匹配", "参考 → 目标 → 结果", "title_match"),
                self._visual_label("match_visual", 880, 190),
                self.ui.HGroup(
                    {"Spacing": 6, "MaximumSize": [880, 34]},
                    [
                        self.ui.Button({"ID": "btn_reference", "Text": "拾取当前帧", "MinimumSize": [110, 32]}),
                        self.ui.Button({"ID": "btn_reference_gallery", "Text": "从画廊引用", "MinimumSize": [110, 32]}),
                        self.ui.Button({"ID": "btn_reference_file", "Text": "本地单帧", "MinimumSize": [95, 32]}),
                        self.ui.Label({"ID": "reference_info", "Text": "尚未设置参考", "WordWrap": True, "MaximumSize": [420, 34]}),
                    ],
                ),
                self.ui.HGroup(
                    {"Spacing": 6, "MaximumSize": [880, 42]},
                    [
                        self.ui.Label({"Text": "范围", "StyleSheet": "color:#8b98a8;"}),
                        self.ui.ComboBox({"ID": "match_scope", "ItemText": ["选中镜头"], "MinimumSize": [150, 30]}),
                        self.ui.Label({"Text": "强度", "StyleSheet": "color:#8b98a8;"}),
                        self.ui.SpinBox({"ID": "match_strength", "Value": 60, "Minimum": 0, "Maximum": 100, "SingleStep": 5, "Suffix": " %", "MinimumSize": [100, 36]}),
                        self.ui.Button({"ID": "btn_match", "Text": "匹配参考色调", "MinimumSize": [130, 32], "StyleSheet": TAB_ACTIVE}),
                        self.ui.Button({"ID": "btn_undo_match", "Text": "撤销本次匹配", "MinimumSize": [130, 32]}),
                    ],
                ),
                self._status("match_status", 34),
                self._title("肤色限定", "YCbCr 遮罩 · 背景降饱和", "title_skin"),
                self.ui.HGroup(
                    {"Spacing": 5, "MaximumSize": [880, 42]},
                    [
                        self.ui.Label({"Text": "色相", "StyleSheet": "color:#8b98a8;"}),
                        self.ui.SpinBox({"ID": "skin_hue", "Value": 0, "Minimum": -30, "Maximum": 30, "Suffix": "°", "MinimumSize": [100, 36]}),
                        self.ui.Label({"Text": "饱和", "StyleSheet": "color:#8b98a8;"}),
                        self.ui.SpinBox({"ID": "skin_sat", "Value": 0, "Minimum": -50, "Maximum": 50, "Suffix": " %", "MinimumSize": [100, 36]}),
                        self.ui.Label({"Text": "亮度", "StyleSheet": "color:#8b98a8;"}),
                        self.ui.SpinBox({"ID": "skin_light", "Value": 0, "Minimum": -50, "Maximum": 50, "Suffix": " %", "MinimumSize": [100, 36]}),
                        self.ui.CheckBox({"ID": "chk_bg_desat", "Text": "背景降饱和", "Checked": False}),
                        self.ui.Button({"ID": "btn_skin", "Text": "生成肤色限定", "MinimumSize": [150, 32], "StyleSheet": TAB_ACTIVE}),
                    ],
                ),
                self._status("skin_status", 32),
            ],
        )

    def _build_batch_page(self):
        return self.ui.VGroup(
            {"Spacing": 6},
            [
                self._title("预设与批量", "DRX · 批量套用 · QC 报告", "title_batch"),
                self._visual_label("batch_visual", 880, 230),
                self.ui.HGroup(
                    {"Spacing": 6, "MaximumSize": [880, 32]},
                    [
                        self.ui.LineEdit({"ID": "preset_name", "PlaceholderText": "预设名称", "MinimumSize": [180, 30]}),
                        self.ui.ComboBox({"ID": "preset_category", "ItemText": ["外景"], "MinimumSize": [110, 30]}),
                        self.ui.Button({"ID": "btn_save_preset", "Text": "保存 DRX", "MinimumSize": [100, 30]}),
                    ],
                ),
                self._status("preset_status", 32),
                self.ui.HGroup(
                    {"Spacing": 5, "MaximumSize": [880, 32]},
                    [
                        self.ui.ComboBox({"ID": "preset_filter", "ItemText": ["全部预设"], "MinimumSize": [100, 30]}),
                        self.ui.ComboBox({"ID": "preset_combo", "ItemText": ["暂无预设"], "MinimumSize": [230, 30]}),
                        self.ui.Button({"ID": "btn_presets_refresh", "Text": "刷新", "MinimumSize": [55, 30]}),
                        self.ui.Button({"ID": "btn_preset_fav", "Text": "收藏", "MinimumSize": [55, 30]}),
                        self.ui.Button({"ID": "btn_preset_delete", "Text": "删除", "MinimumSize": [55, 30]}),
                    ],
                ),
                self.ui.HGroup(
                    {"Spacing": 5, "MaximumSize": [880, 32]},
                    [
                        self.ui.ComboBox({"ID": "preset_scope", "ItemText": ["选中镜头"], "MinimumSize": [150, 30]}),
                        self.ui.Button({"ID": "btn_apply_preset", "Text": "应用到当前", "MinimumSize": [100, 30]}),
                        self.ui.Button({"ID": "btn_batch_preset", "Text": "批量应用", "MinimumSize": [100, 30], "StyleSheet": TAB_ACTIVE}),
                    ],
                ),
                self.ui.HGroup(
                    {"Spacing": 6, "MaximumSize": [880, 34]},
                    [
                        self.ui.Button({"ID": "btn_report", "Text": "校验时间线并输出报告", "MinimumSize": [190, 32]}),
                        self.ui.Label({"ID": "report_status", "Text": "尚未生成报告", "WordWrap": True, "MaximumSize": [650, 34]}),
                    ],
                ),
            ],
        )

    # ---------------------------------------------------------------- previews
    def _set_visual(self, widget_id, text):
        widget = self._find(widget_id)
        if widget is not None:
            widget.Text = text

    def _update_match_visual(self):
        reference = None
        if self.reference:
            reference = self.reference.get("preview")
        self._set_visual(
            "match_visual",
            self._match_html(
                reference,
                getattr(self, "target_preview", None),
                getattr(self, "result_preview", None),
            ),
        )

    def refresh_analysis(self):
        try:
            context = self._require_clip()
            try:
                self.resolve.OpenPage("color")
                time.sleep(0.25)
            except Exception:
                pass
            frame_path = preview.export_current_frame(
                context["project"], "current"
            )
            info = features.current_clip_info(context)
            path = frame_path
            self.target_preview = frame_path
            stats = info.get("stats") or {}
            en = self.language == "en"
            log_name = info["log"]["name"]
            if en and log_name == "未识别":
                log_name = "Not recognized"
            if en:
                lines = [
                    "%s  ·  %s  ·  %s"
                    % (info["resolution"], info["fps"], info["codec"]),
                    "Depth %s  ·  WB %s  ·  Log %s"
                    % (info["bit_depth"], info["white_balance"], log_name),
                    "Mid %.3f  ·  Contrast %.2f stops  ·  Sat %.2f"
                    % (
                        stats.get("p50", 0.0),
                        stats.get("contrast_stops", 0.0),
                        stats.get("saturation", 0.0),
                    ),
                ]
            else:
                lines = [
                    "%s  ·  %s  ·  %s"
                    % (info["resolution"], info["fps"], info["codec"]),
                    "位深 %s  ·  WB %s  ·  Log %s"
                    % (info["bit_depth"], info["white_balance"], log_name),
                    "中间调 %.3f  ·  对比 %.2f stops  ·  饱和 %.2f"
                    % (
                        stats.get("p50", 0.0),
                        stats.get("contrast_stops", 0.0),
                        stats.get("saturation", 0.0),
                    ),
                ]
            self._set_visual(
                "analysis_visual",
                self._visual_html(
                    path,
                    info["name"] + (" · Current Frame" if en else " · 当前帧"),
                    lines,
                ),
            )
            self._set_visual(
                "normalize_visual",
                self._visual_html(
                    path,
                    "Current Frame" if en else "当前帧",
                    [
                        "%s · %s · %s"
                        % (info["resolution"], info["fps"], log_name),
                        "Confirm target node and version backup before correction."
                        if en
                        else "自动校正前请确认目标节点与版本备份。",
                    ],
                ),
            )
            self._set_visual(
                "batch_visual",
                self._visual_html(
                    path,
                    info["name"] + (" · Current Frame" if en else " · 当前帧"),
                    [
                        "%s · %s · %s" % (info["resolution"], info["fps"], info["codec"]),
                        "Test on a shot before saving or batch applying."
                        if en
                        else "保存预设或批量应用前，建议先在测试镜头验证。",
                    ],
                ),
            )
            if info["warnings"]:
                self._set(
                    "analysis_warning",
                    "⚠ " + self._warning_text(info["warnings"]),
                    "#fbbf24",
                )
            else:
                self._set(
                    "analysis_warning",
                    "✓ No obvious clipping or mismatch"
                    if en
                    else "✓ 未发现明显裁切或素材不匹配",
                    "#6ee7b7",
                )
            self._set(
                "analysis_status",
                (
                    analysis.describe_stats_en(stats)
                    if en
                    else analysis.describe_stats(stats)
                )
                if stats
                else "",
                "#8b98a8",
            )
            self._update_match_visual()
        except Exception as exc:
            en = self.language == "en"
            placeholder = self._visual_html(
                None,
                "Preview unavailable" if en else "预览不可用",
                [
                    str(exc),
                    "Open a project/timeline and confirm the Color page."
                    if en
                    else "请打开项目/时间线，并确认 Color 页面可用。",
                ],
            )
            for widget_id in (
                "analysis_visual",
                "normalize_visual",
                "batch_visual",
            ):
                self._set_visual(widget_id, placeholder)
            self._set_visual("match_visual", self._match_html(None, None, None))
            self._set("analysis_warning", "⚠ %s" % exc, "#fbbf24")
            self._set("analysis_status", "", "#8b98a8")
            self._log("刷新素材/预览失败：%s" % exc)

    @_guarded
    def on_fix_warnings(self, event):
        try:
            context = self._require_clip()
            clip = context["clip"]
            project = context["project"]
            capture = rb.capture_item_thumbnail(
                context["timeline"], clip
            )
            stats = capture["stats"]
            model = analysis.combined_warning_model(
                stats, self._strength("primary_strength")
            )
            if not model.get("applied"):
                self._set(
                    "analysis_status",
                    self._t(
                        "没有可自动处理的曝光/色温/饱和警告；不匹配/Log 需手动确认。",
                        "No auto-fixable exposure/WB/saturation warnings; check mismatch/Log manually.",
                    ),
                    "#fbbf24",
                )
                self._log(
                    "一键处理警告：没有可自动处理项；分辨率/帧率不匹配、"
                    "Log 未识别需要手动处理。"
                )
                return

            node_index, blank_count = features.warning_fix_node_index(clip)
            backup, version = self._backup(clip, "警告处理前")
            space_key, _ = self._space(context)
            try:
                features.apply_model(
                    project,
                    clip,
                    node_index,
                    model,
                    space_key,
                    "warning-fix",
                )
            except Exception:
                self._restore_on_failure(clip, backup)
                raise

            remaining = max(0, blank_count - 1)
            self._set(
                "analysis_status",
                self._t(
                    "警告修复已写入 %02d 号空白节点；02–04 未改动；剩余空白 %d 个。",
                    "Warning fix written to blank node %02d; 02–04 untouched; %d blank node(s) left.",
                )
                % (node_index, remaining),
                "#6ee7b7",
            )
            self._log(
                "一键处理警告：%s｜%s｜写入 %02d 号空白节点｜02–04 未改动%s"
                % (
                    clip.GetName(),
                    analysis.describe_model(model),
                    node_index,
                    "｜最后一个空白节点已占用，匹配需另加节点"
                    if remaining <= 0
                    else "｜最后一个空白节点保留给匹配",
                )
            )
            if (
                stats.get("p99", 0) >= 0.90
                or stats.get("clipped_high_ratio", 0) >= 0.02
            ):
                self._log(
                    "注意：已经裁切的高光细节无法恢复；本次只降低后续继续裁切的风险。"
                )
            self._save(context)
            self.refresh_nodes()
        except Exception as exc:
            self._set(
                "analysis_status",
                self._t("一键处理警告失败：%s", "Fix warnings failed: %s") % exc,
                "#f87171",
            )
            self._log("一键处理警告失败：%s" % exc)

    @_guarded
    def on_reference(self, event):
        super().on_reference(event)
        try:
            if self.reference is None:
                return
            context = self._require_clip()
            path = preview.export_current_frame(
                context["project"], "reference"
            )
            self.reference["preview"] = path
            if self.language == "en":
                self._set(
                    "reference_info",
                    "Reference: %s (locked)" % self.reference.get("name", ""),
                    "#6ee7b7",
                )
            self._update_match_visual()
        except Exception:
            pass

    def _set_match_reference(self, reference):
        self.reference = reference
        self._set(
            "reference_info",
            self._t(
                "参考：%s（已锁定）", "Reference: %s (locked)"
            )
            % reference.get("name", ""),
            "#6ee7b7",
        )
        self._update_match_visual()
        self._log(
            "参考已锁定：%s｜%s"
            % (
                reference.get("name", ""),
                analysis.describe_stats(reference["stats"]),
            )
        )

    @_guarded
    def on_reference_gallery(self, event):
        try:
            context = self._require_clip()
            entries = features.list_gallery_stills(context["project"])
            if not entries:
                raise rb.ColorFlowError(
                    "画廊里没有静帧。请先在 Color 页面抓取静帧，"
                    "或使用“本地单帧”。"
                )
            if len(entries) == 1:
                self._use_gallery_reference(entries[0])
                return
            self._open_reference_picker(entries)
        except Exception as exc:
            self._set(
                "reference_info",
                self._t("读取画廊失败：%s", "Gallery read failed: %s") % exc,
                "#f87171",
            )
            self._log("读取画廊失败：%s" % exc)

    @_guarded
    def on_reference_file(self, event):
        try:
            path = self.fusion.RequestFile()
            if not path:
                return
            self._set(
                "reference_info",
                self._t("正在载入本地参考…", "Loading local reference…"),
                "#fbbf24",
            )
            self.pump()
            context = self._require_clip()
            reference = features.reference_from_local_file(
                context["project"], str(path)
            )
            self._set_match_reference(reference)
        except Exception as exc:
            self._set(
                "reference_info",
                self._t("载入本地参考失败：%s", "Local reference failed: %s")
                % exc,
                "#f87171",
            )
            self._log("载入本地参考失败：%s" % exc)

    def _use_gallery_reference(self, entry):
        try:
            self._set(
                "reference_info",
                self._t("正在读取画廊静帧…", "Loading gallery still…"),
                "#fbbf24",
            )
            self.pump()
            context = self._require_clip()
            reference = features.reference_from_gallery_still(
                context["project"], entry
            )
            self._set_match_reference(reference)
        except Exception as exc:
            self._set(
                "reference_info",
                self._t("载入画廊静帧失败：%s", "Gallery still failed: %s")
                % exc,
                "#f87171",
            )
            self._log("载入画廊静帧失败：%s" % exc)

    def _open_reference_picker(self, entries):
        if self._ref_picker_win is not None:
            self._ref_picker_win.Show()
            self._ref_picker_win.Raise()
            return
        picker_id = self.window_id + ".refpick"
        self._ref_picker_entries = entries
        self._ref_picker_combo = self.ui.ComboBox(
            {
                "ID": "gallery_ref_pick",
                "ItemText": [entry["label"] for entry in entries],
                "CurrentIndex": 0,
                "MinimumSize": [540, 32],
            }
        )
        use_button = self.ui.Button(
            {
                "ID": "btn_gallery_ref_use",
                "Text": self._t("使用所选静帧", "Use Selected Still"),
                "MinimumSize": [130, 32],
                "StyleSheet": TAB_ACTIVE,
            }
        )
        cancel_button = self.ui.Button(
            {
                "ID": "btn_gallery_ref_cancel",
                "Text": self._t("取消", "Cancel"),
                "MinimumSize": [80, 32],
            }
        )
        root = self.ui.VGroup(
            {"Spacing": 10},
            [
                self.ui.Label(
                    {
                        "Text": self._t(
                            "选择画廊静帧", "Select Gallery Still"
                        ),
                        "StyleSheet": "color:#22d3ee;font-size:13pt;font-weight:700;",
                    }
                ),
                self._ref_picker_combo,
                self.ui.HGroup(
                    {"Spacing": 8},
                    [
                        use_button,
                        cancel_button,
                        self.ui.HGap(0, 1),
                    ],
                ),
            ],
        )
        picker = self.dispatcher.AddWindow(
            {
                "ID": picker_id,
                "Geometry": [420, 260, 600, 180],
                "WindowTitle": self._t("ColorFlow · 选择静帧", "ColorFlow · Select Still"),
                "StyleSheet": STYLE,
            },
            root,
        )
        self._ref_picker_win = picker
        picker.On[picker_id].Close = self.on_reference_picker_close
        picker.On["btn_gallery_ref_use"].Clicked = self.on_reference_picker_use
        picker.On["btn_gallery_ref_cancel"].Clicked = self.on_reference_picker_close
        picker.Show()
        picker.Raise()

    def on_reference_picker_use(self, event):
        try:
            index = int(self._ref_picker_combo.CurrentIndex)
            entry = self._ref_picker_entries[index]
        except Exception:
            entry = None
        if self._ref_picker_win is not None:
            try:
                self._ref_picker_win.Hide()
            except Exception:
                pass
            self._ref_picker_win = None
        if entry is not None:
            self._use_gallery_reference(entry)

    def on_reference_picker_close(self, event):
        if self._ref_picker_win is not None:
            try:
                self._ref_picker_win.Hide()
            except Exception:
                pass
            self._ref_picker_win = None

    @_guarded
    def on_match(self, event):
        self.last_backups = []
        super().on_match(event)
        if self.language == "en":
            current = ""
            try:
                current = self._find("match_status").Text or ""
            except Exception:
                pass
            if "失败" in current:
                self._set(
                    "match_status",
                    "Match finished with some failures; see the log.",
                    "#f87171",
                )
            else:
                self._set(
                    "match_status",
                    "Match complete. Check the preview; use Undo Match if needed.",
                    "#6ee7b7",
                )
        try:
            context = self._context()
            if self.last_backups and context["timeline"] is not None:
                features.save_batch_manifest(
                    "match", context["timeline"], self.last_backups
                )
                self._log(
                    "匹配回退记录已保存：%s" % features.LAST_BATCH_PATH
                )
        except Exception:
            pass
        try:
            context = self._require_clip()
            self.result_preview = preview.export_current_frame(
                context["project"], "result"
            )
            self._update_match_visual()
        except Exception:
            pass

    @_guarded
    def on_undo_match(self, event):
        try:
            context = self._require_clip()
            timeline = context["timeline"]
            data = features.load_batch_manifest()
            if not data and self.last_backups:
                data = features.save_batch_manifest(
                    "match", timeline, self.last_backups
                )
            if not data:
                raise rb.ColorFlowError("没有可回退的批量匹配记录。")
            if (
                data.get("timeline_id")
                and data["timeline_id"] != timeline.GetUniqueId()
            ):
                raise rb.ColorFlowError(
                    "上次匹配记录属于时间线“%s”，请先切回该时间线。"
                    % data.get("timeline_name", "")
                )
            restored, failed = features.restore_batch_manifest(timeline, data)
            if not failed:
                features.clear_batch_manifest()
            self.last_backups = []
            self._save(context)
            if failed:
                self._set(
                    "match_status",
                    self._t(
                        "已回退 %d 个，失败 %d 个（%s）",
                        "Restored %d, failed %d (%s)",
                    )
                    % (len(restored), len(failed), failed[0][1]),
                    "#f87171",
                )
            else:
                self._set(
                    "match_status",
                    self._t(
                        "已回退上次匹配：%d 个镜头恢复写入前版本。",
                        "Match undone: %d clip(s) restored to the previous version.",
                    )
                    % len(restored),
                    "#6ee7b7",
                )
            self._log(
                "撤销本次匹配：恢复 %d 个，失败 %d 个"
                % (len(restored), len(failed))
            )
            self.refresh_nodes()
        except Exception as exc:
            self._set(
                "match_status",
                self._t("撤销匹配失败：%s", "Undo match failed: %s") % exc,
                "#f87171",
            )
            self._log("撤销匹配失败：%s" % exc)

    def switch_tab(self, index):
        super().switch_tab(index)
        if int(index) == 2:
            self._update_match_visual()

    def _single_node_restore_impl(self, event=None):
        try:
            context = self._require_clip()
            capture = rb.capture_item_thumbnail(
                context["timeline"], context["clip"]
            )
            model = analysis.restore_model(
                capture["stats"],
                self._strength("primary_strength"),
                True,
            )
            result = self._write_model(
                context,
                context["clip"],
                model,
                "单节点还原-%s" % context["clip"].GetName(),
                "primary",
            )
            self._log(
                "单节点兼容还原：%s｜节点 %02d｜%s"
                % (
                    context["clip"].GetName(),
                    result["node"]["index"],
                    analysis.describe_model(model),
                )
            )
            self._save(context)
            self.refresh_nodes()
            self._set(
                "primary_status",
                self._t(
                    "节点不足，已使用单节点兼容还原，写入 %02d 号节点：%s",
                    "Not enough nodes; single-node fallback written to node %02d: %s",
                )
                % (result["node"]["index"], analysis.describe_model(model)),
                "#6ee7b7",
            )
        except Exception as exc:
            self._set(
                "primary_status",
                self._t(
                    "单节点兼容还原失败：%s",
                    "Single-node fallback failed: %s",
                )
                % exc,
                "#f87171",
            )
            self._log("单节点兼容还原失败：%s" % exc)

    @_guarded
    def on_split_restore(self, event):
        try:
            context = self._require_clip()
            clip = context["clip"]
            project = context["project"]
            nodes = self._nodes(clip)
            backup = None
            version = None
            template = features.find_template()
            template_used = None
            use_template = bool(template)
            if use_template:
                backup, version = self._backup(clip, "分节点还原前")
                try:
                    features.apply_template(
                        project, clip, template, label_nodes=True
                    )
                    template_used = os.path.basename(template)
                except Exception:
                    self._restore_on_failure(clip, backup)
                    raise
                nodes = self._nodes(clip)
                if len(nodes) < 5:
                    self._restore_on_failure(clip, backup)
                    self._log(
                        "模板 %s 节点数仍少于 5，回退单节点兼容还原。"
                        % os.path.basename(template)
                    )
                    return self._single_node_restore_impl(event)
                self._log("已套用节点模板：%s（%d 节点）" % (template_used, len(nodes)))
            elif len(nodes) < 5:
                self._log("未找到可用节点模板，使用单节点兼容还原。")
                return self._single_node_restore_impl(event)
            else:
                backup, version = self._backup(clip, "分节点还原前")

            capture = rb.capture_item_thumbnail(
                context["timeline"], clip
            )
            stats = capture["stats"]
            strength = self._strength("primary_strength")
            space_key, _ = self._space(context)
            writes = [
                (2, analysis.exposure_model(stats, strength), "02-exposure"),
                (3, analysis.white_balance_model(stats, strength), "03-temperature"),
                (
                    4,
                    analysis.saturation_model(stats, strength, True),
                    "04-saturation",
                ),
            ]
            try:
                for node_index, model, label in writes:
                    features.apply_model(
                        project, clip, node_index, model, space_key, label
                    )
            except Exception:
                self._restore_on_failure(clip, backup)
                raise

            self._log(
                "一键还原（分节点）：%s｜模板 %s｜02曝光 %+.2fEV｜03色温 R/G %+.3f B/G %+.3f｜"
                "04饱和 %.3f / 对比 %.3f｜最后空白节点保留给匹配"
                % (
                    clip.GetName(),
                    template_used or "沿用当前节点链",
                    writes[0][1]["exposure_stops"],
                    writes[1][1]["wb_rg"],
                    writes[1][1]["wb_bg"],
                    writes[2][1]["saturation"],
                    writes[2][1]["contrast"],
                )
            )
            self._save(context)
            self.refresh_nodes()
            template_note = (
                self._t(
                    "模板 %s，" % template_used,
                    " with template %s, " % template_used,
                )
                if template_used
                else ""
            )
            self._set(
                "primary_status",
                self._t(
                    "一键还原（分节点）完成：%s02 曝光 / 03 色温 / 04 饱和；"
                    "01 降噪和最后空白节点未写入。",
                    "Split restore complete%s: 02 Exposure / 03 Temperature / "
                    "04 Saturation; 01 Denoise and last blank untouched.",
                )
                % template_note,
                "#6ee7b7",
            )
        except Exception as exc:
            self._set(
                "primary_status",
                self._t(
                    "一键还原（分节点）失败：%s",
                    "Split restore failed: %s",
                )
                % exc,
                "#f87171",
            )
            self._log("一键还原（分节点）失败：%s" % exc)

    @_guarded
    def on_save_template_preserve(self, event):
        try:
            context = self._require_clip()
            try:
                self.resolve.OpenPage("color")
                time.sleep(0.4)
            except Exception:
                pass
            path = features.save_template_preserve(
                context["project"], context["timeline"], "ColorFlow_5node"
            )
            self._set(
                "tree_status",
                self._t(
                    "模板已保存（保留当前工具/调色）：%s",
                    "Template saved (current tools/grades preserved): %s",
                )
                % path,
                "#6ee7b7",
            )
            self._log(
                "保存节点模板（保留工具）：%s；请确保 02-04 为空白校正节点、"
                "01 保留降噪、最后节点留空给匹配。" % path
            )
        except Exception as exc:
            self._set(
                "tree_status",
                self._t(
                    "保存节点模板失败：%s",
                    "Save template failed: %s",
                )
                % exc,
                "#f87171",
            )
            self._log("保存节点模板失败：%s" % exc)

    @_guarded
    def on_report(self, event):
        try:
            context = self._require_clip()

            def progress(index, total, name):
                if self._cancel_requested:
                    raise rb.ColorFlowError("操作已取消")
                self._set(
                    "report_status",
                    "正在分析 %d/%d：%s" % (index + 1, total, name),
                    "#fbbf24",
                )
                self.pump()

            path, rows = features.report_timeline(
                context["project"], context["timeline"], progress
            )
            warnings = sum(1 for row in rows if row["info"].get("warnings"))
            self._set(
                "report_status",
                "报告已生成：%s（%d 个镜头，%d 个警告）"
                % (path, len(rows), warnings),
                "#fbbf24" if warnings else "#6ee7b7",
            )
            self._log("调色报告：%s" % path)
        except Exception as exc:
            self._set("report_status", "生成报告失败：%s" % exc, "#f87171")
            self._log("生成报告失败：%s" % exc)

    # Long or write-heavy actions inherited from v2 get a busy guard so a
    # second click cannot start a nested operation while the first is running.
    on_refresh_analysis = _guarded(V2App.on_refresh_analysis)
    on_build = _guarded(V2App.on_build)
    on_make_tree = _guarded(V2App.on_make_tree)
    on_make_template = _guarded(V2App.on_make_template)
    on_auto_bw = _guarded(V2App.on_auto_bw)
    on_auto_wb = _guarded(V2App.on_auto_wb)
    on_auto_exposure = _guarded(V2App.on_auto_exposure)
    on_reset = _guarded(V2App.on_reset)
    on_skin = _guarded(V2App.on_skin)
    on_apply_lut = _guarded(V2App.on_apply_lut)
    on_remove_lut = _guarded(V2App.on_remove_lut)
    on_save_preset = _guarded(V2App.on_save_preset)
    on_apply_preset = _guarded(V2App.on_apply_preset)
    on_batch_preset = _guarded(V2App.on_batch_preset)


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

