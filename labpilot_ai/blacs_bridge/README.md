# BLACS bridge

Use the installed site gateway and `labpilot-control` for reviewed same-machine control. The legacy `labpilot_ai.blacs_bridge.plugin.Plugin` runs inside BLACS and provides local front-panel readback through IPv4 loopback. [BLACS local setup](../../manual/03_blacs/real_blacs_bridge.md)

For legacy readback, use the Labscript environment from the repository directory and install with `python tools/install_real_blacs_bridge.py --disable-write`. After a normal BLACS restart, inspect `http://127.0.0.1:8765/status`. The read-only plugin reports service `labpilot-real-blacs-bridge` and `allow_write: false`. If the site has configured a token, send it in a single `X-LabPilot-Token` header. The in-memory simulation reports service `labpilot-blacs-manual-bridge`.
