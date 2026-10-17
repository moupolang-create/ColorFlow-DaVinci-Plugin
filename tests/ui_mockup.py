import os
import sys
import uuid

import DaVinciResolveScript as dvr


resolve = dvr.scriptapp("Resolve")
fusion = resolve.Fusion()
ui = fusion.UIManager
dispatcher = dvr.UIDispatcher(ui)
win_id = "com.colorflow.mockup." + uuid.uuid4().hex[:8]

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
QTextEdit {
    background-color: #0d1015;
    border: 1px solid #232a33;
    border-radius: 7px;
    color: #b9c6d6;
}
"""


def card(title, subtitle, children):
    return ui.VGroup(
        {
            "Spacing": 10,
            "StyleSheet": "background-color:#14181e;border:1px solid #232b35;border-radius:12px;padding:16px;",
        },
        [
            ui.Label(
                {
                    "Text": '<span style="font-size:13pt;font-weight:700;color:#f5f8fc;">%s</span>'
                    '<span style="color:#7d8b9d;">  %s</span>' % (title, subtitle)
                }
            ),
            *children,
        ],
    )


def chip(text):
    return ui.Label(
        {
            "Text": text,
            "StyleSheet": "background-color:#1b222b;border:1px solid #2b3542;border-radius:6px;padding:5px 9px;color:#c7d4e3;",
        }
    )


def node_box(text, accent=False):
    color = "#22d3ee" if accent else "#2b3542"
    fg = "#041014" if accent else "#dce5ef"
    bg = "#22d3ee" if accent else "#1a2028"
    return ui.Label(
        {
            "Text": text,
            "Alignment": "AlignCenter",
            "MinimumSize": [96, 42],
            "StyleSheet": "background-color:%s;border:1px solid %s;border-radius:8px;color:%s;font-weight:600;"
            % (bg, color, fg),
        }
    )


def arrow():
    return ui.Label({"Text": "›", "StyleSheet": "color:#5f7187;font-size:16pt;"})


def cyan_button(text, width=210):
    return ui.Button(
        {
            "Text": text,
            "MinimumSize": [width, 44],
            "StyleSheet": "background-color:#22d3ee;border:1px solid #22d3ee;border-radius:9px;color:#041014;font-size:11pt;font-weight:700;padding:10px 18px;",
        }
    )


header = ui.HGroup(
    {"Spacing": 10},
    [
        ui.Label({"Text": "◈", "StyleSheet": "color:#22d3ee;font-size:15pt;"}),
        ui.Label({"Text": "DaVinci", "StyleSheet": "color:#8b98a8;font-size:9pt;"}),
        ui.HGap(0, 1),
        ui.Label({"Text": "ColorFlow", "StyleSheet": "color:#f5f8fc;font-size:16pt;font-weight:700;"}),
        ui.Label({"Text": "调色助手", "StyleSheet": "color:#7d8b9d;font-size:10pt;"}),
        ui.HGap(0, 2),
        ui.Label({"Text": "面板预览", "StyleSheet": "color:#22d3ee;font-size:9pt;"}),
    ],
)

sidebar = ui.VGroup(
    {
        "Spacing": 6,
        "StyleSheet": "background-color:#0e1116;border:1px solid #1d242d;border-radius:12px;padding:12px 8px;",
    },
    [
        ui.Label({"Text": "✦", "StyleSheet": "color:#22d3ee;font-size:16pt;", "Alignment": "AlignCenter"}),
        ui.VGap(10),
        ui.Label({"Text": "◈", "StyleSheet": "color:#22d3ee;font-size:16pt;", "Alignment": "AlignCenter"}),
        ui.Label({"Text": "◐", "StyleSheet": "color:#6d7c8e;font-size:16pt;", "Alignment": "AlignCenter"}),
        ui.Label({"Text": "◎", "StyleSheet": "color:#6d7c8e;font-size:16pt;", "Alignment": "AlignCenter"}),
        ui.Label({"Text": "▤", "StyleSheet": "color:#6d7c8e;font-size:16pt;", "Alignment": "AlignCenter"}),
        ui.VGap(0, 1),
        ui.Label({"Text": "◉", "StyleSheet": "color:#4b5a6c;font-size:13pt;", "Alignment": "AlignCenter"}),
    ],
)

tabs = ui.HGroup(
    {"Spacing": 8},
    [
        ui.Button({"Text": "素材分析", "Checkable": True, "Checked": True, "MinimumSize": [0, 42]}),
        ui.Button({"Text": "一级调色", "Checkable": True, "MinimumSize": [0, 42]}),
        ui.Button({"Text": "镜头匹配与肤色", "Checkable": True, "MinimumSize": [0, 42]}),
        ui.Button({"Text": "预设与批量", "Checkable": True, "MinimumSize": [0, 42]}),
    ],
)

analysis_page = card(
    "当前素材",
    "读取媒体池与时间线元数据",
    [
        ui.Label({"Text": "A132_C004_0113WJ_001.mxf", "StyleSheet": "font-size:15pt;font-weight:700;color:#f5f8fc;"}),
        ui.HGroup(
            {"Spacing": 7},
            [
                chip("5120 × 2700"),
                chip("30 fps"),
                chip("Apple ProRes 4444"),
                chip("10 bit"),
                chip("WB 5600 K"),
                chip("Log: 未识别"),
            ],
        ),
        ui.Label(
            {
                "Text": '<span style="color:#fbbf24;">⚠ 高光接近裁切</span>'
                '<span style="color:#7d8b9d;">   ·   </span>'
                '<span style="color:#f87171;">素材分辨率与时间线不一致</span>',
            }
        ),
        ui.Button({"Text": "刷新素材信息", "MinimumSize": [150, 36]}),
    ],
)

primary_page = card(
    "一键生成标准调色节点树",
    "输入 → Log还原 → 一级校色 → 肤色Qualifier → 风格LUT",
    [
        ui.HGroup(
            {"Spacing": 6},
            [
                node_box("输入"),
                arrow(),
                node_box("Log 还原"),
                arrow(),
                node_box("一级校色"),
                arrow(),
                node_box("肤色"),
                arrow(),
                node_box("风格 LUT", accent=True),
            ],
        ),
        ui.HGroup(
            {"Spacing": 12},
            [
                cyan_button("＋  自动黑白场", 240),
                cyan_button("＋  自动白平衡", 240),
                ui.Button({"Text": "自动曝光拉伸", "MinimumSize": [160, 44]}),
            ],
        ),
        ui.HGroup(
            {"Spacing": 8},
            [
                ui.Label({"Text": "LUT 库", "StyleSheet": "color:#8b98a8;"}),
                ui.ComboBox({"ItemText": ["SLog3 → Rec.709", "ARRI LogC3 → Rec.709", "HLG → Rec.709", "自定义收藏"], "MinimumSize": [260, 36]}),
                ui.Button({"Text": "套用 LUT", "MinimumSize": [110, 36]}),
                ui.Button({"Text": "移除 LUT", "MinimumSize": [110, 36]}),
            ],
        ),
    ],
)

match_page = card(
    "镜头匹配与肤色",
    "参考帧 → 统计匹配 → 肤色保护",
    [
        ui.HGroup(
            {"Spacing": 10},
            [
                ui.Button({"Text": "拾取参考帧", "MinimumSize": [150, 40]}),
                chip("参考：A132_C004 · 中间调 0.254"),
                ui.HGap(0, 1),
                ui.Button({"Text": "匹配选中镜头", "MinimumSize": [150, 40]}),
            ],
        ),
        ui.HGroup(
            {"Spacing": 8},
            [
                ui.Label({"Text": "肤色色相", "StyleSheet": "color:#8b98a8;"}),
                ui.SpinBox({"Value": 0, "Minimum": -30, "Maximum": 30, "MinimumSize": [110, 34]}),
                ui.Label({"Text": "饱和度", "StyleSheet": "color:#8b98a8;"}),
                ui.SpinBox({"Value": 0, "Minimum": -50, "Maximum": 50, "MinimumSize": [110, 34]}),
                ui.Label({"Text": "亮度", "StyleSheet": "color:#8b98a8;"}),
                ui.SpinBox({"Value": 0, "Minimum": -50, "Maximum": 50, "MinimumSize": [110, 34]}),
            ],
        ),
        ui.Button({"Text": "保护肤色 · 背景降饱和", "MinimumSize": [220, 40]}),
    ],
)

preset_page = card(
    "预设与批量",
    "保存节点链、批量套用、输出调色报告",
    [
        ui.HGroup(
            {"Spacing": 8},
            [
                ui.LineEdit({"PlaceholderText": "预设名称", "MinimumSize": [220, 36]}),
                ui.ComboBox({"ItemText": ["外景", "室内", "漫剧夜景"], "MinimumSize": [140, 36]}),
                ui.Button({"Text": "保存为 DRX 预设", "MinimumSize": [150, 36]}),
            ],
        ),
        ui.HGroup(
            {"Spacing": 8},
            [
                ui.ComboBox({"ItemText": ["收藏预设", "全部预设"], "MinimumSize": [160, 36]}),
                ui.Button({"Text": "批量应用预设", "MinimumSize": [150, 36]}),
                ui.Button({"Text": "校验时间线并输出报告", "MinimumSize": [190, 36]}),
            ],
        ),
        ui.Label({"Text": "报告：0 个镜头 · 0 个高光警告 · 0 个不匹配", "StyleSheet": "color:#7d8b9d;"}),
    ],
)

pages = ui.VGroup({"Spacing": 10}, [analysis_page, primary_page, match_page, preset_page])
primary_page.Hide()
match_page.Hide()
preset_page.Hide()

content = ui.VGroup(
    {"Spacing": 10},
    [
        tabs,
        pages,
        ui.HGap(0, 1),
    ],
)

body = ui.HGroup({"Spacing": 12}, [sidebar, content])
root = ui.VGroup({"Spacing": 10}, [header, body])

win = dispatcher.AddWindow(
    {
        "ID": win_id,
        "Geometry": [120, 80, 1120, 760],
        "WindowTitle": "ColorFlow · UI Mockup",
        "StyleSheet": STYLE,
    },
    root,
)


def close(event):
    dispatcher.ExitLoop()


win.On[win_id].Close = close
win.Show()
print("MOCKUP_SHOWN", flush=True)
dispatcher.RunLoop()
try:
    win.Close()
except Exception:
    pass
print("MOCKUP_DONE", flush=True)

