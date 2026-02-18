from pajbot.modules.raffle import RaffleModule


def build_module() -> RaffleModule:
    module = RaffleModule(bot=None)
    module.settings = module.default_settings.copy()
    return module


def test_default_join_command_is_not_join() -> None:
    module = build_module()
    assert module._get_join_command_alias() == "joinraffle"
    assert module._get_join_command_display() == "!joinraffle"


def test_configured_join_command_is_sanitized() -> None:
    module = build_module()
    module.settings["join_command"] = "!Join-Me NOW"
    assert module._get_join_command_alias() == "joinmenow"
    assert module._get_join_command_display() == "!joinmenow"


def test_phrase_formatting_rewrites_legacy_join_reference() -> None:
    module = build_module()
    module.settings["join_command"] = "rafflein"
    module.settings["message_start"] = "A raffle has begun. Type !join to enter."
    phrase = module._format_raffle_phrase("message_start", length=60, points=100)
    assert phrase == "A raffle has begun. Type !rafflein to enter."


def test_phrase_formatting_supports_join_command_placeholder() -> None:
    module = build_module()
    module.settings["join_command"] = "rafflein"
    module.settings["message_start"] = "A raffle has begun. Type {join_command} to enter."
    phrase = module._format_raffle_phrase("message_start", length=60, points=100)
    assert phrase == "A raffle has begun. Type !rafflein to enter."
