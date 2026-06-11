"""Real BLACS bridge support for LabPilot AI.

This package is intended to be imported from inside the running BLACS process
as a BLACS plugin. It exposes a localhost HTTP API consumed by
labpilot_ai.blacs_ctrl.manual_client.BlacsManualClient.
"""

from .plugin import Plugin, name, module

__all__ = ["Plugin", "name", "module"]
