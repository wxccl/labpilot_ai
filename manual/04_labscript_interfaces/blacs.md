# BLACS Manual interface

LabPilot AI talks to BLACS through a localhost bridge boundary. It does not patch BLACS internals and it does not bypass the LabPilot safety layer.

## v0.1.3 bridge scope

The first real BLACS bridge target is controlled manual write/readback through the LabPilot bridge:

- `GET /status`
- `GET /channels`
- `GET /values`
- `POST /set_manual`

The UI exposes:

- `Test BLACS bridge`
- `Read current values`
- `AI parse usable actions`
- `Index H5/BLACS to Knowledge`
- `Program hardware on write`

`AI parse usable actions` reads the active `connection_table.py` without executing it and imports manual AO/DO/static channels into the local BLACS registry. Editing the `target value` cell writes immediately through the BLACS bridge after local type/range validation; empty target cells are ignored.

## Registry example

```yaml
mot_coil_current:
  device: "coil_driver"
  channel: "ao0"
  kind: "manual"
  type: float
  unit: A
  min: 0
  max: 20
  risk: high
  require_confirm: true
  ai_control: false
  description: MOT coil current manual control.
```

## Safety workflow

```text
Natural-language command or UI edit
  -> JSON action with type="set_blacs_manual"
  -> SafetyValidator whitelist/type/range check
  -> table edits write immediately; natural-language commands still use Parse/Execute review
  -> manual_client
  -> localhost BLACS bridge
```

## Important first-release limit

Readonly bridge discovery is the recommended first lab validation step. Real manual writes should only be enabled after the lab-side BLACS bridge/plugin has been reviewed, tested in mock mode, and staged on one low-risk channel. High-power lasers, magnetic coils, power supplies, shutters, and DDS outputs should remain high-risk and confirmation-gated.

## Related code

- `labpilot_ai/blacs_ctrl/manual_client.py`
- `labpilot_ai/blacs_ctrl/manual_bridge_server.py`
- `configs/blacs_manual_registry.yaml`
- `labpilot_ai/safety/validator.py`
