"""ColorFlow v2 — four-page Resolve UIManager panel."""

import html
import os
import time
import traceback
import uuid
from datetime import datetime

from . import analysis
from . import features
from . import resolve_bridge as rb
from .version import VERSION


WIN_ID_PREFIX = "com.colorflow.resolve.panel.v2"

STYLE = """
QWidget {
    background-color: #0b0d10;
    color: #e7edf5;
    font-family: 'Segoe UI';
    font-size: 10pt;
}
QLabel { background: transparent; }
QPushButton {
    background-color: #1a1f27;
    border: 1px solid #2b333f;
    border-radius: 8px;
    color: #dce5ef;
    padding: 8px 14px;
}
QPushButton:hover { background-color: #232b36; }
QPushButton:pressed { background-color: #151a20; }
QPushButton:checked {
    background-color: #22d3ee;
    border-color: #22d3ee;
    color: #041014;
    font-weight: 700;
}
QComboBox, QLineEdit, QSpinBox {
    background-color: #11151b;
    border: 1px solid #2b333f;
    border-radius: 7px;
    padding: 7px 9px;
    color: #e7edf5;
}
QSpinBox { padding: 2px 4px; }
QSpinBox::up-button, QSpinBox::down-button { width: 14px; }
QComboBox::drop-down { border: 0; }
QTextEdit {
    background-color: #0d1015;
    border: 1px solid #232a33;
    border-radius: 7px;
    color: #b9c6d6;
}
QScrollBar:vertical { background: #0b0d10; width: 10px; }
QScrollBar::handle:vertical { background: #2b333f; border-radius: 5px; }
"""

CARD_STYLE = (
    "background-color:#14181e;"
    "border:1px solid #232b35;"
    "border-radius:12px;"
)
CHIP_STYLE = (
    "background-color:#1b222b;"
    "border:1px solid #2b3542;"
    "border-radius:6px;"
    "padding:5px 9px;"
    "color:#c7d4e3;"
)
CYAN_STYLE = (
    "background-color:#22d3ee;"
    "border:1px solid #22d3ee;"
    "border-radius:9px;"
    "color:#041014;"
    "font-weight:700;"
    "padding:9px 16px;"
)
SIDE_ACTIVE = (
    "background-color:#22d3ee;"
    "border:1px solid #22d3ee;"
    "border-radius:9px;"
    "color:#041014;"
    "font-weight:700;"
)
SIDE_IDLE = (
    "background-color:#0e1116;"
    "border:1px solid #1d242d;"
    "border-radius:9px;"
    "color:#6d7c8e;"
)
TAB_ACTIVE = (
    "background-color:#22d3ee;"
    "border:1px solid #22d3ee;"
    "border-radius:8px;"
    "color:#041014;"
    "font-weight:700;"
    "padding:9px 16px;"
)
TAB_IDLE = (
    "background-color:#1a1f27;"
    "border:1px solid #2b333f;"
    "border-radius:8px;"
    "color:#dce5ef;"
    "padding:9px 16px;"
)


def _chip(text):
    return {
        "Text": text,
        "StyleSheet": CHIP_STYLE,
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
        self.pages = []
        self.tab_buttons = []
        self.side_buttons = []
        self.active_tab = 0
        self.reference = None
        self.last_backups = []
        self.lut_entries = []
        self.preset_entries = []
        self.last_report = ""
        self._closing = False
        self._cancel_requested = False

    # ------------------------------------------------------------------ UI
    def _build_window(self):
        self.title_font = self.ui.Font(
            {"Family": "Segoe UI", "PointSize": 18, "Bold": True}
        )
        self.body_font = self.ui.Font({"Family": "Segoe UI", "PointSize": 9})
        self.small_font = self.ui.Font({"Family": "Segoe UI", "PointSize": 8})
        self.mono_font = self.ui.Font({"Family": "Consolas", "PixelSize": 10})

        header = self.ui.HGroup(
            {"Spacing": 9, "Weight": 0},
            [
                self.ui.Label(
                    {
                        "Text": "◈",
                        "StyleSheet": "color:#22d3ee;font-size:15pt;",
                    }
                ),
                self.ui.Label(
                    {
                        "Text": "DaVinci",
                        "StyleSheet": "color:#8b98a8;font-size:9pt;",
                    }
                ),
                self.ui.Label(
                    {
                        "Text": "ColorFlow",
                        "StyleSheet": "color:#f5f8fc;font-size:17pt;font-weight:700;",
                    }
                ),
                self.ui.Label(
                    {
                        "Text": "调色助手",
                        "StyleSheet": "color:#7d8b9d;font-size:10pt;",
                    }
                ),
                self.ui.HGap(0, 2),
                self.ui.Label(
                    {
                        "Text": "本地处理 · 不上传素材",
                        "StyleSheet": "color:#22d3ee;font-size:9pt;",
                    }
                ),
            ],
        )

        context_row = self.ui.HGroup(
            {"Spacing": 14, "Weight": 0},
            [
                self.ui.Label({"ID": "ctx_project", "Text": "项目：—", "Font": self.body_font, "MaximumSize": [230, 24]}),
                self.ui.Label({"ID": "ctx_timeline", "Text": "时间线：—", "Font": self.body_font, "MaximumSize": [230, 24]}),
                self.ui.Label({"ID": "ctx_clip", "Text": "当前镜头：—", "Font": self.body_font, "MaximumSize": [230, 24]}),
                self.ui.Label({"ID": "ctx_space", "Text": "色彩空间：—", "Font": self.body_font, "MaximumSize": [230, 24]}),
            ],
        )

        sidebar = self.ui.VGroup(
            {
                "Spacing": 7,
                "MinimumSize": [58, 0],
                "MaximumSize": [58, 820],
                "StyleSheet": "background-color:#0e1116;border:1px solid #1d242d;border-radius:12px;padding:12px 7px;",
            },
            [
                self.ui.Label(
                    {
                        "Text": "CF",
                        "StyleSheet": "color:#22d3ee;font-size:13pt;font-weight:700;",
                        "Alignment": "AlignCenter",
                        "MaximumSize": [42, 24],
                    }
                ),
                self.ui.VGap(10),
                self.ui.Button(
                    {"ID": "side_0", "Text": "◈", "FixedSize": [42, 42], "MaximumSize": [42, 42], "StyleSheet": SIDE_ACTIVE}
                ),
                self.ui.Button(
                    {"ID": "side_1", "Text": "◐", "FixedSize": [42, 42], "MaximumSize": [42, 42], "StyleSheet": SIDE_IDLE}
                ),
                self.ui.Button(
                    {"ID": "side_2", "Text": "◎", "FixedSize": [42, 42], "MaximumSize": [42, 42], "StyleSheet": SIDE_IDLE}
                ),
                self.ui.Button(
                    {"ID": "side_3", "Text": "▤", "FixedSize": [42, 42], "MaximumSize": [42, 42], "StyleSheet": SIDE_IDLE}
                ),
                self.ui.VGap(0, 1),
                self.ui.Label(
                    {
                        "Text": "v2",
                        "StyleSheet": "color:#4b5a6c;font-size:9pt;",
                        "Alignment": "AlignCenter",
                        "MaximumSize": [42, 20],
                    }
                ),
            ],
        )

        tabs = self.ui.HGroup(
            {"Spacing": 8, "Weight": 0},
            [
                self.ui.Button(
                    {
                        "ID": "tab_0",
                        "Text": "素材分析",
                        "Checkable": True,
                        "Checked": True,
                        "MinimumSize": [0, 42],
                        "StyleSheet": TAB_ACTIVE,
                    }
                ),
                self.ui.Button(
                    {
                        "ID": "tab_1",
                        "Text": "一级调色",
                        "Checkable": True,
                        "MinimumSize": [0, 42],
                        "StyleSheet": TAB_IDLE,
                    }
                ),
                self.ui.Button(
                    {
                        "ID": "tab_2",
                        "Text": "镜头匹配与肤色",
                        "Checkable": True,
                        "MinimumSize": [0, 42],
                        "StyleSheet": TAB_IDLE,
                    }
                ),
                self.ui.Button(
                    {
                        "ID": "tab_3",
                        "Text": "预设与批量",
                        "Checkable": True,
                        "MinimumSize": [0, 42],
                        "StyleSheet": TAB_IDLE,
                    }
                ),
            ],
        )

        self.pages = [
            self._build_analysis_page(),
            self._build_primary_page(),
            self._build_match_page(),
            self._build_preset_page(),
        ]
        # Keep all pages attached while handlers are registered, then detach
        # the inactive pages before Show() so they do not contribute layout
        # size to the window.
        self.page_host = self.ui.VGroup(
            {"Spacing": 0},
            [*self.pages],
        )

        content = self.ui.VGroup(
            {"Spacing": 10, "Weight": 1},
            [tabs, self.page_host],
        )
        body = self.ui.HGroup(
            {"Spacing": 12, "Weight": 1},
            [sidebar, content],
        )

        log_card = self.ui.VGroup(
            {"Spacing": 4, "Weight": 0},
            [
                self.ui.Label(
                    {
                        "Text": '<b>运行日志</b> <span style="color:#7f8a99;">每一步都可核对</span>',
                        "Font": self.body_font,
                    }
                ),
                self.ui.TextEdit(
                    {
                        "ID": "log",
                        "ReadOnly": True,
                        "Font": self.mono_font,
                        "TextColor": "#b9c6d6",
                        "TextBackgroundColor": "#0d1015",
                        "LineWrapMode": "WidgetWidth",
                        "MinimumSize": [0, 70],
                        "MaximumSize": [1000, 90],
                    }
                ),
            ],
        )

        footer = self.ui.HGroup(
            {"Spacing": 8, "Weight": 0},
            [
                self.ui.Label(
                    {
                        "Text": "公开脚本接口不能新建节点；节点树通过 DRX 模板套用。请先在 Color 页面准备可用节点。",
                        "WordWrap": True,
                        "StyleSheet": "color:#7f8a99;",
                        "Weight": 1,
                        "MaximumSize": [900, 30],
                    }
                ),
                self.ui.Button(
                    {"ID": "btn_close", "Text": "关闭面板", "MinimumSize": [90, 28]}
                ),
            ],
        )

        window = self.dispatcher.AddWindow(
            {
                "ID": self.window_id,
                "Geometry": [110, 30, 1000, 940],
                "WindowTitle": "ColorFlow · 达芬奇调色助手",
                "StyleSheet": STYLE,
            },
            self.ui.VGroup(
                {"Spacing": 8, "Weight": 1},
                [header, context_row, body, log_card, footer],
            ),
        )
        window.On[self.window_id].Close = self.on_close
        return window

    def _card(self, title, subtitle, children):
        return self.ui.VGroup(
            {"Spacing": 6},
            [
                self.ui.Label(
                    {
                        "Text": '<span style="font-size:13pt;font-weight:700;color:#f5f8fc;">%s</span>'
                        '<span style="color:#7d8b9d;">  %s</span>' % (title, subtitle),
                        "WordWrap": True,
                    }
                ),
                *children,
            ],
        )

    def _node_box(self, text, accent=False):
        if accent:
            style = (
                "background-color:#22d3ee;border:1px solid #22d3ee;"
                "border-radius:8px;color:#041014;font-weight:700;"
            )
        else:
            style = (
                "background-color:#1a2028;border:1px solid #2b3542;"
                "border-radius:8px;color:#dce5ef;font-weight:600;"
            )
        return self.ui.Label(
            {
                "Text": text,
                "Alignment": "AlignCenter",
                "MinimumSize": [92, 40],
                "StyleSheet": style,
            }
        )

    def _arrow(self):
        return self.ui.Label(
            {"Text": "›", "StyleSheet": "color:#5f7187;font-size:16pt;"}
        )

    def _build_analysis_page(self):
        info_grid = self.ui.VGroup(
            {"Spacing": 7},
            [
                self.ui.HGroup(
                    {"Spacing": 7},
                    [
                        self.ui.Label({"ID": "meta_resolution", "Text": "分辨率 —", "StyleSheet": CHIP_STYLE, "MaximumSize": [320, 30]}),
                        self.ui.Label({"ID": "meta_fps", "Text": "帧率 —", "StyleSheet": CHIP_STYLE, "MaximumSize": [320, 30]}),
                        self.ui.Label({"ID": "meta_codec", "Text": "编码 —", "StyleSheet": CHIP_STYLE, "MaximumSize": [320, 30]}),
                    ],
                ),
                self.ui.HGroup(
                    {"Spacing": 7},
                    [
                        self.ui.Label({"ID": "meta_depth", "Text": "位深 —", "StyleSheet": CHIP_STYLE, "MaximumSize": [320, 30]}),
                        self.ui.Label({"ID": "meta_wb", "Text": "白平衡 —", "StyleSheet": CHIP_STYLE, "MaximumSize": [320, 30]}),
                        self.ui.Label({"ID": "meta_log", "Text": "Log —", "StyleSheet": CHIP_STYLE, "MaximumSize": [320, 30]}),
                    ],
                ),
            ],
        )
        analysis_card = self._card(
            "当前素材",
            "读取媒体池与时间线元数据",
            [
                self.ui.Label(
                    {
                        "ID": "analysis_clip_name",
                        "Text": "未打开时间线",
                        "StyleSheet": "font-size:15pt;font-weight:700;color:#f5f8fc;",
                        "MaximumSize": [900, 30],
                    }
                ),
                info_grid,
                self.ui.Label(
                    {
                        "ID": "analysis_warning",
                        "Text": "⚠ 请先打开时间线并选中一个镜头。",
                        "WordWrap": True,
                        "StyleSheet": "color:#fbbf24;",
                        "MaximumSize": [900, 54],
                    }
                ),
                self.ui.HGroup(
                    {"Spacing": 8},
                    [
                        self.ui.Button(
                            {"ID": "btn_refresh_analysis", "Text": "刷新素材信息", "MinimumSize": [150, 34]}
                        ),
                        self.ui.Button(
                            {"ID": "btn_refresh_nodes_top", "Text": "刷新节点", "MinimumSize": [110, 34]}
                        ),
                    ],
                ),
                self.ui.HGroup(
                    {"Spacing": 8},
                    [
                        self.ui.Label({"Text": "还原范围", "StyleSheet": "color:#8b98a8;"}),
                        self.ui.ComboBox(
                            {
                                "ID": "restore_scope",
                                "ItemText": ["当前镜头", "选中镜头", "整条时间线"],
                                "CurrentIndex": 0,
                                "MinimumSize": [150, 32],
                            }
                        ),
                        self.ui.Button(
                            {"ID": "btn_reset", "Text": "备份并还原原始", "MinimumSize": [150, 32]}
                        ),
                    ],
                ),
                self.ui.Label(
                    {"ID": "analysis_status", "Text": "", "WordWrap": True, "StyleSheet": "color:#8b98a8;", "MaximumSize": [900, 40]}
                ),
            ],
        )
        build_card = self._card(
            "素材池与建线",
            "最大分辨率 + 最常见帧率",
            [
                self.ui.Label(
                    {"ID": "source_info", "Text": "正在读取当前媒体池…", "WordWrap": True, "MaximumSize": [900, 44]}
                ),
                self.ui.HGroup(
                    {"Spacing": 8},
                    [
                        self.ui.CheckBox({"ID": "chk_recursive", "Text": "含子文件夹", "Checked": True}),
                        self.ui.CheckBox({"ID": "chk_start_tc", "Text": "起始 01:00:00:00", "Checked": True}),
                    ],
                ),
                self.ui.HGroup(
                    {"Spacing": 8},
                    [
                        self.ui.Button(
                            {"ID": "btn_build", "Text": "按素材建线", "MinimumSize": [150, 36]}
                        ),
                        self.ui.Button(
                            {"ID": "btn_refresh_media", "Text": "刷新媒体池", "MinimumSize": [130, 36]}
                        ),
                    ],
                ),
                self.ui.Label(
                    {"ID": "build_status", "Text": "", "WordWrap": True, "StyleSheet": "color:#8b98a8;", "MaximumSize": [900, 40]}
                ),
            ],
        )
        return self.ui.VGroup(
            {"Spacing": 8},
            [analysis_card, build_card],
        )

    def _build_primary_page(self):
        tree_card = self._card(
            "一键生成标准调色节点树",
            "输入 → Log还原 → 一级校色 → 肤色Qualifier → 风格LUT",
            [
                self.ui.HGroup(
                    {"Spacing": 5},
                    [
                        self._node_box("输入"),
                        self._arrow(),
                        self._node_box("Log 还原"),
                        self._arrow(),
                        self._node_box("一级校色"),
                        self._arrow(),
                        self._node_box("肤色"),
                        self._arrow(),
                        self._node_box("风格 LUT", True),
                    ],
                ),
                self.ui.HGroup(
                    {"Spacing": 8},
                    [
                        self.ui.Button(
                            {"ID": "btn_make_tree", "Text": "套用节点模板", "MinimumSize": [150, 38]}
                        ),
                        self.ui.Button(
                            {
                                "ID": "btn_make_template",
                                "Text": "从当前节点链生成模板",
                                "MinimumSize": [190, 38],
                            }
                        ),
                    ],
                ),
                self.ui.Label(
                    {"ID": "tree_status", "Text": "", "WordWrap": True, "StyleSheet": "color:#8b98a8;", "MaximumSize": [900, 44]}
                ),
            ],
        )
        auto_card = self._card(
            "一级校正",
            "自动黑白场 / 白平衡 / 曝光拉伸",
            [
                self.ui.HGroup(
                    {"Spacing": 10},
                    [
                        self.ui.Button(
                            {
                                "ID": "btn_auto_bw",
                                "Text": "＋  自动黑白场",
                                "MinimumSize": [190, 44],
                                "StyleSheet": CYAN_STYLE,
                            }
                        ),
                        self.ui.Button(
                            {
                                "ID": "btn_auto_wb",
                                "Text": "＋  自动白平衡",
                                "MinimumSize": [190, 44],
                                "StyleSheet": CYAN_STYLE,
                            }
                        ),
                        self.ui.Button(
                            {"ID": "btn_auto_exposure", "Text": "自动曝光拉伸", "MinimumSize": [150, 44]}
                        ),
                    ],
                ),
                self.ui.HGroup(
                    {"Spacing": 8},
                    [
                        self.ui.Label({"Text": "强度", "StyleSheet": "color:#8b98a8;"}),
                        self.ui.SpinBox(
                            {
                                "ID": "primary_strength",
                                "Value": 70,
                                "Minimum": 0,
                                "Maximum": 100,
                                "SingleStep": 5,
                                "Suffix": " %",
                                "MinimumSize": [110, 32],
                            }
                        ),
                        self.ui.Label({"Text": "写入节点", "StyleSheet": "color:#8b98a8;"}),
                        self.ui.ComboBox(
                            {"ID": "node_combo", "ItemText": ["读取中…"], "MinimumSize": [240, 32]}
                        ),
                        self.ui.CheckBox(
                            {"ID": "chk_auto_node", "Text": "按角色自动选节点", "Checked": True}
                        ),
                        self.ui.CheckBox(
                            {"ID": "chk_backup", "Text": "写入前建版本", "Checked": True}
                        ),
                        self.ui.CheckBox(
                            {"ID": "chk_allow_nonempty", "Text": "允许写非空节点", "Checked": False}
                        ),
                        self.ui.Button(
                            {"ID": "btn_undo", "Text": "撤销上次写入", "MinimumSize": [120, 32]}
                        ),
                    ],
                ),
                self.ui.Label(
                    {"ID": "primary_status", "Text": "", "WordWrap": True, "StyleSheet": "color:#8b98a8;", "MaximumSize": [900, 40]}
                ),
            ],
        )
        lut_card = self._card(
            "LUT 库",
            "SLog3 / ARRI / HLG / 自定义收藏",
            [
                self.ui.HGroup(
                    {"Spacing": 8},
                    [
                        self.ui.ComboBox(
                            {
                                "ID": "lut_category",
                                "ItemText": ["全部", "SLog3", "ARRI", "HLG", "CLog", "Rec.709", "自定义"],
                                "MinimumSize": [110, 32],
                            }
                        ),
                        self.ui.ComboBox(
                            {"ID": "lut_combo", "ItemText": ["点击刷新 LUT 库"], "MinimumSize": [330, 32]}
                        ),
                        self.ui.Button({"ID": "btn_refresh_luts", "Text": "刷新", "MinimumSize": [70, 32]}),
                        self.ui.Button({"ID": "btn_browse_lut", "Text": "浏览…", "MinimumSize": [80, 32]}),
                        self.ui.Button({"ID": "btn_apply_lut", "Text": "套用 LUT", "MinimumSize": [100, 32], "StyleSheet": CYAN_STYLE}),
                        self.ui.Button({"ID": "btn_remove_lut", "Text": "移除 LUT", "MinimumSize": [100, 32]}),
                    ],
                ),
                self.ui.Label(
                    {"ID": "lut_status", "Text": "", "WordWrap": True, "StyleSheet": "color:#8b98a8;", "MaximumSize": [900, 40]}
                ),
            ],
        )
        return self.ui.VGroup(
            {"Spacing": 8},
            [tree_card, auto_card, lut_card],
        )

    def _build_match_page(self):
        match_card = self._card(
            "镜头匹配",
            "参考帧 → 统计匹配 → 目标镜头",
            [
                self.ui.HGroup(
                    {"Spacing": 8},
                    [
                        self.ui.Button(
                            {"ID": "btn_reference", "Text": "拾取参考帧", "MinimumSize": [140, 36]}
                        ),
                        self.ui.Label(
                            {
                                "ID": "reference_info",
                                "Text": "尚未设置参考镜头",
                                "WordWrap": True,
                                "StyleSheet": "color:#8b98a8;",
                                "Weight": 1,
                                "MaximumSize": [700, 40],
                            }
                        ),
                    ],
                ),
                self.ui.HGroup(
                    {"Spacing": 8},
                    [
                        self.ui.Label({"Text": "范围", "StyleSheet": "color:#8b98a8;"}),
                        self.ui.ComboBox(
                            {
                                "ID": "match_scope",
                                "ItemText": ["当前镜头", "选中镜头", "整条时间线"],
                                "CurrentIndex": 1,
                                "MinimumSize": [150, 32],
                            }
                        ),
                        self.ui.Button(
                            {
                                "ID": "btn_match",
                                "Text": "匹配参考色调",
                                "MinimumSize": [160, 36],
                                "StyleSheet": CYAN_STYLE,
                            }
                        ),
                    ],
                ),
                self.ui.Label(
                    {"ID": "match_status", "Text": "", "WordWrap": True, "StyleSheet": "color:#8b98a8;", "MaximumSize": [900, 40]}
                ),
            ],
        )
        skin_card = self._card(
            "肤色限定与保护",
            "YCbCr 肤色遮罩 DCTL",
            [
                self.ui.Label(
                    {
                        "Text": "公开 API 不能原生创建 Qualifier 节点；这里用肤色色相/YCbCr 遮罩实现同等效果。AI 人脸检测未内置。",
                        "WordWrap": True,
                        "StyleSheet": "color:#7d8b9d;",
                    }
                ),
                self.ui.HGroup(
                    {"Spacing": 8},
                    [
                        self.ui.Label({"Text": "色相偏移", "StyleSheet": "color:#8b98a8;"}),
                        self.ui.SpinBox(
                            {
                                "ID": "skin_hue",
                                "Value": 0,
                                "Minimum": -30,
                                "Maximum": 30,
                                "Suffix": "°",
                                "MinimumSize": [100, 32],
                            }
                        ),
                        self.ui.Label({"Text": "饱和度", "StyleSheet": "color:#8b98a8;"}),
                        self.ui.SpinBox(
                            {
                                "ID": "skin_sat",
                                "Value": 0,
                                "Minimum": -50,
                                "Maximum": 50,
                                "Suffix": " %",
                                "MinimumSize": [100, 32],
                            }
                        ),
                        self.ui.Label({"Text": "亮度", "StyleSheet": "color:#8b98a8;"}),
                        self.ui.SpinBox(
                            {
                                "ID": "skin_light",
                                "Value": 0,
                                "Minimum": -50,
                                "Maximum": 50,
                                "Suffix": " %",
                                "MinimumSize": [100, 32],
                            }
                        ),
                        self.ui.CheckBox(
                            {"ID": "chk_bg_desat", "Text": "背景降饱和", "Checked": False}
                        ),
                        self.ui.Button(
                            {
                                "ID": "btn_skin",
                                "Text": "生成肤色限定",
                                "MinimumSize": [140, 36],
                                "StyleSheet": CYAN_STYLE,
                            }
                        ),
                    ],
                ),
                self.ui.Label(
                    {"ID": "skin_status", "Text": "", "WordWrap": True, "StyleSheet": "color:#8b98a8;", "MaximumSize": [900, 40]}
                ),
            ],
        )
        return self.ui.VGroup(
            {"Spacing": 8},
            [match_card, skin_card],
        )

    def _build_preset_page(self):
        save_card = self._card(
            "保存当前节点链为 DRX 预设",
            "标签分类：外景 / 室内 / 漫剧夜景",
            [
                self.ui.HGroup(
                    {"Spacing": 8},
                    [
                        self.ui.LineEdit(
                            {"ID": "preset_name", "PlaceholderText": "预设名称", "MinimumSize": [220, 34]}
                        ),
                        self.ui.ComboBox(
                            {
                                "ID": "preset_category",
                                "ItemText": ["外景", "室内", "漫剧夜景", "自定义"],
                                "MinimumSize": [140, 34],
                            }
                        ),
                        self.ui.Button(
                            {"ID": "btn_save_preset", "Text": "保存为 DRX 预设", "MinimumSize": [160, 36]}
                        ),
                    ],
                ),
                self.ui.Label(
                    {"ID": "preset_status", "Text": "", "WordWrap": True, "StyleSheet": "color:#8b98a8;", "MaximumSize": [900, 40]}
                ),
            ],
        )
        library_card = self._card(
            "预设库与批量",
            "收藏 / 搜索 / 删除 / 批量套用",
            [
                self.ui.HGroup(
                    {"Spacing": 8},
                    [
                        self.ui.ComboBox(
                            {
                                "ID": "preset_filter",
                                "ItemText": ["全部预设", "收藏预设"],
                                "MinimumSize": [120, 32],
                            }
                        ),
                        self.ui.ComboBox(
                            {"ID": "preset_combo", "ItemText": ["暂无预设"], "MinimumSize": [330, 32]}
                        ),
                        self.ui.Button({"ID": "btn_preset_fav", "Text": "收藏/取消", "MinimumSize": [100, 32]}),
                        self.ui.Button({"ID": "btn_preset_delete", "Text": "删除", "MinimumSize": [70, 32]}),
                        self.ui.Button({"ID": "btn_presets_refresh", "Text": "刷新", "MinimumSize": [70, 32]}),
                    ],
                ),
                self.ui.HGroup(
                    {"Spacing": 8},
                    [
                        self.ui.Button(
                            {"ID": "btn_apply_preset", "Text": "应用到当前镜头", "MinimumSize": [150, 36]}
                        ),
                        self.ui.ComboBox(
                            {
                                "ID": "preset_scope",
                                "ItemText": ["选中镜头", "整条时间线", "当前镜头"],
                                "CurrentIndex": 0,
                                "MinimumSize": [140, 32],
                            }
                        ),
                        self.ui.Button(
                            {
                                "ID": "btn_batch_preset",
                                "Text": "批量应用预设",
                                "MinimumSize": [150, 36],
                                "StyleSheet": CYAN_STYLE,
                            }
                        ),
                    ],
                ),
            ],
        )
        report_card = self._card(
            "时间线校验与调色报告",
            "生成 HTML 报告",
            [
                self.ui.HGroup(
                    {"Spacing": 8},
                    [
                        self.ui.Button(
                            {
                                "ID": "btn_report",
                                "Text": "校验整条时间线并输出报告",
                                "MinimumSize": [220, 38],
                            }
                        ),
                        self.ui.Label(
                            {
                                "ID": "report_status",
                                "Text": "尚未生成报告",
                                "WordWrap": True,
                                "StyleSheet": "color:#8b98a8;",
                                "Weight": 1,
                                "MaximumSize": [700, 40],
                            }
                        ),
                    ],
                ),
            ],
        )
        return self.ui.VGroup(
            {"Spacing": 8},
            [save_card, library_card, report_card],
        )

    def _connect(self):
        for widget_id, items, index in (
            ("lut_category", ["全部", "SLog3", "ARRI", "HLG", "CLog", "Rec.709", "自定义"], 0),
            ("match_scope", ["当前镜头", "选中/当前镜头", "整条时间线"], 1),
            ("preset_filter", ["全部预设", "收藏预设"], 0),
            ("preset_category", ["外景", "室内", "漫剧夜景", "自定义"], 0),
            ("preset_scope", ["当前镜头", "选中/当前镜头", "整条时间线"], 1),
            ("restore_scope", ["当前镜头", "选中/当前镜头", "整条时间线"], 0),
        ):
            combo = self._find(widget_id)
            combo.Clear()
            combo.AddItems(items)
            combo.CurrentIndex = index
        for index in range(4):
            self.win.On["tab_%d" % index].Clicked = (
                lambda event, index=index: self.switch_tab(index)
            )
            try:
                self.win.On["side_%d" % index].Clicked = (
                    lambda event, index=index: self.switch_tab(index)
                )
            except Exception:
                pass
        self.win.On["btn_close"].Clicked = self.on_close
        self.win.On["btn_refresh_analysis"].Clicked = self.on_refresh_analysis
        self.win.On["btn_refresh_nodes_top"].Clicked = self.on_refresh_nodes
        self.win.On["btn_refresh_media"].Clicked = self.on_refresh_media
        self.win.On["btn_build"].Clicked = self.on_build
        self.win.On["btn_make_tree"].Clicked = self.on_make_tree
        self.win.On["btn_make_template"].Clicked = self.on_make_template
        self.win.On["btn_auto_bw"].Clicked = self.on_auto_bw
        self.win.On["btn_auto_wb"].Clicked = self.on_auto_wb
        self.win.On["btn_auto_exposure"].Clicked = self.on_auto_exposure
        self.win.On["btn_reset"].Clicked = self.on_reset
        self.win.On["btn_undo"].Clicked = self.on_undo
        self.win.On["btn_refresh_luts"].Clicked = self.on_refresh_luts
        self.win.On["btn_browse_lut"].Clicked = self.on_browse_lut
        self.win.On["btn_apply_lut"].Clicked = self.on_apply_lut
        self.win.On["btn_remove_lut"].Clicked = self.on_remove_lut
        self.win.On["lut_category"].CurrentIndexChanged = self.on_lut_category
        self.win.On["btn_reference"].Clicked = self.on_reference
        self.win.On["btn_match"].Clicked = self.on_match
        self.win.On["btn_skin"].Clicked = self.on_skin
        self.win.On["btn_save_preset"].Clicked = self.on_save_preset
        self.win.On["btn_presets_refresh"].Clicked = self.on_refresh_presets
        self.win.On["btn_preset_fav"].Clicked = self.on_preset_fav
        self.win.On["btn_preset_delete"].Clicked = self.on_preset_delete
        self.win.On["btn_apply_preset"].Clicked = self.on_apply_preset
        self.win.On["btn_batch_preset"].Clicked = self.on_batch_preset
        self.win.On["btn_report"].Clicked = self.on_report
        self.win.On["preset_filter"].CurrentIndexChanged = self.on_refresh_presets
        self.win.On["node_combo"].CurrentIndexChanged = self.on_node_changed

    # ------------------------------------------------------------- utilities
    def _find(self, widget_id):
        widget = getattr(self, "widgets", {}).get(widget_id)
        if widget is not None:
            return widget
        return self.win.Find(widget_id)

    def _build_widget_registry(self):
        self.widgets = {}

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
                walk(child, depth + 1)

        for page in self.pages:
            walk(page)

    def _work_area(self):
        try:
            import ctypes
            from ctypes import wintypes

            rect = wintypes.RECT()
            ctypes.windll.user32.SystemParametersInfoW(
                0x0030, 0, ctypes.byref(rect), 0
            )
            return rect.left, rect.top, rect.right, rect.bottom
        except Exception:
            return 0, 0, 1920, 1080

    def _ensure_on_screen(self):
        try:
            size = self.win.Size()
            pos = self.win.Pos()
            width = int(size.get(1, 1000))
            height = int(size.get(2, 820))
            x = int(pos.get(1, 100))
            y = int(pos.get(2, 100))
            left, top, right, bottom = self._work_area()
            if (
                x < left
                or y < top
                or x + width > right
                or y + height > bottom
            ):
                self.win.Move([max(left + 40, 40), max(top + 30, 30)])
                self.win.Resize(
                    [
                        min(width, max(720, right - left - 100)),
                        min(height, max(520, bottom - top - 80)),
                    ]
                )
        except Exception:
            pass

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

    def _require_clip(self):
        context = self._context()
        if context["timeline"] is None:
            raise rb.ColorFlowError("当前没有打开的时间线。")
        if context["clip"] is None:
            raise rb.ColorFlowError("请先把播放头放在一个视频镜头上。")
        return context

    def _target_items(self, scope):
        context = self._require_clip()
        return context, rb.video_items(context["timeline"], scope, context["clip"])

    def _space(self, context):
        return rb.project_color_space(context["project"])

    def _nodes(self, clip):
        return rb.list_nodes(clip)

    def _node_label(self, node):
        return rb.node_label(node)

    def _target_node(self, role, clip):
        nodes = self._nodes(clip)
        if not nodes:
            raise rb.ColorFlowError("当前镜头没有节点。")
        if bool(self._find("chk_auto_node").Checked):
            index = features.auto_node_index(clip, role)
        else:
            index = int(self._find("node_combo").CurrentIndex) + 1
        node = next((entry for entry in nodes if entry["index"] == index), None)
        if node is None:
            raise rb.ColorFlowError("选中的节点在当前镜头上不存在。")
        if (
            bool(self._find("chk_auto_node").Checked)
            and not node.get("likely_empty")
            and not node.get("managed")
        ):
            # The role node may already contain user tools. Prefer a genuinely
            # empty node before asking the user to allow overwriting.
            empty_nodes = [entry for entry in nodes if entry.get("likely_empty")]
            managed_nodes = [entry for entry in nodes if entry.get("managed")]
            if empty_nodes:
                node = empty_nodes[-1]
            elif managed_nodes:
                node = managed_nodes[-1]
        allow_nonempty = bool(self._find("chk_allow_nonempty").Checked)
        if (
            not node.get("likely_empty")
            and not node.get("managed")
            and not allow_nonempty
        ):
            raise rb.ColorFlowError(
                "节点 %02d 已有工具或第三方 LUT。请换空白节点，"
                "或勾选“允许写非空节点”。" % index
            )
        return node

    def _backup(self, clip, label):
        if not bool(self._find("chk_backup").Checked):
            return None, None
        backup, version = rb.create_backup_version(clip, label)
        if backup and backup.get("versionName"):
            self.last_backups.append(
                (clip, backup.get("versionName"), int(backup.get("versionType", 0) or 0))
            )
        return backup, version

    def _restore_on_failure(self, clip, backup):
        if not backup:
            return
        name = backup.get("versionName")
        if name:
            try:
                rb.restore_version(clip, name, backup.get("versionType", 0))
            except Exception:
                pass

    def _save(self, context):
        try:
            context["project_manager"].SaveProject()
        except Exception:
            pass

    def _write_model(self, context, clip, model, label, role="primary"):
        node = self._target_node(role, clip)
        backup, version = self._backup(clip, label)
        space_key, space_label = self._space(context)
        try:
            detail = features.apply_model(
                context["project"],
                clip,
                node["index"],
                model,
                space_key,
                label,
            )
        except Exception:
            self._restore_on_failure(clip, backup)
            raise
        return {
            "node": node,
            "engine": "DCTL" if space_key == "dwg" else "CDL/DCTL",
            "space": space_label,
            "detail": detail,
            "backup": backup,
            "version": version,
        }

    # ---------------------------------------------------------------- context
    def refresh_context(self):
        try:
            context = self._context()
        except Exception as exc:
            self._set("ctx_project", "项目：%s" % exc, "#f87171")
            return None
        project = context["project"]
        timeline = context["timeline"]
        clip = context["clip"]
        space_key, space_label = self._space(context)
        self._set("ctx_project", "项目：%s" % project.GetName(), "#d7dce3")
        self._set(
            "ctx_timeline",
            "时间线：%s" % (timeline.GetName() if timeline else "未打开"),
            "#d7dce3",
        )
        self._set(
            "ctx_clip",
            "当前镜头：%s" % (clip.GetName() if clip else "无"),
            "#d7dce3",
        )
        self._set(
            "ctx_space",
            "色彩空间：%s" % space_label,
            "#6ee7b7" if space_key == "dwg" else "#fbbf24",
        )
        return context

    def refresh_analysis(self):
        try:
            context = self._require_clip()
            info = features.current_clip_info(context)
            self._set("analysis_clip_name", info["name"], "#f5f8fc")
            self._set("meta_resolution", "分辨率 %s" % info["resolution"], "#c7d4e3")
            self._set("meta_fps", "帧率 %s" % info["fps"], "#c7d4e3")
            self._set("meta_codec", "编码 %s" % info["codec"], "#c7d4e3")
            self._set("meta_depth", "位深 %s" % info["bit_depth"], "#c7d4e3")
            self._set("meta_wb", "白平衡 %s" % info["white_balance"], "#c7d4e3")
            log_color = "#6ee7b7" if info["log"]["recognized"] else "#fbbf24"
            self._set("meta_log", "Log %s" % info["log"]["name"], log_color)
            if info["warnings"]:
                self._set(
                    "analysis_warning",
                    "⚠ " + " · ".join(info["warnings"]),
                    "#fbbf24",
                )
            else:
                self._set("analysis_warning", "✓ 未发现明显裁切或素材不匹配", "#6ee7b7")
            self._set("analysis_status", analysis.describe_stats(info["stats"]) if info["stats"] else "未读取到画面统计。", "#8b98a8")
            self._log("素材分析：%s · %s · %s" % (info["name"], info["resolution"], info["log"]["name"]))
        except Exception as exc:
            self._set("analysis_clip_name", "未打开时间线", "#f5f8fc")
            for widget in ("meta_resolution", "meta_fps", "meta_codec", "meta_depth", "meta_wb", "meta_log"):
                self._set(widget, "—", "#7d8b9d")
            self._set("analysis_warning", "⚠ %s" % exc, "#fbbf24")
            self._set("analysis_status", "", "#8b98a8")

    def refresh_nodes(self):
        try:
            context = self._require_clip()
            nodes = self._nodes(context["clip"])
        except Exception as exc:
            nodes = []
            self._set("primary_status", str(exc), "#fbbf24")
        combo = self._find("node_combo")
        combo.Clear()
        if not nodes:
            combo.AddItem("没有可用节点")
            return
        combo.AddItems([self._node_label(node) for node in nodes])
        empty = [index for index, node in enumerate(nodes) if node.get("likely_empty")]
        index = empty[-1] if empty else len(nodes) - 1
        combo.CurrentIndex = index
        self._set(
            "primary_status",
            "节点：%s" % self._node_label(nodes[index]),
            "#6ee7b7" if nodes[index].get("likely_empty") else "#fbbf24",
        )

    def refresh_media(self):
        try:
            context = self._context()
            recursive = bool(self._find("chk_recursive").Checked)
            clips, origin = rb.media_clips(context["project"], recursive)
            if not clips:
                self._set("source_info", "当前媒体池文件夹没有视频素材。", "#fbbf24")
                return
            summary = rb.source_summary(clips)
            warning = ""
            if summary["mixed_resolution"]:
                warning += " · 分辨率不一致"
            if summary["mixed_fps"]:
                warning += " · 帧率不一致"
            self._set(
                "source_info",
                "%s · %d 个素材 · %dx%d · %.3f fps%s"
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
        except Exception as exc:
            self._set("source_info", "读取素材失败：%s" % exc, "#f87171")

    def refresh_luts(self):
        try:
            self.lut_entries = features.scan_luts()
            self._populate_lut_combo()
            self._set(
                "lut_status",
                "已扫描 %d 个 LUT/DCTL。" % len(self.lut_entries),
                "#6ee7b7",
            )
        except Exception as exc:
            self._set("lut_status", "扫描 LUT 失败：%s" % exc, "#f87171")

    def _populate_lut_combo(self):
        category = str(self._find("lut_category").CurrentText)
        if category == "全部":
            entries = self.lut_entries
        elif category == "自定义":
            entries = [item for item in self.lut_entries if item["category"] == "自定义"]
        else:
            entries = [item for item in self.lut_entries if item["category"] == category]
        self._visible_luts = entries[:500]
        combo = self._find("lut_combo")
        combo.Clear()
        if not self._visible_luts:
            combo.AddItem("没有匹配的 LUT")
            return
        combo.AddItems([item["relative"] for item in self._visible_luts])
        combo.CurrentIndex = 0

    def refresh_presets(self):
        try:
            self.preset_entries = features.list_presets()
        except Exception:
            self.preset_entries = []
        only_fav = int(self._find("preset_filter").CurrentIndex) == 1
        entries = [entry for entry in self.preset_entries if entry.get("exists")]
        if only_fav:
            entries = [entry for entry in entries if entry.get("favorite")]
        self._visible_presets = entries
        combo = self._find("preset_combo")
        combo.Clear()
        if not entries:
            combo.AddItem("暂无预设")
            return
        combo.AddItems(
            [
                "%s%s · %s" % ("★ " if entry.get("favorite") else "", entry.get("name"), entry.get("category"))
                for entry in entries
            ]
        )
        combo.CurrentIndex = 0

    def refresh_all(self):
        self.refresh_context()
        self.refresh_analysis()
        self.refresh_nodes()
        self.refresh_media()
        self.refresh_luts()
        self.refresh_presets()

    def switch_tab(self, index):
        index = max(0, min(3, int(index)))
        if index == self.active_tab:
            return
        old_page = self.pages[self.active_tab]
        try:
            self.page_host.RemoveChild(old_page)
        except Exception:
            pass
        try:
            self.page_host.AddChild(self.pages[index])
        except Exception:
            pass
        try:
            self.win.RecalcLayout()
        except Exception:
            pass
        self.active_tab = index
        for position in range(4):
            try:
                self._find("tab_%d" % position).StyleSheet = (
                    TAB_ACTIVE if position == index else TAB_IDLE
                )
            except Exception:
                pass
            try:
                self._find("side_%d" % position).StyleSheet = (
                    SIDE_ACTIVE if position == index else SIDE_IDLE
                )
            except Exception:
                pass
        self.pump()

    # ---------------------------------------------------------------- handlers
    def on_refresh_analysis(self, event):
        self.refresh_context()
        self.refresh_analysis()

    def on_refresh_media(self, event):
        self.refresh_media()

    def on_refresh_nodes(self, event):
        self.refresh_nodes()

    def on_node_changed(self, event):
        pass

    def on_build(self, event):
        try:
            context = self._context()
            clips, origin = rb.media_clips(
                context["project"], bool(self._find("chk_recursive").Checked)
            )
            if not clips:
                raise rb.ColorFlowError("当前媒体池没有视频素材。")
            name = "ColorFlow · %s · %s" % (origin, datetime.now().strftime("%m%d-%H%M%S"))
            start_tc = "01:00:00:00" if bool(self._find("chk_start_tc").Checked) else None
            result = rb.create_timeline(context["project"], clips, name, start_tc)
            try:
                context["project_manager"].SaveProject()
            except Exception:
                pass
            self._set("build_status", "已创建 %s · %s" % (result["name"], result["duration"]), "#6ee7b7")
            self._log("建线完成：%s" % result["name"])
            self.refresh_all()
        except Exception as exc:
            self._set("build_status", "建线失败：%s" % exc, "#f87171")
            self._log("建线失败：%s" % exc)

    def on_make_tree(self, event):
        try:
            context = self._require_clip()
            path = features.find_template()
            if not path:
                raise rb.ColorFlowError(
                    "还没有节点模板。请先在 Color 页面准备多节点链，"
                    "然后点“从当前节点链生成模板”。"
                )
            backup, version = self._backup(context["clip"], "套用节点树前")
            try:
                nodes = features.apply_template(context["project"], context["clip"], path)
            except Exception:
                self._restore_on_failure(context["clip"], backup)
                raise
            self._set("tree_status", "已套用模板：%d 个节点。" % nodes, "#6ee7b7")
            self._log("套用节点模板：%s（%d 节点）" % (os.path.basename(path), nodes))
            self._save(context)
            self.refresh_nodes()
        except Exception as exc:
            self._set("tree_status", "套用模板失败：%s" % exc, "#f87171")
            self._log("套用模板失败：%s" % exc)

    def on_make_template(self, event):
        try:
            context = self._require_clip()
            self._set("tree_status", "正在复制时间线并生成模板…", "#fbbf24")
            try:
                self.resolve.OpenPage("color")
                time.sleep(0.4)
            except Exception:
                pass
            path, nodes = features.create_template_from_timeline(
                context["project"], context["timeline"], "ColorFlow_5node"
            )
            self._set("tree_status", "模板已生成：%d 节点 · %s" % (nodes, path), "#6ee7b7")
            self._log("节点模板已生成：%s" % path)
        except Exception as exc:
            self._set("tree_status", "生成模板失败：%s" % exc, "#f87171")
            self._log("生成模板失败：%s" % exc)

    def _auto_common(self, model_builder, label, role="primary"):
        try:
            context = self._require_clip()
            capture = rb.capture_item_thumbnail(context["timeline"], context["clip"])
            model = model_builder(capture["stats"])
            result = self._write_model(context, context["clip"], model, label, role)
            self._set(
                "primary_status",
                "已写入 %02d 号节点 · %s" % (result["node"]["index"], analysis.describe_model(model)),
                "#6ee7b7",
            )
            self._log("%s：%s" % (label, analysis.describe_model(model)))
            self._save(context)
            self.refresh_nodes()
        except Exception as exc:
            self._set("primary_status", "%s失败：%s" % (label, exc), "#f87171")
            self._log("%s失败：%s" % (label, exc))

    def on_auto_bw(self, event):
        try:
            context = self._require_clip()
            capture = rb.capture_item_thumbnail(context["timeline"], context["clip"])
            strength = self._strength("primary_strength")
            space_key, _ = self._space(context)
            node = self._target_node("exposure", context["clip"])
            backup, version = self._backup(context["clip"], "自动黑白场前")
            try:
                features.apply_tone_stretch(
                    context["project"],
                    context["clip"],
                    node["index"],
                    capture["stats"],
                    strength,
                    space_key,
                    "auto-bw-%s" % context["clip"].GetName(),
                )
            except Exception:
                self._restore_on_failure(context["clip"], backup)
                raise
            self._set("primary_status", "自动黑白场已写入 %02d 号节点。" % node["index"], "#6ee7b7")
            self._log("自动黑白场：p01 %.4f / p99 %.4f" % (capture["stats"].get("p01", 0), capture["stats"].get("p99", 0)))
            self._save(context)
            self.refresh_nodes()
        except Exception as exc:
            self._set("primary_status", "自动黑白场失败：%s" % exc, "#f87171")
            self._log("自动黑白场失败：%s" % exc)

    def on_auto_wb(self, event):
        self._auto_common(
            lambda stats: analysis.restore_model(
                stats, self._strength("primary_strength"), False
            ),
            "自动白平衡",
            "temperature",
        )

    def on_auto_exposure(self, event):
        self._auto_common(
            lambda stats: analysis.exposure_model(
                stats, self._strength("primary_strength")
            ),
            "自动曝光拉伸",
            "exposure",
        )

    def on_refresh_luts(self, event):
        self.refresh_luts()

    def on_lut_category(self, event):
        try:
            self._populate_lut_combo()
        except Exception:
            pass

    def on_browse_lut(self, event):
        try:
            path = self.fusion.RequestFile()
            if not path:
                return
            absolute, relative = features.import_lut(str(path))
            self._apply_lut_path(absolute, relative)
        except Exception as exc:
            self._set("lut_status", "套用 LUT 失败：%s" % exc, "#f87171")
            self._log("套用 LUT 失败：%s" % exc)

    def _apply_lut_path(self, absolute, relative):
        context = self._require_clip()
        node = self._target_node("style", context["clip"])
        backup, version = self._backup(context["clip"], "套用 LUT 前")
        try:
            rb.apply_lut(context["project"], context["clip"], node["index"], absolute, relative)
        except Exception:
            self._restore_on_failure(context["clip"], backup)
            raise
        self._set("lut_status", "LUT 已写入 %02d 号节点：%s" % (node["index"], relative), "#6ee7b7")
        self._log("套用 LUT：%s" % relative)
        self._save(context)
        self.refresh_nodes()

    def on_apply_lut(self, event):
        try:
            if not getattr(self, "_visible_luts", None):
                raise rb.ColorFlowError("没有可套用的 LUT，请先刷新 LUT 库。")
            index = int(self._find("lut_combo").CurrentIndex)
            entry = self._visible_luts[index]
            self._apply_lut_path(entry["absolute"], entry["relative"])
        except Exception as exc:
            self._set("lut_status", "套用 LUT 失败：%s" % exc, "#f87171")
            self._log("套用 LUT 失败：%s" % exc)

    def on_remove_lut(self, event):
        try:
            context = self._require_clip()
            node = self._target_node("style", context["clip"])
            backup, version = self._backup(context["clip"], "移除 LUT 前")
            try:
                features.clear_lut(context["clip"], node["index"])
            except Exception:
                self._restore_on_failure(context["clip"], backup)
                raise
            self._set("lut_status", "已移除 %02d 号节点的 LUT。" % node["index"], "#6ee7b7")
            self._log("移除 LUT：节点 %02d" % node["index"])
            self._save(context)
            self.refresh_nodes()
        except Exception as exc:
            self._set("lut_status", "移除 LUT 失败：%s" % exc, "#f87171")

    def on_reference(self, event):
        try:
            context = self._require_clip()
            capture = rb.capture_item_thumbnail(context["timeline"], context["clip"])
            self.reference = {
                "name": capture["name"],
                "stats": capture["stats"],
                "clip_id": context["clip"].GetUniqueId(),
            }
            self._set("reference_info", "参考：%s（已锁定）" % capture["name"], "#6ee7b7")
            self._log("参考帧：%s｜%s" % (capture["name"], analysis.describe_stats(capture["stats"])))
        except Exception as exc:
            self._set("reference_info", "拾取参考失败：%s" % exc, "#f87171")

    def on_match(self, event):
        try:
            if self.reference is None:
                raise rb.ColorFlowError("请先点击“拾取参考帧”。")
            scope = self._scope("match_scope")
            context, items = self._target_items(scope)
            targets = [
                item
                for item in items
                if item.GetUniqueId() != self.reference["clip_id"]
            ]
            if not targets:
                raise rb.ColorFlowError("没有可匹配的目标镜头。")
            successes = 0
            failures = []
            for item in targets:
                if self._cancel_requested:
                    break
                try:
                    capture = rb.capture_item_thumbnail(context["timeline"], item)
                    strength = 0.70
                    try:
                        strength = self._strength("match_strength")
                    except Exception:
                        pass
                    model = analysis.match_model(
                        self.reference["stats"], capture["stats"], strength
                    )
                    result = self._write_model(context, item, model, "匹配-%s" % item.GetName(), "match")
                    successes += 1
                    self._log(
                        "%s → %02d 节点：%s"
                        % (item.GetName(), result["node"]["index"], analysis.describe_model(model))
                    )
                except Exception as exc:
                    failures.append((item.GetName(), str(exc)))
                    self._log("匹配失败：%s：%s" % (item.GetName(), exc))
                self.pump()
            try:
                context["project_manager"].SaveProject()
            except Exception:
                pass
            color = "#f87171" if failures else "#6ee7b7"
            text = "匹配完成 %d 个" % successes
            if failures:
                text += "，失败 %d 个（%s）" % (len(failures), failures[0][1])
            self._set("match_status", text, color)
            self.refresh_nodes()
        except Exception as exc:
            self._set("match_status", "匹配失败：%s" % exc, "#f87171")
            self._log("匹配失败：%s" % exc)

    def on_skin(self, event):
        try:
            context = self._require_clip()
            node = self._target_node("skin", context["clip"])
            backup, version = self._backup(context["clip"], "肤色限定前")
            space_key, _ = self._space(context)
            bg = 0.5 if bool(self._find("chk_bg_desat").Checked) else 0.0
            try:
                features.apply_skin(
                    context["project"],
                    context["clip"],
                    node["index"],
                    float(self._find("skin_hue").Value),
                    float(self._find("skin_sat").Value),
                    float(self._find("skin_light").Value),
                    bg,
                    space_key,
                    "skin-%s" % context["clip"].GetName(),
                )
            except Exception:
                self._restore_on_failure(context["clip"], backup)
                raise
            self._set("skin_status", "肤色限定 DCTL 已写入 %02d 号节点。" % node["index"], "#6ee7b7")
            self._log("肤色限定：节点 %02d · 色相 %.1f · 饱和 %.1f · 亮度 %.1f" % (node["index"], self._find("skin_hue").Value, self._find("skin_sat").Value, self._find("skin_light").Value))
            self._save(context)
            self.refresh_nodes()
        except Exception as exc:
            self._set("skin_status", "肤色限定失败：%s" % exc, "#f87171")
            self._log("肤色限定失败：%s" % exc)

    def on_save_preset(self, event):
        try:
            context = self._require_clip()
            name = str(self._find("preset_name").Text or "").strip()
            if not name:
                name = "ColorFlow · %s" % datetime.now().strftime("%m%d-%H%M%S")
            category = str(self._find("preset_category").CurrentText)
            try:
                self.resolve.OpenPage("color")
                time.sleep(0.4)
            except Exception:
                pass
            entry = features.save_preset_with_project(
                context["project"], context["timeline"], name, category
            )
            self._set("preset_status", "已保存预设：%s" % entry["file"], "#6ee7b7")
            self._log("保存 DRX 预设：%s" % entry["file"])
            self.refresh_presets()
        except Exception as exc:
            self._set("preset_status", "保存预设失败：%s" % exc, "#f87171")
            self._log("保存预设失败：%s" % exc)

    def on_refresh_presets(self, event):
        self.refresh_presets()

    def _selected_preset(self):
        index = int(self._find("preset_combo").CurrentIndex)
        entries = getattr(self, "_visible_presets", [])
        if index < 0 or index >= len(entries):
            raise rb.ColorFlowError("请选择一个预设。")
        return entries[index]

    def on_preset_fav(self, event):
        try:
            entry = self._selected_preset()
            features.toggle_favorite(entry["key"])
            self.refresh_presets()
            self._log("切换收藏：%s" % entry["name"])
        except Exception as exc:
            self._set("preset_status", "收藏失败：%s" % exc, "#f87171")

    def on_preset_delete(self, event):
        try:
            entry = self._selected_preset()
            features.delete_preset(entry["key"])
            self.refresh_presets()
            self._log("删除预设：%s" % entry["name"])
        except Exception as exc:
            self._set("preset_status", "删除失败：%s" % exc, "#f87171")

    def on_apply_preset(self, event):
        try:
            context = self._require_clip()
            entry = self._selected_preset()
            backup, version = self._backup(context["clip"], "套用预设前")
            try:
                features.apply_preset(context["project"], context["clip"], entry["file"])
            except Exception:
                self._restore_on_failure(context["clip"], backup)
                raise
            self._set("preset_status", "已应用：%s" % entry["name"], "#6ee7b7")
            self._log("应用预设：%s" % entry["name"])
            self._save(context)
            self.refresh_nodes()
        except Exception as exc:
            self._set("preset_status", "应用预设失败：%s" % exc, "#f87171")

    def on_batch_preset(self, event):
        try:
            entry = self._selected_preset()
            context, items = self._target_items(self._scope("preset_scope"))
            successes = 0
            failures = []
            for item in items:
                if self._cancel_requested:
                    break
                try:
                    backup, version = self._backup(item, "批量预设前")
                    try:
                        features.apply_preset(context["project"], item, entry["file"])
                    except Exception:
                        self._restore_on_failure(item, backup)
                        raise
                    successes += 1
                    self._log("批量预设：%s" % item.GetName())
                except Exception as exc:
                    failures.append((item.GetName(), str(exc)))
                self.pump()
            try:
                context["project_manager"].SaveProject()
            except Exception:
                pass
            self._set(
                "preset_status",
                "批量应用完成 %d 个%s" % (
                    successes,
                    ("，失败 %d 个（%s）" % (len(failures), failures[0][1])) if failures else "",
                ),
                "#f87171" if failures else "#6ee7b7",
            )
            self.refresh_nodes()
        except Exception as exc:
            self._set("preset_status", "批量应用失败：%s" % exc, "#f87171")

    def on_report(self, event):
        try:
            context = self._require_clip()

            def progress(index, total, name):
                self._set(
                    "report_status",
                    "正在分析 %d/%d：%s" % (index + 1, total, name),
                    "#fbbf24",
                )
                self.pump()

            path, rows = features.report_timeline(
                context["project"], context["timeline"], progress
            )
            self.last_report = path
            warnings = sum(1 for row in rows if row["info"].get("warnings"))
            self._set(
                "report_status",
                "报告已生成：%s（%d 个镜头，%d 个警告）" % (path, len(rows), warnings),
                "#6ee7b7" if not warnings else "#fbbf24",
            )
            self._log("调色报告：%s" % path)
        except Exception as exc:
            self._set("report_status", "生成报告失败：%s" % exc, "#f87171")
            self._log("生成报告失败：%s" % exc)

    def on_reset(self, event):
        try:
            context, items = self._target_items(self._scope("restore_scope"))
            successes = 0
            failures = []
            for item in items:
                if self._cancel_requested:
                    break
                backup = None
                try:
                    backup, version = rb.create_backup_version(item, "还原前")
                    if backup and backup.get("versionName"):
                        self.last_backups.append(
                            (
                                item,
                                backup.get("versionName"),
                                int(backup.get("versionType", 0) or 0),
                            )
                        )
                    rb.reset_grade(item)
                    successes += 1
                    self._log("还原原始：%s（%s）" % (item.GetName(), version))
                except Exception as exc:
                    self._restore_on_failure(item, backup)
                    failures.append((item.GetName(), str(exc)))
                self.pump()
            self._save(context)
            self._set(
                "primary_status",
                "还原完成 %d 个%s"
                % (
                    successes,
                    ("，失败 %d 个（%s）" % (len(failures), failures[0][1])) if failures else "",
                ),
                "#f87171" if failures else "#6ee7b7",
            )
            self.refresh_nodes()
        except Exception as exc:
            self._set("primary_status", "还原失败：%s" % exc, "#f87171")
            self._log("还原失败：%s" % exc)

    def on_undo(self, event):
        if not self.last_backups:
            self._set("primary_status", "没有可撤销的本次写入。", "#fbbf24")
            return
        restored = 0
        for clip, name, version_type in reversed(self.last_backups):
            try:
                if rb.restore_version(clip, name, version_type):
                    restored += 1
            except Exception:
                pass
        self.last_backups = []
        self._set("primary_status", "已恢复 %d 个镜头。" % restored, "#6ee7b7")
        try:
            context = self._context()
            self._save(context)
        except Exception:
            pass

    def on_close(self, event):
        if self._closing:
            return
        self._closing = True
        self._cancel_requested = True
        try:
            self.win.Hide()
        except Exception:
            pass
        try:
            self.dispatcher.ExitLoop()
        except Exception:
            pass

    def show(self):
        self.win = self._build_window()
        self.tab_buttons = [self._find("tab_%d" % index) for index in range(4)]
        self.side_buttons = [self._find("side_%d" % index) for index in range(4)]
        self._build_widget_registry()
        self._connect()
        for page in self.pages[1:]:
            try:
                self.page_host.RemoveChild(page)
            except Exception:
                pass
        self.win.Show()
        self._ensure_on_screen()
        try:
            self.win.RecalcLayout()
        except Exception:
            pass
        self.refresh_all()
        self._log(
            "ColorFlow v%s 已启动。无时间线时可以浏览界面，操作前请打开项目和时间线。"
            % VERSION
        )
        self.dispatcher.RunLoop()
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

