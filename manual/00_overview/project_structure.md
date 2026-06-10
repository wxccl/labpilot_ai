# 项目结构

## 顶层目录

```text
labpilot_ai/
  configs/              # 实验室配置和 registry
  labpilot_ai/          # Python 包源码
  manual/               # 使用和开发手册
  plugins/              # single/multi lyse 模块示例或实验室模块
  tests/                # 单元测试和集成测试
  README.md             # 快速入口
  pyproject.toml        # PyPI/可编辑安装配置
  label.png             # 软件图标
```

## Python 包目录

```text
labpilot_ai/labpilot_ai/
  app/                  # PyQt 主窗口、主题、页面
  ai/                   # LLM client、prompt、schema、错误建议
  analysis/             # 绘图、拟合、报告生成
  blacs_ctrl/           # BLACS manual bridge client/server
  config/               # settings manager
  lyse_ctrl/            # H5 加载、single/multi runner、结果 store
  optimizer/            # grid/Bayesian 优化器和 history
  protocol/             # protocol suggestion 存储
  runmanager_ctrl/      # runmanager backend、scan builder
  safety/               # validator 和 audit log
  storage/              # SQLite 项目状态
  utils/                # 通用路径和 JSON 工具
  voice/                # 录音、STT、CUDA DLL、唤醒、术语
```

## 配置目录

```text
configs/
  project_settings.yaml         # 项目路径、AI、语音默认配置
  global_registry.yaml          # runmanager globals 白名单
  blacs_manual_registry.yaml    # BLACS manual 通道白名单
  lyse_registry.yaml            # single/multi 模块声明
  safety_rules.yaml             # 全局安全规则
  voice_lexicon.yaml            # 语音术语和纠错词表
```

## 重要入口

- 命令行入口：`labpilot_ai.main:main`
- 模块启动：`python -m labpilot_ai`
- 主窗口：`labpilot_ai/app/main_window.py`
- 主题：`labpilot_ai/app/theme.py`
- STT worker：`labpilot_ai/voice/stt_worker.py`
