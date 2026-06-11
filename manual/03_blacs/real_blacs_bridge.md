# LabPilot AI Real BLACS Bridge

This patch adds a real BLACS plugin bridge. The old `manual_bridge_server` is only a placeholder HTTP server and does not control BLACS. The new bridge must be loaded by the running BLACS process.

## Install into the labscript environment

```powershell
conda activate labscript
cd E:\Labpilot\labpilot_ai
python -m pip install -e .
python tools\install_real_blacs_bridge.py --disable-write
```

Then restart BLACS.

## Verify that BLACS loaded the real plugin

Stop any placeholder server using port 8765, then start BLACS and run:

```powershell
curl.exe http://127.0.0.1:8765/status
```

Expected:

```json
{
  "ok": true,
  "service": "labpilot-real-blacs-bridge",
  "has_blacs": true
}
```

If the service is `labpilot-blacs-manual-bridge`, you are still connected to the placeholder server, not real BLACS.

## Read channels and values

```powershell
curl.exe http://127.0.0.1:8765/channels
curl.exe http://127.0.0.1:8765/values
python tools\check_real_blacs_bridge.py
```

## Enable writes only after readback works

Writes are disabled by default. Enable them only after checking `/channels` and `/values`:

```powershell
python tools\install_real_blacs_bridge.py --allow-write
```

Restart BLACS, then test a low-risk channel only:

```powershell
$body = '{"name":"DeviceName.ao0","value":0.01,"program":true}'
Invoke-WebRequest -Uri http://127.0.0.1:8765/set_manual -Method POST -ContentType "application/json" -Body $body
```

The write path uses the BLACS DeviceTab front-panel object and `program_device()`/`program_manual` state-machine path; it does not bypass BLACS worker processes.

## Safety notes

- First test with a dummy output or low-risk AO/DO.
- Keep `require_confirm: true` and min/max ranges in `configs/blacs_manual_registry.yaml`.
- Do not enable writes for microwave, high-power light, coils, shutters, or DDS gates before verifying a safe low-risk channel.
- If BLACS is in buffered/running mode, the bridge refuses manual writes.
