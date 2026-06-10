def advise_error(error_text: str) -> str:
    text = (error_text or "").strip()
    low = text.lower()
    hints = []

    if any(token in low for token in ["unicode", "utf-8", "codec", "mojibake", "encoding", "decode error", "�"]):
        hints.append("Check source/document encoding. Save Python and Markdown files as UTF-8, then rerun compileall before release.")
    if any(token in text for token in ["乱码", "鏄", "涓", "鎵", "寮"]):
        hints.append("This looks like mojibake. Reopen the affected file as UTF-8, replace corrupted strings, and avoid mixed terminal encodings.")
    if "not in global whitelist" in low or "global" in low and "whitelist" in low:
        hints.append("Add the variable to configs/global_registry.yaml with type, range, risk, aliases, and description.")
    if "importerror" in low or "modulenotfounderror" in low or "no module named" in low:
        hints.append("Install the missing optional dependency, or disable the related feature in Settings before continuing.")
    if "blacs" in low and ("connection" in low or "refused" in low or "bridge" in low or "localhost" in low):
        hints.append("Check the BLACS localhost bridge, the registered channel name, and Mock BLACS mode before programming hardware.")
    if "runmanager" in low and ("connection" in low or "timeout" in low or "remote" in low):
        hints.append("Check that runmanager is running, remote access is available, and the timeout is long enough.")
    if "h5py has already been imported" in low or "h5_lock" in low:
        hints.append("Restart Python and ensure labpilot_ai.bootstrap_labscript.install_h5_lock() runs before importing h5py.")
    if "cublas" in low or "cudnn" in low or "cuda runtime" in low:
        hints.append("For GPU STT, run Diagnostics and verify CUDA/cuBLAS/cuDNN DLL paths; switch to CPU/int8 if the DLL stack is unstable.")
    if "openmp" in low or "libiomp5md" in low or "omp: error" in low:
        hints.append("Keep STT in isolated_release mode or CPU/int8 mode to isolate OpenMP runtime conflicts.")
    if "pypdf" in low or "pdf import requires" in low or "pdf indexing requires" in low:
        hints.append("Install PDF support with pip install -e .[docs] or pip install pypdf.")
    if "module" in low and ("not registered" in low or "no module" in low or "path does not exist" in low):
        hints.append("Register the single/multi analysis module in configs/lyse_registry.yaml and verify the module path.")
    if "objective" in low and ("missing" in low or "unsafe" in low or "variable" in low):
        hints.append("Choose an objective from lyse results or use a safe expression over registered result fields.")
    if "scipy" in low or "curve_fit" in low:
        hints.append("Install scipy fitting dependencies with pip install -e .[fit], or choose a simpler fit model.")
    if "h5" in low and ("timeout" in low or "folder" in low or "not found" in low):
        hints.append("Verify the H5 output folder, shot naming rule, and whether the experiment actually produced a new H5 file.")
    if "knowledge" in low or "fts" in low or "sqlite" in low:
        hints.append("Rebuild the Knowledge index and confirm the configured source folders are readable.")

    if not hints:
        hints.append("Check the traceback, then reproduce in Dry run or Mock mode before touching hardware.")
    return "\n".join(f"- {hint}" for hint in hints)
