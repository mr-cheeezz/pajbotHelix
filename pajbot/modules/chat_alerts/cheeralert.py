from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import logging
import math

from pajbot.managers.handler import HandlerManager
from pajbot.models.user import User
from pajbot.modules import BaseModule, ModuleSetting
from pajbot.modules.chat_alerts import ChatAlertModule

if TYPE_CHECKING:
    from pajbot.bot import Bot

log = logging.getLogger(__name__)


class CheerAlertModule(BaseModule):
    ID = __name__.split(".")[-1]
    NAME = "Cheer Alert"
    DESCRIPTION = "Prints a message in chat/whispers when a user cheers in your chat"
    CATEGORY = "Feature"
    ENABLED_DEFAULT = False
    PARENT_MODULE = ChatAlertModule
    SETTINGS = [
        ModuleSetting(
            key="chat_message",
            label="Enable chat messages for users who cheer bits",
            type="boolean",
            required=True,
            default=True,
        ),
        ModuleSetting(
            key="chat_message_type",
            label="Method to use when sending cheer chat messages",
            type="options",
            required=True,
            default="say",
            options=["announce", "say", "me"],
        ),
        ModuleSetting(
            key="whisper_message",
            label="Enable whisper messages for users who cheer bits",
            type="boolean",
            required=True,
            default=False,
        ),
        ModuleSetting(
            key="whisper_after",
            label="Whisper the message after X seconds",
            type="number",
            required=True,
            placeholder="",
            default=5,
            constraints={"min_value": 1, "max_value": 120},
        ),
        ModuleSetting(
            key="one_bit",
            label="Chat message for users who cheer 1 or more bits | Available arguments: {username}, {num_bits}",
            type="text",
            required=True,
            placeholder="{username} thank you so much for cheering {num_bits} bits! PogChamp",
            default="{username} thank you so much for cheering {num_bits} bits! PogChamp",
            constraints={"max_str_len": 400},
        ),
        ModuleSetting(
            key="sixnine_bits",
            label="Chat message for users who cheer 69 bits, leave empty to fallback to the previous bit amount message. | Available arguments: {username}, {num_bits}",
            type="text",
            required=True,
            placeholder="{username} thank you so much for cheering {num_bits} bits! Kreygasm",
            default="",
            constraints={"max_str_len": 400},
        ),
        ModuleSetting(
            key="hundred_bits",
            label="Chat message for users who cheer 100 or more bits, leave empty to fallback to the previous bit amount message. | Available arguments: {username}, {num_bits}",
            type="text",
            required=True,
            placeholder="{username} thank you so much for cheering {num_bits} bits! PogChamp",
            default="",
            constraints={"max_str_len": 400},
        ),
        ModuleSetting(
            key="fourtwenty_bits",
            label="Chat message for users who cheer 420 bits, leave empty to fallback to the previous bit amount message. | Available arguments: {username}, {num_bits}",
            type="text",
            required=True,
            placeholder="{username} thank you so much for cheering {num_bits} bits! CiGrip",
            default="",
            constraints={"max_str_len": 400},
        ),
        ModuleSetting(
            key="fivehundred_bits",
            label="Chat message for users who cheer 500 or more bits, leave empty to fallback to the previous bit amount message. | Available arguments: {username}, {num_bits}",
            type="text",
            required=True,
            placeholder="{username} thank you so much for cheering {num_bits} bits! PogChamp",
            default="",
            constraints={"max_str_len": 400},
        ),
        ModuleSetting(
            key="fifteenhundred_bits",
            label="Chat message for users who cheer 1500 or more bits, leave empty to fallback to the previous bit amount message. | Available arguments: {username}, {num_bits}",
            type="text",
            required=True,
            placeholder="{username} thank you so much for cheering {num_bits} bits! PogChamp",
            default="",
            constraints={"max_str_len": 400},
        ),
        ModuleSetting(
            key="fivethousand_bits",
            label="Chat message for users who cheer 5000 or more bits, leave empty to fallback to the previous bit amount message. | Available arguments: {username}, {num_bits}",
            type="text",
            required=True,
            placeholder="{username} thank you so much for cheering {num_bits} bits! PogChamp",
            default="",
            constraints={"max_str_len": 400},
        ),
        ModuleSetting(
            key="fivethousand_bits_message_type",
            label="Message type for 5000+ bits cheer alerts",
            type="options",
            required=True,
            default="inherit",
            options=["inherit", "announce", "say", "me"],
        ),
        ModuleSetting(
            key="tenthousand_bits",
            label="Chat message for users who cheer 10000 or more bits, leave empty to fallback to the previous bit amount message. | Available arguments: {username}, {num_bits}",
            type="text",
            required=True,
            placeholder="{username} thank you so much for cheering {num_bits} bits! PogChamp",
            default="",
            constraints={"max_str_len": 400},
        ),
        ModuleSetting(
            key="tenthousand_bits_message_type",
            label="Message type for 10000+ bits cheer alerts",
            type="options",
            required=True,
            default="inherit",
            options=["inherit", "announce", "say", "me"],
        ),
        ModuleSetting(
            key="twentyfivethousand_bits",
            label="Chat message for users who cheer 25000 or more bits, leave empty to fallback to the previous bit amount message. | Available arguments: {username}, {num_bits}",
            type="text",
            required=True,
            placeholder="{username} thank you so much for cheering {num_bits} bits! PogChamp",
            default="",
            constraints={"max_str_len": 400},
        ),
        ModuleSetting(
            key="twentyfivethousand_bits_message_type",
            label="Message type for 25000+ bits cheer alerts",
            type="options",
            required=True,
            default="inherit",
            options=["inherit", "announce", "say", "me"],
        ),
        ModuleSetting(
            key="grant_points_per_100_bits",
            label="Give points to user per 100 bits they cheer. 0 = off",
            type="number",
            required=True,
            placeholder="",
            default=0,
            constraints={"min_value": 0, "max_value": 1000000},
        ),
        ModuleSetting(
            key="alert_message_points_given",
            label="Message to announce points were given to user, leave empty to disable message. If the user cheers less than 100 bits, no message will be sent. | Available arguments: {username}, {points}, {num_bits}",
            type="text",
            required=True,
            default="{username} was given {points} points for cheering {num_bits} bits! FeelsAmazingMan",
            constraints={"max_str_len": 300},
        ),
    ]

    def __init__(self, bot: Optional[Bot]) -> None:
        super().__init__(bot)

    def _get_cheer_phrase_key(self, num_bits: int) -> Optional[str]:
        if num_bits >= 25000 and self.settings["twentyfivethousand_bits"] != "":
            return "twentyfivethousand_bits"
        if num_bits >= 10000 and self.settings["tenthousand_bits"] != "":
            return "tenthousand_bits"
        if num_bits >= 5000 and self.settings["fivethousand_bits"] != "":
            return "fivethousand_bits"
        if num_bits >= 1500 and self.settings["fifteenhundred_bits"] != "":
            return "fifteenhundred_bits"
        if num_bits >= 500 and self.settings["fivehundred_bits"] != "":
            return "fivehundred_bits"
        if num_bits == 420 and self.settings["fourtwenty_bits"] != "":
            return "fourtwenty_bits"
        if num_bits >= 100 and self.settings["hundred_bits"] != "":
            return "hundred_bits"
        if num_bits == 69 and self.settings["sixnine_bits"] != "":
            return "sixnine_bits"
        if self.settings["one_bit"] != "":
            return "one_bit"

        return None

    def _get_cheer_chat_method(self, phrase_key: str) -> str:
        override_key_by_phrase = {
            "fivethousand_bits": "fivethousand_bits_message_type",
            "tenthousand_bits": "tenthousand_bits_message_type",
            "twentyfivethousand_bits": "twentyfivethousand_bits_message_type",
        }

        override_setting_key = override_key_by_phrase.get(phrase_key)
        if override_setting_key is not None:
            override_method = self.settings[override_setting_key]
            if override_method != "inherit":
                return override_method

        return self.settings["chat_message_type"]

    def on_cheer(self, user: User, num_bits: int) -> None:
        """
        A user just cheered bits.
        Send the event to the websocket manager, and send a customized message in chat.
        """

        assert self.bot is not None

        payload = {"username": user.name, "num_bits": num_bits}
        self.bot.websocket_manager.emit("cheer", payload)

        selected_phrase_key = self._get_cheer_phrase_key(num_bits)
        selected_phrase = (
            self.get_phrase(selected_phrase_key, **payload) if selected_phrase_key is not None else None
        )

        if self.settings["chat_message"]:
            if selected_phrase is not None:
                method = self._get_cheer_chat_method(selected_phrase_key if selected_phrase_key is not None else "")
                self.bot.send_message(selected_phrase, method=method)

        if self.settings["whisper_message"]:
            if selected_phrase is not None:
                self.bot.execute_delayed(
                    self.settings["whisper_after"],
                    self.bot.whisper,
                    user,
                    selected_phrase,
                )

        if self.settings["grant_points_per_100_bits"] <= 0:
            return

        round_number = math.floor(num_bits / 100)

        if round_number > 0:
            points_to_grant = round_number * self.settings["grant_points_per_100_bits"]
            user.points += points_to_grant
            alert_message = self.settings["alert_message_points_given"]
            if alert_message != "":
                self.bot.say(alert_message.format(username=user, points=points_to_grant, num_bits=num_bits))

    def on_pubmsg(self, source: User, message: str, tags: dict[str, str]) -> bool:
        if "bits" not in tags:
            return True

        try:
            num_bits = int(tags["bits"])
        except ValueError:
            log.error("BabyRage error occurred with getting the bits integer")
            return True

        if "display-name" not in tags:
            log.debug(f"cheeralert requires a display-name, but it is missing: {tags}")
            return True
        self.on_cheer(source, num_bits)

        return True

    def enable(self, bot: Optional[Bot]) -> None:
        if bot is not None:
            HandlerManager.add_handler("on_pubmsg", self.on_pubmsg)

    def disable(self, bot: Optional[Bot]) -> None:
        if bot is not None:
            HandlerManager.remove_handler("on_pubmsg", self.on_pubmsg)
