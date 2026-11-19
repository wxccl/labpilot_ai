"""Create and verify a profile-bound Windows desktop shortcut."""
import argparse
import os
from pathlib import Path
import subprocess
import sys


def create(profile):
    if os.name != "nt":
        raise OSError("Desktop shortcut creation requires Windows.")
    profile = Path(profile).resolve(strict=True)
    launcher = Path(sys.executable).with_name("pythonw.exe")
    icon = Path(__file__).with_name("labpilot.ico")
    if not profile.is_file() or not launcher.is_file() or not icon.is_file():
        raise ValueError("Missing profile, pythonw.exe, or application icon.")
    args = subprocess.list2cmdline(["-m", "labpilot_ai.automation_cli", "--profile", str(profile), "ui"])
    script = """
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$shell = New-Object -ComObject WScript.Shell
$path = Join-Path ($shell.SpecialFolders.Item('Desktop')) 'LabPilot Workflow.lnk'
$link = $shell.CreateShortcut($path)
$link.TargetPath = $env:LABPILOT_LINK_TARGET
$link.Arguments = $env:LABPILOT_LINK_ARGS
$link.WorkingDirectory = $env:LABPILOT_LINK_DIR
$link.IconLocation = $env:LABPILOT_LINK_ICON
$link.Save()
$check = $shell.CreateShortcut($path)
if ($check.TargetPath -ne $env:LABPILOT_LINK_TARGET -or $check.Arguments -ne $env:LABPILOT_LINK_ARGS) { throw 'Shortcut verification failed' }
Write-Output $path
"""
    env = dict(os.environ, LABPILOT_LINK_TARGET=str(launcher), LABPILOT_LINK_ARGS=args,
               LABPILOT_LINK_DIR=str(profile.parent), LABPILOT_LINK_ICON=str(icon))
    completed = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                               capture_output=True, encoding="utf8", errors="replace", env=env,
                               timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip())
    return Path(completed.stdout.strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    print(create(parser.parse_args().profile))
