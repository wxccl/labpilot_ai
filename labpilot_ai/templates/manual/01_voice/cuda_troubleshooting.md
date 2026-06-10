# CUDA 排障：cublas64_12.dll / cuDNN / CTranslate2

这个问题已经在当前代码中修复，但新电脑配置 GPU STT 时仍可能遇到。

## 典型错误

```text
Library cublas64_12.dll is not found or cannot be loaded
```

或者：

```text
CUDA runtime was requested but the required CUDA/cuDNN/cuBLAS libraries were not found.
```

## 本机已验证的解决方案

本机存在 CUDA Toolkit DLL：

```powershell
dir "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6\bin\cublas64_12.dll"
```

但仅有 DLL 文件还不够，关键是 Python 子进程的 DLL 搜索路径必须能找到这些目录。

当前代码新增：

```text
labpilot_ai/voice/cuda_paths.py
```

它会自动发现并注册：

```text
C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v*\bin
<env>\Lib\site-packages\nvidia\cublas\bin
<env>\Lib\site-packages\nvidia\cudnn\bin
<env>\Lib\site-packages\nvidia\cuda_nvrtc\bin
<env>\Lib\site-packages\ctranslate2
```

## 推荐检查步骤

1. 确认正在使用 labscript 环境：

```powershell
conda activate labscript
python -c "import sys; print(sys.executable)"
```

2. 安装或更新 NVIDIA wheel：

```powershell
pip install -U nvidia-cublas-cu12 nvidia-cudnn-cu12
```

3. 检查 Python 环境中 DLL：

```powershell
python -c "import sys,pathlib; [print(p) for root in map(pathlib.Path, sys.path) for p in root.glob('**/cublas64_12.dll')]"
python -c "import sys,pathlib; [print(p) for root in map(pathlib.Path, sys.path) for p in root.glob('**/cudnn64_9.dll')]"
```

4. 测试 LabPilot 自动 DLL 注册：

```powershell
cd E:\Labpilot\labpilot_ai
python -c "from labpilot_ai.voice.cuda_paths import register_cuda_dll_dirs; print([str(p) for p in register_cuda_dll_dirs()[:10]])"
```

5. 测试 GPU 模型加载：

```powershell
python -c "from labpilot_ai.voice.cuda_paths import register_cuda_dll_dirs; register_cuda_dll_dirs(); from faster_whisper import WhisperModel; WhisperModel('small', device='cuda', compute_type='float16'); print('GPU model load OK')"
```

## 如果仍失败

优先检查：

- LabPilot 是否从同一个 conda 环境启动。
- `faster-whisper` 和 `ctranslate2` 是否安装在当前环境。
- `nvidia-cublas-cu12` 与 `nvidia-cudnn-cu12` 是否装在当前环境。
- `PATH` 中是否包含 CUDA Toolkit 的 `bin`。
- 是否有多个 Python 或多个 conda 环境混用。

实验现场如果暂时无法解决，先切回 CPU 模式：

```yaml
voice:
  device: "cpu"
  compute_type: "int8"
```

CPU 模式不会尝试加载 CUDA。
