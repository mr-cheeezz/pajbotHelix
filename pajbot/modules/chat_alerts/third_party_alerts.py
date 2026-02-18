from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
import hashlib
import json
import threading
import time
import urllib.parse
import uuid

import logging

from pajbot.managers.db import DBManager
from pajbot.managers.schedule import ScheduledJob
from pajbot.managers.schedule import ScheduleManager
from pajbot.models.user import User
from pajbot.modules import BaseModule, ModuleSetting
from pajbot.modules.chat_alerts import ChatAlertModule

import requests
from requests import HTTPError

try:
    import websocket  # type: ignore[import-not-found]
except ImportError:
    websocket = None

log = logging.getLogger(__name__)


@dataclass
class ExternalTipEvent:
    event_id: str
    username: str
    amount: Decimal
    currency: str
    message: str
    provider: str


class ThirdPartyAlertsModule(BaseModule):
    ID = __name__.split(".")[-1]
    NAME = "Streamlabs / StreamElements Alerts"
    DESCRIPTION = "Fetches tip/donation alerts from StreamElements or Streamlabs and can grant points."
    CATEGORY = "Feature"
    ENABLED_DEFAULT = True
    PARENT_MODULE = ChatAlertModule
    SETTINGS = [
        ModuleSetting(
            key="chat_alert_tip_enabled",
            label="Send chat alerts for external tips/donations",
            type="boolean",
            required=True,
            default=True,
        ),
        ModuleSetting(
            key="tip_amount_1_message",
            label="Tip alert message for 1+ amount (full independent message). Leave empty to disable this bucket | Available arguments: {provider}, {username}, {amount}, {currency}, {message}",
            type="text",
            required=True,
            default="",
            constraints={"min_str_len": 0, "max_str_len": 400},
        ),
        ModuleSetting(
            key="tip_amount_1_message_type",
            label="Message type for 1+ amount tip alerts",
            type="options",
            required=True,
            default="say",
            options=["announce", "say", "me"],
        ),
        ModuleSetting(
            key="tip_amount_5_message",
            label="Tip alert message for 5+ amount (full independent message). Leave empty to disable this bucket | Available arguments: {provider}, {username}, {amount}, {currency}, {message}",
            type="text",
            required=True,
            default="",
            constraints={"min_str_len": 0, "max_str_len": 400},
        ),
        ModuleSetting(
            key="tip_amount_5_message_type",
            label="Message type for 5+ amount tip alerts",
            type="options",
            required=True,
            default="say",
            options=["announce", "say", "me"],
        ),
        ModuleSetting(
            key="tip_amount_10_message",
            label="Tip alert message for 10+ amount (full independent message). Leave empty to disable this bucket | Available arguments: {provider}, {username}, {amount}, {currency}, {message}",
            type="text",
            required=True,
            default="",
            constraints={"min_str_len": 0, "max_str_len": 400},
        ),
        ModuleSetting(
            key="tip_amount_10_message_type",
            label="Message type for 10+ amount tip alerts",
            type="options",
            required=True,
            default="say",
            options=["announce", "say", "me"],
        ),
        ModuleSetting(
            key="tip_amount_20_message",
            label="Tip alert message for 20+ amount (full independent message). Leave empty to disable this bucket | Available arguments: {provider}, {username}, {amount}, {currency}, {message}",
            type="text",
            required=True,
            default="",
            constraints={"min_str_len": 0, "max_str_len": 400},
        ),
        ModuleSetting(
            key="tip_amount_20_message_type",
            label="Message type for 20+ amount tip alerts",
            type="options",
            required=True,
            default="say",
            options=["announce", "say", "me"],
        ),
        ModuleSetting(
            key="tip_amount_50_message",
            label="Tip alert message for 50+ amount (full independent message). Leave empty to disable this bucket | Available arguments: {provider}, {username}, {amount}, {currency}, {message}",
            type="text",
            required=True,
            default="",
            constraints={"min_str_len": 0, "max_str_len": 400},
        ),
        ModuleSetting(
            key="tip_amount_50_message_type",
            label="Message type for 50+ amount tip alerts",
            type="options",
            required=True,
            default="say",
            options=["announce", "say", "me"],
        ),
        ModuleSetting(
            key="tip_amount_100_message",
            label="Tip alert message for 100+ amount (full independent message). Leave empty to disable this bucket | Available arguments: {provider}, {username}, {amount}, {currency}, {message}",
            type="text",
            required=True,
            default="",
            constraints={"min_str_len": 0, "max_str_len": 400},
        ),
        ModuleSetting(
            key="tip_amount_100_message_type",
            label="Message type for 100+ amount tip alerts",
            type="options",
            required=True,
            default="say",
            options=["announce", "say", "me"],
        ),
        ModuleSetting(
            key="tip_amount_250_message",
            label="Tip alert message for 250+ amount (full independent message). Leave empty to disable this bucket | Available arguments: {provider}, {username}, {amount}, {currency}, {message}",
            type="text",
            required=True,
            default="",
            constraints={"min_str_len": 0, "max_str_len": 400},
        ),
        ModuleSetting(
            key="tip_amount_250_message_type",
            label="Message type for 250+ amount tip alerts",
            type="options",
            required=True,
            default="say",
            options=["announce", "say", "me"],
        ),
        ModuleSetting(
            key="grant_points_per_tip",
            label="Points to give to donor on each external tip/donation (if donor matches a user in DB). 0 = off",
            type="number",
            required=True,
            default=0,
            constraints={"min_value": 0, "max_value": 1000000},
        ),
        ModuleSetting(
            key="grant_points_message",
            label="Message to announce points were given to donor, leave empty to disable | Available arguments: {user}, {points}, {provider}",
            type="text",
            required=True,
            default="{user} was given {points} points from {provider} support! FeelsAmazingMan",
            constraints={"min_str_len": 0, "max_str_len": 300},
        ),
    ]

    def __init__(self, bot) -> None:
        super().__init__(bot)

        self.provider = "none"
        self.token = ""
        self.streamlabs_socket_token = ""
        self.poll_seconds = 20
        self.realtime_enabled = True
        self.se_channel_id: Optional[str] = None

        self.seen_event_ids: set[str] = set()
        self.max_seen_events = 300
        self.initialized_event_cache = False
        self.poll_job: Optional[ScheduledJob] = None

        self._realtime_thread: Optional[threading.Thread] = None
        self._realtime_stop_event = threading.Event()

    def _load_provider_config(self) -> None:
        if self.bot is None:
            return

        provider_config = self.bot.config.get("alerts_provider", {})
        raw_provider = provider_config.get("provider", "none").strip().lower()
        if raw_provider not in ("none", "streamelements", "streamlabs"):
            log.warning("Unknown alerts_provider.provider value '%s'. Falling back to 'none'.", raw_provider)
            raw_provider = "none"

        self.provider = raw_provider
        self.token = provider_config.get("token", "").strip()
        self.streamlabs_socket_token = provider_config.get("socket_token", "").strip()

        try:
            self.poll_seconds = int(provider_config.get("poll_seconds", "20"))
        except ValueError:
            self.poll_seconds = 20

        self.poll_seconds = max(10, min(self.poll_seconds, 300))
        self.realtime_enabled = str(provider_config.get("realtime_enabled", "true")).strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

    @staticmethod
    def _parse_amount(value: Any) -> Decimal:
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return Decimal("0")

    @staticmethod
    def _parse_bool(value: Any) -> bool:
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    @staticmethod
    def _stable_fallback_id(prefix: str, payload: dict[str, Any]) -> str:
        digest = hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        return f"{prefix}-{digest}"

    @staticmethod
    def _extract_message_text(payload: dict[str, Any]) -> str:
        for key in ("message", "tipMessage"):
            value = payload.get(key)
            if isinstance(value, str):
                return value.strip()
        return ""

    @staticmethod
    def _extract_currency(payload: dict[str, Any]) -> str:
        for key in ("currency", "currencyCode"):
            value = payload.get(key)
            if value:
                return str(value)
        return "USD"

    @staticmethod
    def _format_amount(amount: Decimal) -> str:
        text = format(amount, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text

    def _resolve_streamelements_channel_id(self) -> Optional[str]:
        if self.bot is None:
            return None

        if self.se_channel_id is not None:
            return self.se_channel_id

        response = requests.get(
            f"https://api.streamelements.com/kappa/v2/channels/{self.bot.streamer.login}",
            timeout=15,
        )
        response.raise_for_status()
        json_data = response.json()
        channel_id = json_data.get("_id")
        if not channel_id:
            raise ValueError("StreamElements channel lookup did not return a valid _id")

        self.se_channel_id = channel_id
        return channel_id

    def _fetch_streamelements_tips(self) -> list[ExternalTipEvent]:
        if not self.token:
            log.warning("alerts_provider is streamelements but no token configured")
            return []

        channel_id = self._resolve_streamelements_channel_id()
        if channel_id is None:
            return []

        response = requests.get(
            f"https://api.streamelements.com/kappa/v2/tips/{channel_id}",
            headers={"Authorization": f"Bearer {self.token}"},
            params={"limit": 20},
            timeout=15,
        )
        response.raise_for_status()
        json_data = response.json()

        raw_tips = json_data.get("docs", [])
        events: list[ExternalTipEvent] = []
        for tip in raw_tips:
            event_id = str(tip.get("_id", ""))
            username = str(tip.get("username", "")).strip()
            if not event_id or not username:
                continue

            events.append(
                ExternalTipEvent(
                    event_id=event_id,
                    username=username,
                    amount=self._parse_amount(tip.get("amount", "0")),
                    currency=str(tip.get("currency", "USD")),
                    message=str(tip.get("message", "")).strip(),
                    provider="StreamElements",
                )
            )

        events.reverse()
        return events

    def _fetch_streamlabs_donations(self) -> list[ExternalTipEvent]:
        if not self.token:
            log.info("Streamlabs polling is disabled because no access token is configured")
            return []

        response = requests.get(
            "https://streamlabs.com/api/v1.0/donations",
            params={"access_token": self.token, "limit": 20},
            timeout=15,
        )
        response.raise_for_status()
        json_data = response.json()

        raw_donations = json_data.get("data", [])
        events: list[ExternalTipEvent] = []
        for donation in raw_donations:
            event_id = str(donation.get("donation_id", donation.get("id", "")))
            username = str(
                donation.get("name", donation.get("username", donation.get("from", "")))
            ).strip()
            if not event_id or not username:
                continue

            events.append(
                ExternalTipEvent(
                    event_id=event_id,
                    username=username,
                    amount=self._parse_amount(donation.get("amount", "0")),
                    currency=str(donation.get("currency", "USD")),
                    message=str(donation.get("message", "")).strip(),
                    provider="Streamlabs",
                )
            )

        events.reverse()
        return events

    def _fetch_provider_events(self) -> list[ExternalTipEvent]:
        if self.provider == "streamelements":
            return self._fetch_streamelements_tips()
        if self.provider == "streamlabs":
            return self._fetch_streamlabs_donations()
        return []

    @staticmethod
    def _read_json_text(raw_text: str) -> Optional[dict[str, Any]]:
        try:
            parsed = json.loads(raw_text)
        except ValueError:
            return None

        if isinstance(parsed, dict):
            return parsed
        return None

    def _event_from_streamelements_payload(self, payload: dict[str, Any]) -> Optional[ExternalTipEvent]:
        # The live activity stream can contain multiple event kinds.
        event_type = str(payload.get("type", payload.get("event", ""))).lower()
        amount = self._parse_amount(payload.get("amount", payload.get("tipAmount", "0")))
        if amount <= 0 and event_type not in ("tip", "donation", "tips"):
            return None

        username = str(payload.get("username", payload.get("user", payload.get("displayName", "")))).strip()
        if not username:
            return None

        raw_id = payload.get("_id", payload.get("id", payload.get("eventId", payload.get("uuid"))))
        if raw_id:
            event_id = str(raw_id)
        else:
            event_id = self._stable_fallback_id("se", payload)

        return ExternalTipEvent(
            event_id=event_id,
            username=username,
            amount=amount,
            currency=self._extract_currency(payload),
            message=self._extract_message_text(payload),
            provider="StreamElements",
        )

    def _extract_streamelements_events(self, parsed_message: dict[str, Any]) -> list[ExternalTipEvent]:
        data = parsed_message.get("data")
        if not isinstance(data, dict):
            return []

        payload = data.get("payload")
        if isinstance(payload, dict):
            event = self._event_from_streamelements_payload(payload)
            return [event] if event is not None else []

        if isinstance(payload, list):
            events: list[ExternalTipEvent] = []
            for item in payload:
                if not isinstance(item, dict):
                    continue
                event = self._event_from_streamelements_payload(item)
                if event is not None:
                    events.append(event)
            return events

        return []

    def _event_from_streamlabs_payload(self, payload: dict[str, Any]) -> Optional[ExternalTipEvent]:
        event_type = str(payload.get("type", "")).lower()
        if event_type and event_type != "donation":
            return None

        username = str(payload.get("name", payload.get("username", payload.get("from", "")))).strip()
        if not username:
            return None

        raw_id = payload.get("donation_id", payload.get("id", payload.get("message_id")))
        if raw_id:
            event_id = str(raw_id)
        else:
            event_id = self._stable_fallback_id("sl", payload)

        return ExternalTipEvent(
            event_id=event_id,
            username=username,
            amount=self._parse_amount(payload.get("amount", "0")),
            currency=self._extract_currency(payload),
            message=self._extract_message_text(payload),
            provider="Streamlabs",
        )

    def _extract_streamlabs_events(self, payload: dict[str, Any]) -> list[ExternalTipEvent]:
        event_type = str(payload.get("type", payload.get("for", ""))).lower()
        if event_type and event_type not in ("donation", "streamlabs"):
            return []

        message_payload = payload.get("message")
        if isinstance(message_payload, dict):
            event = self._event_from_streamlabs_payload(message_payload)
            return [event] if event is not None else []

        if isinstance(message_payload, list):
            events: list[ExternalTipEvent] = []
            for item in message_payload:
                if not isinstance(item, dict):
                    continue
                event = self._event_from_streamlabs_payload(item)
                if event is not None:
                    events.append(event)
            return events

        event = self._event_from_streamlabs_payload(payload)
        return [event] if event is not None else []

    def _remember_event_id(self, event_id: str) -> None:
        self.seen_event_ids.add(event_id)

        if len(self.seen_event_ids) > self.max_seen_events:
            # Keep memory bounded - we only need recent IDs.
            self.seen_event_ids = set(list(self.seen_event_ids)[-self.max_seen_events :])

    def _handle_incoming_events(self, events: list[ExternalTipEvent]) -> None:
        for event in events:
            if event.event_id in self.seen_event_ids:
                continue

            self._remember_event_id(event.event_id)
            if self.bot is not None:
                self.bot.execute_now(self._handle_tip_event, event)

    def _streamlabs_fetch_socket_token(self) -> str:
        response = requests.get(
            "https://streamlabs.com/api/v2.0/socket/token",
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=15,
        )
        response.raise_for_status()
        json_data = response.json()
        socket_token = str(json_data.get("socket_token", "")).strip()
        if not socket_token:
            raise ValueError("Streamlabs socket token response was missing socket_token")
        return socket_token

    def _resolve_streamlabs_socket_token(self) -> str:
        if self.streamlabs_socket_token:
            return self.streamlabs_socket_token
        if self.token:
            return self._streamlabs_fetch_socket_token()
        raise RuntimeError("No Streamlabs token configured (set socket_token or token)")

    def _run_streamelements_realtime_once(self) -> None:
        if websocket is None:
            raise RuntimeError("websocket-client is not installed")
        if not self.token:
            raise RuntimeError("No StreamElements token configured")

        channel_id = self._resolve_streamelements_channel_id()
        if channel_id is None:
            raise RuntimeError("Unable to resolve StreamElements channel id")

        ws = websocket.create_connection("wss://astro.streamelements.com", timeout=30)
        try:
            subscribe_payload = {
                "type": "subscribe",
                "nonce": str(uuid.uuid4()),
                "data": {"topic": "channel.activities", "room": channel_id, "token": self.token},
            }
            ws.send(json.dumps(subscribe_payload))

            while not self._realtime_stop_event.is_set():
                raw_message = ws.recv()
                if not raw_message:
                    continue

                if isinstance(raw_message, bytes):
                    raw_message = raw_message.decode("utf-8", "replace")

                parsed_message = self._read_json_text(raw_message)
                if parsed_message is None:
                    continue

                events = self._extract_streamelements_events(parsed_message)
                if events:
                    self._handle_incoming_events(events)
        finally:
            try:
                ws.close()
            except Exception:
                pass

    def _run_streamlabs_realtime_once(self) -> None:
        if websocket is None:
            raise RuntimeError("websocket-client is not installed")

        socket_token = self._resolve_streamlabs_socket_token()
        token_query = urllib.parse.quote(socket_token, safe="")
        ws = websocket.create_connection(
            f"wss://sockets.streamlabs.com/socket.io/?EIO=3&transport=websocket&token={token_query}",
            timeout=30,
        )
        try:
            connected_namespace = False
            while not self._realtime_stop_event.is_set():
                raw_message = ws.recv()
                if not raw_message:
                    continue

                if isinstance(raw_message, bytes):
                    raw_message = raw_message.decode("utf-8", "replace")

                if raw_message.startswith("0"):
                    ws.send("40")
                    connected_namespace = True
                    continue

                if raw_message == "2":
                    ws.send("3")
                    continue

                if not connected_namespace:
                    continue

                if not raw_message.startswith("42"):
                    continue

                try:
                    payload = json.loads(raw_message[2:])
                except ValueError:
                    continue

                if not isinstance(payload, list) or len(payload) < 2:
                    continue

                event_name = payload[0]
                event_payload = payload[1]
                if event_name != "event" or not isinstance(event_payload, dict):
                    continue

                events = self._extract_streamlabs_events(event_payload)
                if events:
                    self._handle_incoming_events(events)
        finally:
            try:
                ws.close()
            except Exception:
                pass

    def _run_realtime_loop(self) -> None:
        while not self._realtime_stop_event.is_set():
            try:
                if self.provider == "streamelements":
                    self._run_streamelements_realtime_once()
                elif self.provider == "streamlabs":
                    self._run_streamlabs_realtime_once()
                else:
                    return
            except HTTPError as ex:
                status_code = ex.response.status_code if ex.response is not None else "unknown"
                log.warning("Realtime alerts HTTP error for %s: status=%s", self.provider, status_code)
            except Exception:
                log.exception("Realtime alerts connection failed for provider=%s", self.provider)

            if self._realtime_stop_event.is_set():
                return

            time.sleep(5)

    def _grant_points_for_tip(self, event: ExternalTipEvent) -> None:
        if self.bot is None:
            return

        points_to_grant = self.settings["grant_points_per_tip"]
        if points_to_grant <= 0:
            return

        with DBManager.create_session_scope() as db_session:
            user = User.find_by_user_input(db_session, event.username)
            if user is None:
                log.debug(
                    "Skipping points grant for %s event %s, user '%s' not found in DB",
                    event.provider,
                    event.event_id,
                    event.username,
                )
                return

            user.points += points_to_grant

            grant_message = self.settings["grant_points_message"]
            if grant_message != "":
                self.bot.say(grant_message.format(user=user, points=points_to_grant, provider=event.provider))

    def _select_tip_message_and_type(self, amount: Decimal) -> tuple[str, str]:
        fixed_thresholds = [
            (Decimal("1"), "tip_amount_1_message", "tip_amount_1_message_type"),
            (Decimal("5"), "tip_amount_5_message", "tip_amount_5_message_type"),
            (Decimal("10"), "tip_amount_10_message", "tip_amount_10_message_type"),
            (Decimal("20"), "tip_amount_20_message", "tip_amount_20_message_type"),
            (Decimal("50"), "tip_amount_50_message", "tip_amount_50_message_type"),
            (Decimal("100"), "tip_amount_100_message", "tip_amount_100_message_type"),
            (Decimal("250"), "tip_amount_250_message", "tip_amount_250_message_type"),
        ]
        # Amount buckets are independent and there is no fallback message.
        selected_bucket: Optional[tuple[str, str]] = None
        selected_threshold = Decimal("0")
        for threshold, message_key, method_key in fixed_thresholds:
            if amount >= threshold and threshold >= selected_threshold:
                selected_threshold = threshold
                selected_bucket = (message_key, method_key)

        if selected_bucket is not None:
            message_key, method_key = selected_bucket
            if self.settings[message_key] != "":
                return message_key, self.settings[method_key]

        return "", "say"

    def _handle_tip_event(self, event: ExternalTipEvent) -> None:
        if self.bot is None:
            return

        if self.settings["chat_alert_tip_enabled"]:
            tip_message_key, tip_message_type = self._select_tip_message_and_type(event.amount)
            if tip_message_key != "":
                chat_message = self.get_phrase(
                    tip_message_key,
                    provider=event.provider,
                    username=event.username,
                    amount=self._format_amount(event.amount),
                    currency=event.currency,
                    message=event.message,
                )
                if chat_message.strip() != "":
                    self.bot.send_message(chat_message, method=tip_message_type)

        self._grant_points_for_tip(event)

    def _poll_provider_events(self) -> None:
        try:
            events = self._fetch_provider_events()
        except Exception:
            log.exception("Failed polling %s events", self.provider)
            return

        if not self.initialized_event_cache:
            for event in events:
                self._remember_event_id(event.event_id)
            self.initialized_event_cache = True
            return

        self._handle_incoming_events(events)

    def _start_realtime_if_configured(self) -> None:
        if not self.realtime_enabled:
            log.info("Realtime third-party alerts disabled via [alerts_provider] realtime_enabled=false")
            return

        if websocket is None:
            log.warning(
                "Realtime third-party alerts requested but websocket-client is missing. Install dependencies to enable realtime."
            )
            return

        self._realtime_stop_event.clear()
        self._realtime_thread = threading.Thread(
            name=f"ThirdPartyAlertsRealtime-{self.provider}",
            target=self._run_realtime_loop,
            daemon=True,
        )
        self._realtime_thread.start()

    def _stop_realtime(self) -> None:
        self._realtime_stop_event.set()
        if self._realtime_thread is not None:
            self._realtime_thread.join(timeout=3)
            self._realtime_thread = None

    def enable(self, bot) -> None:
        if bot is None:
            return

        self._load_provider_config()
        if self.provider == "none":
            log.info("ThirdPartyAlertsModule disabled via [alerts_provider] provider=none")
            return

        self._start_realtime_if_configured()
        self.poll_job = ScheduleManager.execute_every(self.poll_seconds, self._poll_provider_events)

    def disable(self, bot) -> None:
        self._stop_realtime()

        if self.poll_job is not None:
            self.poll_job.remove()
            self.poll_job = None
