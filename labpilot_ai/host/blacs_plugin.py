"""BLACS plugin that uses the native manual device state machine."""

import logging
from pathlib import Path
import time
import uuid

from labpilot_ai.blacs_bridge.accessor import BLACSAccessor
from labpilot_ai.blacs_bridge.plugin import Plugin as PluginHooks

from .adapters import blacs_values
from .blacs import atomic_json, mailbox
from .protocol import Profile, Refused, read_json, require_snapshot, snapshot


name = "LabPilot Host"
module = "labpilot_host"
log = logging.getLogger(__name__)


class Plugin(PluginHooks):
    def __init__(self, initial_settings=None):
        self.timer = None
        self.spool = None
        self.generation = uuid.uuid4().hex
        self.updated = 0.0
        self.pending = None

    def plugin_setup_complete(self, BLACS):
        try:
            from blacs.tab_base_classes import MODE_MANUAL, define_state
            from qtutils.qt.QtCore import QTimer

            config = BLACS["exp_config"]
            profile_path = config.get("BLACS/plugins", "labpilot_host.profile")
            self.profile = Profile(profile_path)
            if self.profile.simulate or not self.profile.blacs.get("enabled"):
                return
            self.accessor = BLACSAccessor(BLACS)
            self.queue = BLACS["experiment_queue"]
            self.manual_mode = MODE_MANUAL
            self.begin_state = define_state(MODE_MANUAL, False)(self._begin_state)
            self.finish_state = define_state(MODE_MANUAL, False)(self._finish_state)
            self.spool = mailbox(self.profile)
            (self.spool / "inbox").mkdir(parents=True, exist_ok=True)
            (self.spool / "outbox").mkdir(exist_ok=True)
            self.timer = QTimer()
            self.timer.timeout.connect(self.poll)
            self.timer.start(250)
        except Exception:
            log.exception("LabPilot Host plugin did not start")

    def close(self):
        if self.timer is not None:
            self.timer.stop()
        if self.spool is not None:
            try:
                if read_json(self.spool / "ready.json").get("generation") == self.generation:
                    (self.spool / "ready.json").unlink(missing_ok=True)
            except (OSError, ValueError):
                pass

    def _reply(self, message, state, *, value=None, reason=None):
        reply = {"generation": self.generation, "mail_id": message["mail_id"], "state": state,
                 "value": value, "reason": reason}
        atomic_json(self.spool / "outbox" / f"{message['mail_id']}.json", reply)

    def poll(self):
        try:
            now = time.time()
            if now - self.updated >= 2:
                atomic_json(self.spool / "ready.json", {"generation": self.generation, "updated": now})
                self.updated = now
            if self.pending and now > self.pending["expires"] + 2:
                # Late callbacks check identity and expiration before changing anything.
                self.pending = None
            path = next(iter((self.spool / "inbox").glob("*.json")), None)
            if path is not None:
                self._read_one(path)
        except Exception:
            log.exception("LabPilot Host mailbox poll failed")

    def _read_one(self, path):
        message = read_json(path)
        path.unlink(missing_ok=True)
        if (type(message) is not dict or path.stem != message.get("mail_id") or
                message.get("generation") != self.generation or
                type(message.get("expires")) not in (float, int) or not 0 < message["expires"] - time.time() <= 7):
            return
        try:
            params = message["params"]
            if message["method"] == "discover":
                devices = sorted(self.accessor._tabs())
                self._reply(message, "OK", value={"available": True, "devices": devices,
                                                  "actions": ["set_manual"] if self.profile.blacs["allow"] else [],
                                                  "write_channels": self.profile.blacs["allow"]})
            elif message["method"] == "snapshot":
                value, _ = self._capture(params.get("device"))
                self._reply(message, "OK", value=value)
            elif message["method"] == "execute" and params.get("action") == "set_manual":
                self._prepare(message)
            else:
                raise Refused("Unsupported BLACS mailbox operation")
        except Refused as exc:
            self._reply(message, "REFUSED", reason=str(exc))
        except Exception:
            log.exception("LabPilot Host mailbox request failed")
            self._reply(message, "UNKNOWN", reason="BLACS plugin could not complete request")

    def _queue_state(self):
        status = str(self.queue.get_status()).strip().lower()
        model = self.queue._model
        count = model.file_count() if hasattr(model, "file_count") else model.rowCount()
        return {"paused": bool(self.queue.manager_paused), "repeat": bool(self.queue.manager_repeat),
                "status": status, "queued": int(count), "active": bool(self.queue._ui.running_shot_name.text())}

    def _capture(self, device):
        if type(device) is not str or device not in self.accessor._tabs():
            raise Refused("Select an exact discovered BLACS device")
        tab = self.accessor._tabs()[device]
        refs = {}
        channels = {}
        values = {}
        for ref in self.accessor._channel_refs():
            if ref.device != device or ref.kind not in {"AO", "DO", "DDS.freq", "DDS.amp", "DDS.phase", "DDS.gate"}:
                continue
            channel = f"{ref.channel}.{ref.subchannel}" if ref.subchannel else ref.channel
            refs[channel] = ref
            channels[channel] = {"kind": ref.kind, "unit": ref.unit, "locked": bool(ref.locked)}
            if ref.minimum is not None and ref.maximum is not None:
                channels[channel]["limits"] = [ref.minimum, ref.maximum]
            values[channel] = ref.value
        value = {"device": device, "generation": self.generation, "channels": channels,
                 "values": values, "manual": tab.mode == self.manual_mode and not tab.error_message,
                 "queue": self._queue_state(), "evidence": "BLACS_FRONT_PANEL"}
        return snapshot(value), refs

    def _require_ready(self, value):
        queue = value["queue"]
        if (not value["manual"] or not queue["paused"] or queue["repeat"] or queue["queued"] or queue["active"]
                or queue["status"] not in {"idle", "queue paused"}):
            raise Refused("Manual programming requires a healthy manual device and an idle, paused, empty BLACS queue")

    def _prepare(self, message):
        if self.pending is not None:
            raise Refused("A prior BLACS operation is in progress")
        params = message["params"]
        device = params.get("device")
        before, refs = self._capture(device)
        self._require_ready(before)
        require_snapshot(params, before)
        values = blacs_values(params, before)
        allowed = self.profile.blacs["allow"].get(device, [])
        if any(channel not in allowed or before["channels"][channel]["locked"] for channel in values):
            raise Refused("BLACS channel is locked or not allowed in the host profile")
        tab = next(iter(refs.values())).tab
        self.pending = message
        self.begin_state(tab, message, self)

    @staticmethod
    def _begin_state(tab, message, plugin):
        if plugin.pending is not message or time.time() >= message["expires"]:
            return
        params = message["params"]
        changed = False
        try:
            before, refs = plugin._capture(params["device"])
            plugin._require_ready(before)
            require_snapshot(params, before)
            for channel, value in params["values"].items():
                ref = refs[channel]
                output = getattr(ref.output, ref.subchannel) if ref.subchannel else ref.output
                changed = True
                output.set_value(value, program=False)
            projected, _ = plugin._capture(params["device"])
            message["requested_front_panel"] = {channel: projected["values"][channel] for channel in params["values"]}
            tab.program_device()
            plugin.finish_state(tab, message, plugin)
        except Exception as exc:
            state = "UNKNOWN" if changed else "REFUSED"
            plugin._reply(message, state, reason=str(exc))
            plugin.pending = None

    @staticmethod
    def _finish_state(tab, message, plugin):
        if plugin.pending is not message:
            return
        try:
            params = message["params"]
            after, refs = plugin._capture(params["device"])
            if tab.error_message or not after["manual"]:
                raise RuntimeError("BLACS device reported a manual programming error")
            for channel in params["values"]:
                ref = refs[channel]
                programmed = tab._last_programmed_values.get(ref.channel)
                if ref.subchannel and isinstance(programmed, dict):
                    programmed = programmed.get(ref.subchannel)
                if programmed != after["values"][channel] or programmed != message["requested_front_panel"][channel]:
                    raise RuntimeError("BLACS programmed and front-panel values differ")
            plugin._reply(message, "OK", value={"after": after, "evidence": {
                "native_state_completed": True, "physical_output_verified": False,
                "source": "BLACS_PROGRAM_DEVICE_STATE_AND_FRONT_PANEL"}})
        except Exception as exc:
            plugin._reply(message, "UNKNOWN", reason=str(exc))
        finally:
            plugin.pending = None
