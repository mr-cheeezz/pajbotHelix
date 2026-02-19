from decimal import Decimal

from pajbot.modules.chat_alerts.third_party_alerts import ExternalTipEvent, ThirdPartyAlertsModule


class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise ValueError(f"Bad response code: {self.status_code}")

    def json(self):
        return self._json


def test_fetch_streamlabs_donations_normalizes_events(monkeypatch) -> None:
    module = ThirdPartyAlertsModule(bot=None)
    module.provider = "streamlabs"
    module.token = "abc"

    def fake_get(url, params=None, timeout=None):
        assert "streamlabs.com/api/v1.0/donations" in url
        return FakeResponse(
            {
                "data": [
                    {
                        "donation_id": 10,
                        "name": "alice",
                        "amount": "4.20",
                        "currency": "USD",
                        "message": "great stream",
                    }
                ]
            }
        )

    monkeypatch.setattr("pajbot.modules.chat_alerts.third_party_alerts.requests.get", fake_get)

    events = module._fetch_streamlabs_donations()
    assert len(events) == 1
    assert events[0].event_id == "10"
    assert events[0].username == "alice"
    assert events[0].amount == Decimal("4.20")
    assert events[0].provider == "Streamlabs"


def test_fetch_streamelements_tips_normalizes_events(monkeypatch) -> None:
    module = ThirdPartyAlertsModule(bot=None)
    module.provider = "streamelements"
    module.token = "abc"

    monkeypatch.setattr(
        ThirdPartyAlertsModule,
        "_resolve_streamelements_channel_id",
        lambda self: "channel-id",
    )

    def fake_get(url, headers=None, params=None, timeout=None):
        assert "api.streamelements.com/kappa/v2/tips/channel-id" in url
        return FakeResponse(
            {
                "docs": [
                    {
                        "_id": "tip-1",
                        "username": "bob",
                        "amount": "5",
                        "currency": "EUR",
                        "message": "pog",
                    }
                ]
            }
        )

    monkeypatch.setattr("pajbot.modules.chat_alerts.third_party_alerts.requests.get", fake_get)

    events = module._fetch_streamelements_tips()
    assert len(events) == 1
    assert events[0].event_id == "tip-1"
    assert events[0].username == "bob"
    assert events[0].amount == Decimal("5")
    assert events[0].provider == "StreamElements"


def test_extract_streamelements_realtime_events() -> None:
    module = ThirdPartyAlertsModule(bot=None)
    parsed = {
        "type": "event",
        "data": {
            "topic": "channel.activities",
            "payload": {
                "_id": "realtime-tip-1",
                "type": "tip",
                "username": "charlie",
                "amount": "7.50",
                "currency": "USD",
                "message": "live pog",
            },
        },
    }
    events = module._extract_streamelements_events(parsed)
    assert len(events) == 1
    assert events[0].event_id == "realtime-tip-1"
    assert events[0].username == "charlie"
    assert events[0].amount == Decimal("7.50")


def test_extract_streamlabs_socket_events() -> None:
    module = ThirdPartyAlertsModule(bot=None)
    payload = {
        "for": "streamlabs",
        "type": "donation",
        "message": [
            {
                "donation_id": "22",
                "name": "delta",
                "amount": "2.00",
                "currency": "USD",
                "message": "socket test",
            }
        ],
    }
    events = module._extract_streamlabs_events(payload)
    assert len(events) == 1
    assert events[0].event_id == "22"
    assert events[0].username == "delta"
    assert events[0].amount == Decimal("2.00")


def test_resolve_streamlabs_socket_token_prefers_configured_token(monkeypatch) -> None:
    module = ThirdPartyAlertsModule(bot=None)
    module.streamlabs_socket_token = "socket-abc"

    monkeypatch.setattr(
        ThirdPartyAlertsModule,
        "_streamlabs_fetch_socket_token",
        lambda self: (_ for _ in ()).throw(AssertionError("should not fetch socket token")),
    )

    assert module._resolve_streamlabs_socket_token() == "socket-abc"


class FakeBot:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[str, str]] = []
        self.say_messages: list[str] = []

    def send_message(self, message: str, method: str = "say") -> None:
        self.sent_messages.append((method, message))

    def say(self, message: str) -> None:
        self.say_messages.append(message)


def test_fixed_tip_amount_bucket_uses_bucket_message_type() -> None:
    module = ThirdPartyAlertsModule(bot=None)
    module.settings = module.default_settings.copy()
    module.settings["chat_alert_tip_enabled"] = True
    module.settings["tip_amount_50_message"] = "bucket50 {amount}"
    module.settings["tip_amount_50_message_type"] = "announce"
    module.bot = FakeBot()

    event = ExternalTipEvent(
        event_id="id-2",
        username="bob",
        amount=Decimal("60"),
        currency="USD",
        message="big",
        provider="Streamlabs",
    )
    module._handle_tip_event(event)

    assert module.bot.sent_messages == [("announce", "bucket50 60")]


def test_fixed_tip_amount_bucket_does_not_fallback_to_lower_bucket_message() -> None:
    module = ThirdPartyAlertsModule(bot=None)
    module.settings = module.default_settings.copy()
    module.settings["chat_alert_tip_enabled"] = True
    module.settings["tip_amount_1_message"] = "bucket1 {amount}"
    module.settings["tip_amount_1_message_type"] = "announce"
    module.settings["tip_amount_50_message"] = ""
    module.settings["tip_amount_50_message_type"] = "me"
    module.bot = FakeBot()

    event = ExternalTipEvent(
        event_id="id-3",
        username="echo",
        amount=Decimal("60"),
        currency="USD",
        message="test",
        provider="Streamlabs",
    )
    module._handle_tip_event(event)

    assert module.bot.sent_messages == []


def test_tip_thank_you_message_still_sends_if_points_grant_path_fails(monkeypatch) -> None:
    module = ThirdPartyAlertsModule(bot=None)
    module.settings = module.default_settings.copy()
    module.settings["chat_alert_tip_enabled"] = True
    module.settings["tip_amount_1_message"] = "thanks {username}"
    module.settings["tip_amount_1_message_type"] = "say"
    module.bot = FakeBot()

    event = ExternalTipEvent(
        event_id="id-4",
        username="frank",
        amount=Decimal("3"),
        currency="USD",
        message="hello",
        provider="Streamlabs",
    )

    def broken_grant(_event):
        raise RuntimeError("points path failed")

    monkeypatch.setattr(module, "_grant_points_for_tip", broken_grant)
    module._handle_tip_event(event)

    assert module.bot.sent_messages == [("say", "thanks frank")]


def test_grant_points_message_off_does_not_send_literal_message(monkeypatch) -> None:
    module = ThirdPartyAlertsModule(bot=None)
    module.settings = module.default_settings.copy()
    module.settings["grant_points_per_tip"] = 100
    module.settings["grant_points_message"] = "off"
    module.bot = FakeBot()

    class DummyUser:
        def __init__(self):
            self.points = 0

    class DummySessionScope:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    event = ExternalTipEvent(
        event_id="id-5",
        username="frank",
        amount=Decimal("2"),
        currency="USD",
        message="hello",
        provider="Streamlabs",
    )

    monkeypatch.setattr("pajbot.modules.chat_alerts.third_party_alerts.DBManager.create_session_scope", lambda: DummySessionScope())
    monkeypatch.setattr("pajbot.modules.chat_alerts.third_party_alerts.User.find_by_user_input", lambda _db, _name: DummyUser())

    module._grant_points_for_tip(event)
    assert module.bot.say_messages == []
