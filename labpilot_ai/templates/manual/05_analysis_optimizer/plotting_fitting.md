# 绘图与拟合

分析绘图集中在 `analysis/`。

## 支持的图

当前设计覆盖：

- 1D scatter。
- 1D line。
- 均值 errorbar。
- histogram。
- 2D scatter color map。
- 2D grid heatmap。
- 3D scatter。
- 3D surface/分布图。

## 拟合模型

基础拟合模型在 `analysis/fit_models.py`：

- linear
- gaussian
- logarithmic
- exponential
- lorentzian
- 2D gaussian
- double 2D gaussian

如果没有安装 scipy，部分拟合会降级或不可用。安装：

```powershell
pip install -e ".[fit]"
```

## 输出

绘图和拟合应该保存：

- 图像路径。
- 拟合参数。
- 参数误差。
- R2 或残差指标。
- 输入字段名。
- 数据筛选条件。
- 生成时间。

这些信息会进入 lyse multi 结果表或项目数据库，保证报告可复现。

当前实现会把分析记录写入：

```text
labpilot_outputs/lyse_results/analysis_results.jsonl
```

记录类型包括：

- `single`
- `multi`
- `plot`
- `fit`
- `report`

## 相关代码

- `analysis/plotting.py`
- `analysis/fit_models.py`
- `analysis/report_generator.py`
- `lyse_ctrl/result_store.py`

## 使用建议

真实数据分析时，先在 Lyse 页面手动选择 H5 文件夹和字段，确认图能正常生成，再交给自然语言 action 调用。
