"""Report capabilities advertised by the selected host without requesting any effect."""


def capability_report(response, requirements=()):
    value = response.get("value", {})
    targets = value.get("targets", {}) if response.get("state") == "OBSERVED" else {}
    available_actions = set()
    for target, info in targets.items():
        if info.get("available") is True:
            available_actions.update(f"{target}.{name}" for name in info.get("actions", ()))
    blacs = targets.get("blacs", {})
    devices = []
    for name in sorted(blacs.get("devices", ())):
        info = blacs.get("device_capabilities", {}).get(name, {})
        devices.append({"device": name, "family": info.get("family", "unknown"),
                        "manual_healthy": info.get("manual_healthy"),
                        "read_actions": info.get("read_actions", []),
                        "write_actions": info.get("write_actions", []),
                        "configured_channels": blacs.get("write_channels", {}).get(name, [])})
    missing = sorted(set(requirements) - available_actions)
    return {"schema": "labpilot-preflight/1",
            "state": "REFUSED" if missing or not any(t.get("available") is True for t in targets.values()) else "OBSERVED",
            "adapter": "packaged_host", "simulated": value.get("simulated"),
            "targets": {name: {"available": info.get("available") is True, "reason": info.get("reason")}
                        for name, info in targets.items()},
            "reason": response.get("reason"), "advertised_actions": sorted(available_actions),
            "missing_required_actions": missing, "devices": devices,
            "managed_batches": targets.get("runmanager", {}).get("managed_batches"),
            "hardware_verified": False}
