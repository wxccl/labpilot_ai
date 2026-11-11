"""Structured local control for operators and Codex."""
import argparse
import json
from pathlib import Path
import sys

from .transport import LocalGateway, MAX_BYTES, load_json


def read_file(path):
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("JSON file too large")
    return load_json(raw.decode("utf-8-sig"))


def save_plan(path, target, request):
    with path.open("x", encoding="utf-8") as stream:
        json.dump({"target": target, "request": request}, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    return {"state": "PREPARED", "path": str(path), "request": request}


def parser():
    cli = argparse.ArgumentParser(prog="labpilot-control", description=__doc__)
    commands = cli.add_subparsers(dest="command", required=True)
    for action in ("discover", "queue", "globals", "metadata"):
        commands.add_parser(action, help=f"Read {action} from the local runtime")
    snapshot = commands.add_parser("snapshot")
    snapshot.add_argument("device")
    manual = commands.add_parser("prepare-manual", help="Prepare one BLACS channel change")
    manual.add_argument("device")
    manual.add_argument("channel")
    manual.add_argument("value", type=load_json, help="JSON value in the device base unit")
    manual.add_argument("--subchannel")
    manual.add_argument("--approver", required=True)
    manual.add_argument("--instruction", required=True)
    manual.add_argument("--output", type=Path, required=True)
    globals_plan = commands.add_parser("prepare-globals", help="Prepare a change to active globals")
    globals_plan.add_argument("values", type=Path, help="JSON object of names and typed values")
    globals_plan.add_argument("--output", type=Path, required=True)
    sequence = commands.add_parser("prepare-sequence", help="Prepare a change to the active sequence")
    sequence.add_argument("path", type=Path)
    sequence.add_argument("--output", type=Path, required=True)
    output = commands.add_parser("prepare-output", help="Prepare a change to the shot output folder")
    output.add_argument("path", type=Path)
    output.add_argument("--output", type=Path, required=True)
    engage = commands.add_parser("prepare-engage", help="Bind Engage to the current configuration")
    engage.add_argument("--shots", type=int, required=True)
    engage.add_argument("--output", type=Path, required=True)
    apply = commands.add_parser("apply", help="Submit one previously reviewed plan")
    apply.add_argument("plan", type=Path)
    return cli


def dispatch(args, gateway):
    from labpilot_ai.blacs_ctrl.local_gateway import LocalBlacs
    from labpilot_ai.runmanager_ctrl.local_gateway import LocalRunmanager

    blacs = LocalBlacs(gateway)
    runmanager = LocalRunmanager(gateway)
    command = args.command
    if command == "discover":
        return blacs.discover()
    if command == "queue":
        return blacs.queue_status()
    if command == "snapshot":
        return blacs.snapshot(args.device)
    if command == "globals":
        return runmanager.read_all()
    if command == "metadata":
        return gateway.call("runmanager", {"schema": "runmanager-metadata-read-request/1", "action": "snapshot"})
    if command == "prepare-manual":
        snapshot = blacs.snapshot(args.device)
        request = blacs.prepare_manual(snapshot, args.channel, args.value, subchannel=args.subchannel,
                                       approver=args.approver, instruction=args.instruction)
        return save_plan(args.output, "blacs", request)
    if command == "prepare-globals":
        return save_plan(args.output, "runmanager", runmanager.prepare_globals(read_file(args.values)))
    if command == "prepare-sequence":
        path = args.path.expanduser().resolve(strict=True)
        if not path.is_file() or path.suffix.lower() != ".py":
            raise ValueError("Select an existing sequence .py file")
        return save_plan(args.output, "runmanager", runmanager.prepare("set_sequence", {"sequence": str(path)}))
    if command == "prepare-output":
        path = args.path.expanduser().resolve(strict=True)
        if not path.is_dir():
            raise ValueError("Select an existing shot output directory")
        return save_plan(args.output, "runmanager", runmanager.prepare("set_output", {"output": str(path)}))
    if command == "prepare-engage":
        request = runmanager.prepare("engage_once", expected_n_shots=args.shots)
        return save_plan(args.output, "runmanager", request)
    envelope = read_file(args.plan)
    if not isinstance(envelope, dict) or set(envelope) != {"target", "request"} or not isinstance(envelope["request"], dict):
        raise ValueError("Expected a LabPilot plan with target and request")
    if envelope["target"] == "blacs":
        return blacs.apply_manual(envelope["request"])
    if envelope["target"] == "runmanager":
        return runmanager.execute(envelope["request"])
    raise ValueError("Unknown plan target")


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = dispatch(args, LocalGateway.from_env())
    except (KeyError, OSError, RuntimeError, ValueError) as exc:
        receipt = getattr(exc, "receipt", None)
        if receipt is not None:
            print(json.dumps(receipt, ensure_ascii=True, indent=2, allow_nan=False))
        print(f"labpilot-control: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False))
    state = result.get("state", "")
    return 2 if state.startswith(("REFUSED", "UNKNOWN", "FAILED", "REJECTED")) else 0


if __name__ == "__main__":
    raise SystemExit(main())
