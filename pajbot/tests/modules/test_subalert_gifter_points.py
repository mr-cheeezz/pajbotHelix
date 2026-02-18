from pajbot.modules.chat_alerts.subalert import SubAlertModule


class FakeBot:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []

    def say(self, message: str) -> None:
        self.sent_messages.append(message)


class FakeUser:
    def __init__(self, points: int, name: str) -> None:
        self.points = points
        self.name = name

    def __str__(self) -> str:
        return self.name


def test_on_gift_sub_shared_grants_points_and_announces() -> None:
    module = SubAlertModule(bot=None)
    module.settings = module.default_settings.copy()
    module.settings["grant_points_on_gift_sub"] = 20
    module.settings["alert_message_points_given_gifter"] = "{user} got {points} for {gift_count} gifts"

    fake_bot = FakeBot()
    module.bot = fake_bot

    gifter = FakeUser(points=100, name="gifter")

    module.on_gift_sub_shared(gifter, gift_count=3)

    assert gifter.points == 160
    assert fake_bot.sent_messages == ["gifter got 60 for 3 gifts"]


def test_on_gift_sub_shared_is_noop_when_disabled() -> None:
    module = SubAlertModule(bot=None)
    module.settings = module.default_settings.copy()
    module.settings["grant_points_on_gift_sub"] = 0

    fake_bot = FakeBot()
    module.bot = fake_bot

    gifter = FakeUser(points=100, name="gifter")
    module.on_gift_sub_shared(gifter, gift_count=2)

    assert gifter.points == 100
    assert fake_bot.sent_messages == []
