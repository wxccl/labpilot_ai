# 语音术语与纠错

实验语音里经常有变量名、缩写、英文实验名和代码术语。普通 STT 容易把它们转错，所以 LabPilot AI 增加了术语纠错层。

## 术语来源

术语表来自：

- `configs/voice_lexicon.yaml`
- `configs/global_registry.yaml` 中的变量名和 aliases
- `configs/blacs_manual_registry.yaml` 中的通道名和 aliases
- `configs/lyse_registry.yaml` 中的结果字段和 aliases

## 例子

如果用户说：

```text
run manger set to f
```

术语层可以把 `run manger` 修正为 `runmanager`，并根据上下文补全常见实验词，如 `TOF`。

## 推荐写法

在 registry 中给每个重要变量写：

```yaml
duration_tof_ms:
  type: float
  unit: ms
  aliases:
    - TOF
    - time of flight
  description: Time of flight duration.
```

这样语音、AI prompt 和 UI tooltip 都能复用同一份语义信息。

## 相关代码

- `voice/lexicon.py`：加载 registry 并执行模糊纠错。
- `configs/voice_lexicon.yaml`：人工补充术语。
- `tests/test_voice.py`：术语纠错测试。
