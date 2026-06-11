from __future__ import annotations

import argparse
import configparser
import shutil
import sys
from pathlib import Path


def _find_blacs_plugins_dir() -> Path:
    import blacs.plugins

    return Path(blacs.plugins.PLUGINS_DIR)


def _labconfig_path() -> Path:
    from labscript_utils.labconfig import LabConfig

    cfg = LabConfig()
    path = getattr(cfg, "config_path", None)
    if not path:
        raise RuntimeError("Could not determine labconfig path from LabConfig().config_path")
    return Path(path)


def install_plugin_shim(overwrite: bool = True) -> Path:
    plugins_dir = _find_blacs_plugins_dir()
    target_dir = plugins_dir / "labpilot_bridge"
    target_dir.mkdir(parents=True, exist_ok=True)
    init_file = target_dir / "__init__.py"
    if init_file.exists() and not overwrite:
        return init_file
    init_file.write_text(
        "from labpilot_ai.blacs_bridge.plugin import Plugin, name, module\n",
        encoding="utf-8",
    )
    return init_file


def enable_labconfig(*, allow_write: bool | None = None, host: str | None = None, port: int | None = None, token: str | None = None) -> Path:
    path = _labconfig_path()
    parser = configparser.ConfigParser()
    parser.optionxform = str
    parser.read(path, encoding="utf-8")
    if not parser.has_section("BLACS/plugins"):
        parser.add_section("BLACS/plugins")
    parser.set("BLACS/plugins", "labpilot_bridge", "True")
    if allow_write is not None:
        parser.set("BLACS/plugins", "labpilot_bridge.allow_write", "True" if allow_write else "False")
    if host:
        parser.set("BLACS/plugins", "labpilot_bridge.host", host)
    if port:
        parser.set("BLACS/plugins", "labpilot_bridge.port", str(int(port)))
    if token:
        parser.set("BLACS/plugins", "labpilot_bridge.token", token)
    backup = path.with_suffix(path.suffix + ".labpilot_bridge.bak")
    shutil.copy2(path, backup)
    with path.open("w", encoding="utf-8") as f:
        parser.write(f)
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="Install LabPilot real BLACS bridge plugin shim into the active labscript environment.")
    ap.add_argument("--allow-write", action="store_true", help="Enable real BLACS manual writes in labconfig. Use only after /channels and /values are verified.")
    ap.add_argument("--disable-write", action="store_true", help="Explicitly disable real BLACS manual writes in labconfig.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--token", default=None, help="Optional token required by LabPilot client via X-LabPilot-Token.")
    args = ap.parse_args()

    shim = install_plugin_shim()
    allow_write = True if args.allow_write else False if args.disable_write else None
    cfg = enable_labconfig(allow_write=allow_write, host=args.host, port=args.port, token=args.token)

    print("Installed BLACS plugin shim:", shim)
    print("Updated labconfig:", cfg)
    print("Next steps:")
    print("  1. Stop any placeholder manual_bridge_server using port", args.port)
    print("  2. Restart BLACS")
    print(f"  3. Test: curl.exe http://{args.host}:{args.port}/status")
    print("  4. Expected service: labpilot-real-blacs-bridge")
    print("  5. Then test /channels and /values before enabling writes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
