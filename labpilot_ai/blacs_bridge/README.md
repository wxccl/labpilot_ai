# LabPilot AI Real BLACS Bridge

This folder contains the BLACS-side bridge plugin.

Important distinction:

- `labpilot_ai.blacs_ctrl.manual_bridge_server` is a placeholder localhost bridge. It only stores values in memory. It does **not** control real BLACS hardware.
- `labpilot_ai.blacs_bridge.plugin.Plugin` is intended to run inside the BLACS process. It can expose `/status`, `/debug`, `/channels`, and `/values` from the live BLACS object.

## Test placeholder bridge

```powershell
conda activate labscript
cd E:\Labpilot\labpilot_ai
python -m labpilot_ai.blacs_ctrl.manual_bridge_server --host 127.0.0.1 --port 8765
```

Then:

```powershell
curl.exe http://127.0.0.1:8765/status
```

If service is `labpilot-blacs-manual-bridge`, this is only the placeholder bridge.

## Real BLACS bridge workflow

1. Install LabPilot AI in the same conda environment used to launch BLACS:

```powershell
conda activate labscript
cd E:\Labpilot\labpilot_ai
python -m pip install -e .
```

2. Configure BLACS to load `labpilot_ai.blacs_bridge.plugin.Plugin` as a BLACS plugin.
   The exact plugin registration location depends on your labscript-suite/BLACS version and labconfig.
   Use BLACS' connection table plugin as a reference.

3. Start BLACS.

4. Test:

```powershell
curl.exe http://127.0.0.1:8765/status
curl.exe http://127.0.0.1:8765/debug
curl.exe http://127.0.0.1:8765/channels
curl.exe http://127.0.0.1:8765/values
```

If `/status` returns service `labpilot-real-blacs-bridge`, LabPilot AI has reached the real BLACS-side plugin.

## Writes are disabled by default

To enable experimental generic Qt widget writes, set before starting BLACS:

```powershell
$env:LABPILOT_BLACS_ALLOW_WRITE="1"
```

Use this only with a low-risk dummy channel first. Generic Qt setters may change a GUI value but may not program real hardware depending on the BLACS tab/device implementation.
