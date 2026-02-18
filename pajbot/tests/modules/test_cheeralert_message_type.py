from pajbot.modules.chat_alerts.cheeralert import CheerAlertModule


class FakeWebsocketManager:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, str]]] = []

    def emit(self, event_name: str, payload: dict[str, str]) -> None:
        self.events.append((event_name, payload))


class FakeBot:
    def __init__(self) -> None:
        self.websocket_manager = FakeWebsocketManager()
        self.sent_messages: list[tuple[str, str]] = []

    def send_message(self, message: str, method: str = "say") -> None:
        self.sent_messages.append((method, message))

    def execute_delayed(self, *args, **kwargs) -> None:
        return

    def whisper(self, *args, **kwargs) -> None:
        return

    def say(self, *args, **kwargs) -> None:
        return


class FakeUser:
    def __init__(self, name: str) -> None:
        self.name = name
        self.points = 0

    def __str__(self) -> str:
        return self.name


def test_cheer_alert_uses_selected_chat_message_type() -> None:
    module = CheerAlertModule(bot=None)
    module.settings = module.default_settings.copy()
    module.settings["chat_message"] = True
    module.settings["whisper_message"] = False
    module.settings["chat_message_type"] = "announce"
    module.settings["one_bit"] = "{username} cheered {num_bits}"
    module.settings["grant_points_per_100_bits"] = 0

    fake_bot = FakeBot()
    module.bot = fake_bot

    user = FakeUser("alice")
    module.on_cheer(user, 1)

    assert fake_bot.sent_messages == [("announce", "alice cheered 1")]
