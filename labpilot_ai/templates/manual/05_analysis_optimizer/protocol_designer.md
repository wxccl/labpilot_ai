# Protocol Designer

Protocol Designer 用来把论文文字、PDF 摘要、图片路径和实验想法整理成实验方案建议。这个页面只生成建议，不直接执行硬件动作。

支持入口：

- `Import text/Markdown`：导入 `.txt`、`.md`、`.markdown`。
- `Import PDF`：使用可选依赖 `pypdf` 提取文本。
- `Attach image path`：记录图片文件名、路径和人工说明；第一版不做 OCR 或本地图像识别。
- `Generate protocol suggestion`：生成实验方案建议。
- `Send to Command box`：复制建议到 Command 页，不自动 Parse，也不自动 Execute。

PDF 依赖：

```powershell
pip install -e ".[docs]"
```

或：

```powershell
pip install pypdf
```

建议流程：

1. 导入论文或实验描述。
2. 添加图片路径和人工说明。
3. 生成 protocol suggestion。
4. 人工检查建议是否符合实验安全要求。
5. 复制到 Command 页，再手动 Parse 和执行。
