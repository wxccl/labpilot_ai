"""Inspect the existing Labscript interpreter and install an optional BLACS shim."""

import configparser
from importlib import metadata, util
import os
from pathlib import Path
import re
import sys
import uuid

from .protocol import Refused


SHIM = b"from labpilot_ai.host.blacs_plugin import Plugin, module, name\n"
BEGIN = "# BEGIN LABPILOT HOST MANAGED BLOCK"
END = "# END LABPILOT HOST MANAGED BLOCK"
ADDED_SEPARATOR = "# LABPILOT HOST ADDED PRECEDING LINE BREAK"
SECTION = "BLACS/plugins"


def _shim_path():
    spec = util.find_spec("blacs")
    paths = getattr(spec, "submodule_search_locations", None)
    if not paths or len(paths) != 1:
        return None
    return Path(paths[0]) / "plugins" / "labpilot_host" / "__init__.py"


def _profile_text(path):
    text = str(path)
    if any(char in text for char in "\r\n%"):
        raise Refused("Choose a profile path that LabConfig can represent without interpolation")
    return text


def _config(path):
    if path is None or not path.is_file():
        raise Refused("Pass the existing site LabConfig file with --labconfig")
    content = path.read_bytes()
    text = content.decode("utf-8-sig")
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(text)
    return content, text, parser


def _atomic(path, data):
    stage = path.with_name(f".{path.name}.{uuid.uuid4().hex}.labpilot-tmp")
    try:
        with stage.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(stage, path)
    finally:
        stage.unlink(missing_ok=True)


def _version(name):
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def doctor(profile, labconfig=None):
    shim = _shim_path()
    found = {name: _version(name) for name in ("labscript", "labscript-utils", "runmanager", "blacs", "lyse")}
    result = {"python": sys.executable, "packages": found, "profile": str(profile.path or ""),
              "simulated": profile.simulate, "runmanager_enabled": bool(profile.runmanager.get("enabled")),
              "blacs_enabled": bool(profile.blacs.get("enabled")), "shim_path": str(shim or ""),
              "shim_present": bool(shim and shim.is_file()), "labconfig": str(labconfig or ""),
              "checks": "Installed package metadata and files; no hardware commands or restart"}
    if labconfig is not None:
        _, _, parsed = _config(labconfig)
        result["labconfig_blacs_plugin_enabled"] = parsed.getboolean(SECTION, "labpilot_host", fallback=False)
    return result


def configure(profile, labconfig, *, apply=False, uninstall=False):
    if profile.path is None or profile.simulate or (not uninstall and not profile.blacs.get("enabled")):
        raise Refused("Supply a native profile with BLACS enabled when installing")
    shim = _shim_path()
    if shim is None or not shim.parent.parent.is_dir():
        raise Refused("No BLACS plugins directory in this interpreter")
    if shim.exists() and shim.read_bytes() != SHIM:
        raise Refused("An unrelated file occupies the LabPilot BLACS shim path")
    original, text, parsed = _config(labconfig)
    newline = "\r\n" if "\r\n" in text else "\n"
    block = re.compile(r"(?m)^" + re.escape(BEGIN) + r"\r?\n.*?^" + re.escape(END) + r"(?:\r?\n|$)", re.S)
    matches = list(block.finditer(text))
    if len(matches) > 1 or (BEGIN in text and not matches) or (END in text and not matches):
        raise Refused("LabPilot configuration markers are ambiguous or damaged")
    if uninstall:
        if not matches:
            raise Refused("No managed LabPilot configuration block exists")
        match = matches[0]
        start = match.start()
        if ADDED_SEPARATOR in match.group() and text[:start].endswith(newline):
            start -= len(newline)
        updated = text[:start] + text[match.end():]
    else:
        options = newline.join((BEGIN, "labpilot_host = True", f"labpilot_host.profile = {_profile_text(profile.path)}", END, ""))
        if matches:
            managed = matches[0].group().replace(f"[{SECTION}]{newline}", "").replace(ADDED_SEPARATOR + newline, "")
            if managed != options:
                raise Refused("Uninstall the existing LabPilot profile before switching profiles")
            updated = text
        elif parsed.has_option(SECTION, "labpilot_host") or parsed.has_option(SECTION, "labpilot_host.profile"):
            raise Refused("Existing unmanaged LabPilot Host configuration needs manual review")
        elif parsed.has_section(SECTION):
            heading = re.search(r"(?m)^\s*\[BLACS/plugins\][^\n]*\n", text)
            if heading is None:
                raise Refused("Could not safely locate the BLACS/plugins section")
            updated = text[:heading.end()] + options + text[heading.end():]
        else:
            prefix = "" if not text or text.endswith(newline) else newline
            managed_options = [BEGIN, f"[{SECTION}]", "labpilot_host = True",
                               f"labpilot_host.profile = {_profile_text(profile.path)}", END, ""]
            if prefix:
                managed_options.insert(1, ADDED_SEPARATOR)
            updated = text + prefix + newline.join(managed_options)
    verified = configparser.ConfigParser(interpolation=None)
    verified.read_string(updated)
    encoding = "utf-8-sig" if original.startswith(b"\xef\xbb\xbf") else "utf-8"
    changed = updated.encode(encoding) != original
    if apply:
        if labconfig.read_bytes() != original:
            raise Refused("LabConfig changed during installation preparation")
        if uninstall:
            if changed:
                _atomic(labconfig, updated.encode(encoding))
            shim.unlink(missing_ok=True)
        else:
            created = not shim.exists()
            shim.parent.mkdir(exist_ok=True)
            if created:
                with shim.open("xb") as stream:
                    stream.write(SHIM)
            try:
                if changed:
                    _atomic(labconfig, updated.encode(encoding))
            except OSError:
                if created:
                    shim.unlink(missing_ok=True)
                raise
    return {"operation": "uninstall" if uninstall else "install", "applied": apply,
            "shim": str(shim), "labconfig": str(labconfig), "changes_labconfig": changed,
            "normal_blacs_restart_required": True}
