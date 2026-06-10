# lyse/HDF5 数据层

lyse 控制集中在 `lyse_ctrl/`，目标是在不破坏原始 H5 格式的前提下读取数据、执行可选分析模块并缓存结果。

## 功能

- 加载单个 H5 文件。
- 加载 H5 文件夹。
- 实时刷新新 shot。
- 运行 single lyse 模块。
- 运行 multi lyse 模块。
- 管理模块启用状态和执行顺序。
- 缓存结果到本地结果表。
- 勾选 single/multi 模块后按 order 批量执行。
- single 模块输出会写回当前 H5 表格，成为后续 multi、绘图、拟合和优化可选字段。

## 相关代码

- `lyse_ctrl/h5_loader.py`：H5 文件读取。
- `lyse_ctrl/module_manager.py`：模块发现、排序和启用。
- `lyse_ctrl/single_runner.py`：single 模块执行。
- `lyse_ctrl/multi_runner.py`：multi 模块执行。
- `lyse_ctrl/result_store.py`：结果缓存。

## Module registry

`configs/lyse_registry.yaml` 描述可选模块：

```yaml
single_modules:
  atom_number:
    path: "plugins/single_modules/atom_number.py"
    enabled: true
    order: 10
    outputs:
      - N_total
      - temperature_uK
```

## 数据原则

- 原始 H5 不应被破坏。
- 额外结果可以写入兼容位置或本地 cache。
- 绘图和报告引用可复现的 result 字段。
- AI 只能选择已登记的字段和模块。

## lyse multi 功能方向

- 单参数散点/折线/均值 errorbar。
- histogram 和分布拟合。
- 双参数 scatter、errorbar、heatmap。
- 三参数 3D scatter/surface、2D heatmap/contour。
- 拟合参数、误差、R2、图像路径和报告摘要保存到结果表。

## UI 按钮

Lyse 页面提供：

- `Run selected single on selected shot`
- `Run checked singles on selected shot`
- `Run checked singles on table`
- `Run selected multi on table`
- `Run checked multis on table`
- `Draw plot`
- `Fit`
- `Generate report`

所有模块运行、绘图、拟合和报告都会追加到 `labpilot_outputs/lyse_results/analysis_results.jsonl`，UI 中的 Analysis records 表格会显示最近动作。
