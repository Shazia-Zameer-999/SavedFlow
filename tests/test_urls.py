from utils.urls import (
    extract_shortcode,
    is_valid_instagram_url,
    normalize_instagram_url,
)


def test_plain_instagram_reel_url():
    url = "https://www.instagram.com/ere.plays/reel/Db4y6J0PG86/"

    assert is_valid_instagram_url(url) is True
    assert extract_shortcode(url) == "Db4y6J0PG86"
    assert normalize_instagram_url(url) == (
        "https://instagram.com/reel/Db4y6J0PG86"
    )


def test_markdown_instagram_reel_url():
    url = (
        "[https://www.instagram.com/ere.plays/reel/Db4y6J0PG86/]"
        "(https://www.instagram.com/ere.plays/reel/Db4y6J0PG86/)"
    )

    assert is_valid_instagram_url(url) is True
    assert extract_shortcode(url) == "Db4y6J0PG86"
    assert normalize_instagram_url(url) == (
        "https://instagram.com/reel/Db4y6J0PG86"
    )


def test_invalid_url():
    url = "https://example.com/not-instagram"

    assert is_valid_instagram_url(url) is False
    assert extract_shortcode(url) is None
    assert normalize_instagram_url(url) is None
