"""CLI, background runner, and agent entry points for LabPilot."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time

from .automation import Automation, default_profile
from .local_control.transport import load_json


def parser():
    cli = argparse.ArgumentParser(prog="labpilot")
    cli.add_argument("--profile", default=default_profile(), help="JSON site profile")
    commands = cli.add_subparsers(dest="command", required=True)
    for name in ("init", "discover", "list", "run-next", "ui"):
        commands.add_parser(name)
    doctor = commands.add_parser("doctor")
    doctor.add_argument("--labconfig", type=Path)
    for name in ("install-host", "uninstall-host"):
        install = commands.add_parser(name)
        install.add_argument("--labconfig", type=Path, required=True)
        install.add_argument("--apply", action="store_true")
    snapshot = commands.add_parser("snapshot")
    snapshot.add_argument("target", choices=("blacs", "runmanager"))
    snapshot.add_argument("--device")
    prepare = commands.add_parser("prepare")
    prepare.add_argument("spec", type=Path, help="JSON object with target, action, values, and optional device or shot count")
    for name in ("status", "events", "cancel", "observe"):
        command = commands.add_parser(name)
        command.add_argument("task_id")
    close = commands.add_parser("close-unresolved")
    close.add_argument("task_id")
    close.add_argument("--operator", required=True)
    close.add_argument("--reason", required=True)
    approve = commands.add_parser("approve")
    approve.add_argument("task_id")
    approve.add_argument("plan_digest")
    approve.add_argument("--operator", required=True)
    approve.add_argument("--minutes", type=int, default=15)
    policy = commands.add_parser("policy")
    policy.add_argument("spec", type=Path)
    authorize = commands.add_parser("authorize-policy")
    authorize.add_argument("task_id")
    authorize.add_argument("policy_id")
    for name in ("policy-status", "revoke-policy"):
        policy_command = commands.add_parser(name)
        policy_command.add_argument("policy_id")
    runner = commands.add_parser("serve")
    runner.add_argument("--interval", type=float, default=5)
    mcp = commands.add_parser("mcp")
    mcp.add_argument("--project-sources", action="store_true")
    deepseek = commands.add_parser("deepseek")
    deepseek.add_argument("--model", required=True)
    deepseek.add_argument("--project-sources", action="store_true")
    deepseek.add_argument("prompt")
    draft = commands.add_parser("draft-code")
    draft.add_argument("--repo", type=Path, required=True)
    draft.add_argument("--review-root", type=Path, required=True)
    draft.add_argument("--scope", action="append", required=True)
    draft.add_argument("prompt")
    collect = commands.add_parser("collect-draft")
    collect.add_argument("bundle", type=Path)
    return cli


def read_object(path):
    with path.open("rb") as file:
        raw = file.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("JSON input exceeds 1 MiB")
    data = load_json(raw.decode("utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    return data


def print_json(value):
    print(json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False), flush=True)


def run_service(app, interval):
    if not 0.5 <= interval <= 60:
        raise ValueError("Interval must be 0.5 to 60 seconds")
    active = {"EXECUTING", "OBSERVING", "UNKNOWN"}
    due = {}
    try:
        while True:
            tasks = app.store.list_active()
            current_ids = {task["task_id"] for task in tasks}
            due = {key: value for key, value in due.items() if key in current_ids}
            for task in tasks:
                key = task["task_id"]
                if task["status"] not in active:
                    due.pop(key, None)
                    continue
                if time.monotonic() >= due.get(key, 0):
                    try:
                        updated = app.service.observe(key)
                        if updated["status"] != task["status"]:
                            print_json(updated)
                    except (OSError, RuntimeError, ValueError) as exc:
                        print(f"Observation of {key}: {exc}", file=sys.stderr, flush=True)
                    due[key] = time.monotonic() + (max(30, interval) if task["status"] == "UNKNOWN" else interval)
            executed = app.service.run_next()
            if executed:
                print_json(executed)
            time.sleep(interval)
    except KeyboardInterrupt:
        return None


def dispatch(args):
    command = args.command
    if command in {"draft-code", "collect-draft"}:
        from .harness.worktree import collect_draft, draft_code

        if command == "collect-draft":
            return collect_draft(args.bundle)
        return draft_code(repo=args.repo, review_root=args.review_root, scope=args.scope, prompt=args.prompt)
    if command == "init":
        profile = Path(args.profile).expanduser().resolve()
        with profile.open("x", encoding="utf-8") as file:
            json.dump({"schema_version": 1, "simulate": True, "project_root": ".",
                       "host": {"state_db": profile.stem + ".host.sqlite3"}}, file, indent=2)
            file.write("\n")
        return {"profile": str(profile), "simulate": True}
    app = Automation(args.profile)
    if command == "doctor":
        environment = app.host.configuration("doctor", args.labconfig)
        capabilities = app.host.call("discover", {})
        return {**environment, "capabilities": capabilities}
    if command in {"install-host", "uninstall-host"}:
        return app.host.configuration(command.split("-")[0], args.labconfig.resolve(), args.apply)
    if command == "discover":
        return app.host.call("discover", {})
    if command == "snapshot":
        params = {"target": args.target}
        if args.device:
            params["device"] = args.device
        return app.dispatch("snapshot", params)
    if command == "prepare":
        return app.dispatch("prepare", read_object(args.spec))
    if command == "approve":
        if not 1 <= args.minutes <= 1440:
            raise ValueError("Approval validity must be between 1 and 1440 minutes")
        expires = datetime.now(timezone.utc) + timedelta(minutes=args.minutes)
        return app.store.approve(args.task_id, args.plan_digest, args.operator, expires.isoformat())
    if command == "policy":
        return app.store.create_policy(read_object(args.spec))
    if command == "authorize-policy":
        return app.store.authorize_policy(args.task_id, args.policy_id)
    if command == "policy-status":
        return app.store.get_policy(args.policy_id)
    if command == "revoke-policy":
        return app.store.revoke_policy(args.policy_id)
    if command == "run-next":
        return app.service.run_next()
    if command == "observe":
        return app.service.observe(args.task_id)
    if command == "close-unresolved":
        return app.store.close_unresolved(args.task_id, args.operator, args.reason)
    if command == "serve":
        return run_service(app, args.interval)
    if command == "list":
        return app.store.list()
    if command in {"status", "events", "cancel"}:
        method = {"status": app.store.get, "events": app.store.events, "cancel": app.store.cancel}[command]
        return method(args.task_id)
    if command == "ui":
        from .automation_ui import run_ui

        return run_ui(app.profile)
    from .harness import build_catalog

    if args.project_sources and app.project_root is None:
        raise ValueError("Set project_root before enabling project source tools")
    catalog = build_catalog(app.dispatch, source_root=app.project_root if args.project_sources else None)
    if command == "mcp":
        from .harness.mcp_stdio import serve

        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8")
            sys.stdout.reconfigure(encoding="utf-8", newline="\n")
        serve(catalog, sys.stdin, sys.stdout)
        return None
    from .harness.deepseek import DeepSeekHTTP, DeepSeekProvider

    return DeepSeekProvider(DeepSeekHTTP.from_env(), model=args.model).run(args.prompt, catalog)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = dispatch(args)
        if result is not None:
            print_json(result)
        if isinstance(result, dict) and result.get("state") in {"UNKNOWN", "REFUSED"}:
            return 2
        return 0
    except (ImportError, KeyError, OSError, RuntimeError, ValueError) as exc:
        print(f"LabPilot: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
