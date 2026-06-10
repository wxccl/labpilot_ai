# CPU/GPU STT

LabPilot AI 使用 faster-whisper 做语音转文字。为了避免主 UI 被依赖库崩溃影响，默认在独立 Python 子进程中运行 STT。

## CPU 模式

CPU 模式最稳，适合所有电脑：

```yaml
voice:
  device: "cpu"
  compute_type: "int8"
  isolated_stt: true
```

CPU worker 会设置：

```text
CUDA_VISIBLE_DEVICES=-1
PYTHONIOENCODING=utf-8
PYTHONUTF8=1
KMP_DUPLICATE_LIB_OK=TRUE
OMP_NUM_THREADS=1
```

`int8` 可以降低内存和 CPU 负载。模型建议：

- fast：`tiny` 或 `base`
- balanced：`small`
- accurate：`medium` + `int8`

## GPU 模式

RTX 3090 可以显著加速 faster-whisper：

```yaml
voice:
  device: "cuda"
  gpu_compute_type: "float16"
```

UI 中可以选择 `GPU RTX/CUDA` 后端。GPU 模式通常使用：

```text
device=cuda
compute_type=float16
model_size=small 或 medium
```

## 什么时候用 CPU

- 只是短命令控制。
- GPU DLL 环境还没配好。
- 实验现场优先稳定。
- 电脑没有 NVIDIA GPU。

## 什么时候用 GPU

- 需要转写较长音频。
- 使用 `medium` 或更大模型。
- 已确认 `WhisperModel(... device='cuda')` 能加载。
- Diagnostics 中 CUDA/cuDNN/cuBLAS 都正常。

## 中文英文混合

默认语言设置为：

```yaml
language: "zh,en"
```

这适合类似下面的命令：

```text
labscript 把 duration_tof_ms 改成 17，然后跑 Rabi scan
```

转写后会进入术语纠错模块，把常见误识别修正成 registry 里的真实变量名或实验术语。
