# BLACS bridge

Use the installed site gateway and `labpilot-control` for reviewed same-machine control. The legacy `labpilot_ai.blacs_bridge.plugin.Plugin` runs inside BLACS and provides local front-panel readback through IPv4 loopback. [BLACS local setup](../../manual/03_blacs/real_blacs_bridge.md)

For legacy readback, use the Labscript environment from the repository directory and install with `python tools/install_real_blacs_bridge.py --disable-write`. After a normal BLACS restart, inspect `http://127.0.0.1:8765/status`. The read-only plugin reports service `labpilot-real-blacs-bridge` and `allow_write: false`. Configure the same site token in the BLACS and client environments (`LABPILOT_BLACS_TOKEN`) and send it in a single `X-LabPilot-Token` header. An absent server token, absent header or wrong token returns 401. HTTP writes are always forbidden. Use managed `labpilot` tasks for actual changes. The in-memory simulation reports service `labpilot-blacs-manual-bridge`.
