import pytest

from utils.helpers import contains_bot_mention, should_respond_to_message


@pytest.mark.parametrize(
    ("text", "bot_username"),
    [
        ("Привет, @example_bot!", "example_bot"),
        ("@Example_Bot, что нового?", "@example_bot"),
    ],
)
def test_exact_bot_mention_is_detected(text: str, bot_username: str) -> None:
    assert contains_bot_mention(text, bot_username)


@pytest.mark.parametrize(
    "text",
    [
        "Привет, бот",
        "Обсуждаем работу бота",
        "mail@example_bot.example",
        "@example_bot_extra",
    ],
)
def test_plain_words_and_partial_usernames_are_ignored(text: str) -> None:
    assert not contains_bot_mention(text, "example_bot")


def test_question_and_reply_still_trigger_response() -> None:
    assert should_respond_to_message("Как дела?", "example_bot", replied_to_bot=False)
    assert should_respond_to_message("Продолжай", "example_bot", replied_to_bot=True)
    assert not should_respond_to_message("Обычное сообщение", "example_bot", False)
