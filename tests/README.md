# ColorFlow tests

纯离线算法测试：

```powershell
python -m unittest discover -s tests -v
```

Resolve 联调测试会操作本机正在运行的 Resolve 项目，请先确认项目状态：

- `timeline_smoke.py`：读取当前媒体池，临时创建一条测试时间线，校验分辨率/帧率/起始时间码后删除；
- `resolve_write_smoke.py`：复制当前时间线，在副本的第 1 层节点写入 DCTL，验证版本备份、ResetAllGrades 与版本回退后删除副本；
- `dctl_runtime_smoke.py`：在副本上导出写入前后实际帧，用像素差证明 DCTL 真的参与渲染，再验证回退；
- `dctl_differential_probe.py`：与本机已安装的 Onv13 DCTL 做差分对照，用于排查“路径写入成功但画面不变”的问题（可选，依赖 Onv13 文件存在）；
- `ui_handler_probe.py`：创建真实 UIManager 面板，执行刷新素材、锁参考镜头等只读操作；
- `ui_full_probe.py`：只创建面板并进入事件循环，用于人工检查布局。
- `close_test_probe.py`：走完整 `show()` 生命周期，用于验证关闭按钮后窗口是否真正销毁。
- `lut_gallery_probe.py`：实际构建 LUT 图库，验证缩略图、分页和关闭；
- `lut_gallery_page_probe.py`：验证 English 分类筛选和上一页 / 下一页；
- `lut_gallery_state_probe.py`：输出 Tree 选中项、预览路径和行映射，排查 Resolve 的 Tree 行为；
- `window_close_probe.py`：确认 UIManager `Window.Close()` / `Hide()` 的实际返回行为。

这些脚本不会删除原始时间线或素材。`resolve_write_smoke.py` 会额外生成一个 `LUT/ColorFlow/*.dctl` 测试文件。

