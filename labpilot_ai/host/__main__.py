"""Run one packaged host request under the existing Labscript interpreter."""

import argparse
from pathlib import Path
import sys


if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from labpilot_ai.host.adapters import Runmanager, Simulator
from labpilot_ai.host.blacs import Blacs
from labpilot_ai.host.protocol import MAX_BYTES, Journal, Profile, Refused, canonical, loads, receipt, request_id


PREFIX = "LABPILOT_HOST_JSON:"


def dispatch(envelope, profile):
    if type(envelope) is not dict or set(envelope) != {"method", "params"} or type(envelope["params"]) is not dict:
        raise Refused("Expected an object with method and params")
    method, params = envelope["method"], envelope["params"]
    journal = Journal(profile.state_db, simulate=profile.simulate)
    adapters = {"runmanager": Runmanager(profile), "blacs": Blacs(profile)}
    if profile.simulate:
        adapters = {name: Simulator(name, journal) for name in adapters}
    if method == "discover":
        targets = {}
        for name, adapter in adapters.items():
            try:
                targets[name] = adapter.discover()
            except Exception as exc:
                targets[name] = {"available": False, "actions": [], "reason": str(exc)}
        return receipt("OBSERVED", value={"targets": targets, "simulated": profile.simulate})
    target = params.get("target")
    if type(target) is not str or target not in adapters:
        raise Refused("Select the runmanager or blacs target")
    if method == "snapshot":
        return receipt("OBSERVED", value=adapters[target].snapshot(params))
    if method == "observe":
        key = request_id(params)
        observed = journal.observe(key, target)
        if observed is None:
            return receipt("UNKNOWN", request_id=key, reason="No host receipt for the requested operation")
        return receipt("OBSERVED", request_id=key, value={"receipt": observed,
                       "evidence": observed.get("value", {}).get("evidence", {})})
    if method != "execute":
        raise Refused("Unknown host method")
    key = request_id(params)
    if type(params.get("action")) is not str:
        raise Refused("A concrete action is required")
    prior = journal.reserve(key, target, params)
    if prior is not None:
        return prior
    try:
        with journal.exclusive_effect():
            value = adapters[target].execute(params)
        result = receipt("APPLIED", value=value, request_id=key)
    except Refused as exc:
        result = receipt("REFUSED", reason=str(exc), request_id=key)
    except Exception as exc:
        result = receipt("UNKNOWN", reason=f"{type(exc).__name__}: {exc}", request_id=key)
    try:
        journal.store(key, result)
    except Exception:
        return receipt("UNKNOWN", request_id=key, reason="Host could not persist the outcome of the original request")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("serve", "doctor", "install", "uninstall"), default="serve")
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--expect-profile-sha256")
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--labconfig", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        profile = Profile(args.profile, simulate=args.simulate, expected_sha256=args.expect_profile_sha256)
        if args.command == "serve":
            raw = sys.stdin.buffer.read(MAX_BYTES + 1)
            result = dispatch(loads(raw.decode("utf-8-sig")), profile)
        else:
            from labpilot_ai.host.install import configure, doctor

            value = (doctor(profile, args.labconfig) if args.command == "doctor" else
                     configure(profile, args.labconfig, apply=args.apply, uninstall=args.command == "uninstall"))
            result = receipt("OBSERVED", value=value)
    except (Refused, ValueError, TypeError, KeyError, RecursionError) as exc:
        result = receipt("REFUSED", reason=str(exc))
    except Exception as exc:
        result = receipt("UNKNOWN", reason=f"{type(exc).__name__}: {exc}")
    print(PREFIX + canonical(result), flush=True)
    return 0 if args.command == "serve" or result["state"] == "OBSERVED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
