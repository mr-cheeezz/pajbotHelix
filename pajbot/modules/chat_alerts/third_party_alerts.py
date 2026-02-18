from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import logging

from pajbot.managers.db import DBManager
from pajbot.managers.schedule import ScheduleManager
from pajbot.models.user import User
from pajbot.modules import BaseModule, ModuleSetting
from pajbot.modules.chat_alerts import ChatAlertModule

import requests

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
    NAME = "Third Party Alerts"
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
            key="chat_alert_tip_message",
            label="External tip alert message | Available arguments: {provider}, {username}, {amount}, {currency}, {message}",
            type="text",
            required=True,
            default="[ {provider} ] {username} tipped {amount} {currency}! {message}",
            constraints={"min_str_len": 10, "max_str_len": 400},
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
        self.poll_seconds = 20
        self.se_channel_id: Optional[str] = None

        self.seen_event_ids: set[str] = set()
        self.max_seen_events = 300
        self.initialized_event_cache = False

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

        try:
            self.poll_seconds = int(provider_config.get("poll_seconds", "20"))
        except ValueError:
            self.poll_seconds = 20

        self.poll_seconds = max(10, min(self.poll_seconds, 300))

    @staticmethod
    def _parse_amount(value: Any) -> Decimal:
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return Decimal("0")

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
            log.warning("alerts_provider is streamlabs but no token configured")
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

    def _remember_event_id(self, event_id: str) -> None:
        self.seen_event_ids.add(event_id)

        if len(self.seen_event_ids) > self.max_seen_events:
            # Keep memory bounded - we only need recent IDs.
            self.seen_event_ids = set(list(self.seen_event_ids)[-self.max_seen_events :])

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

    def _handle_tip_event(self, event: ExternalTipEvent) -> None:
        if self.bot is None:
            return

        if self.settings["chat_alert_tip_enabled"]:
            chat_message = self.get_phrase(
                "chat_alert_tip_message",
                provider=event.provider,
                username=event.username,
                amount=f"{event.amount.normalize()}",
                currency=event.currency,
                message=event.message,
            )
            self.bot.say(chat_message)

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

        for event in events:
            if event.event_id in self.seen_event_ids:
                continue

            self._remember_event_id(event.event_id)
            self._handle_tip_event(event)

    def enable(self, bot) -> None:
        if bot is None:
            return

        self._load_provider_config()
        if self.provider == "none":
            log.info("ThirdPartyAlertsModule disabled via [alerts_provider] provider=none")
            return

        ScheduleManager.execute_every(self.poll_seconds, self._poll_provider_events)

