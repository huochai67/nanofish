from src.plugins.media_parser.parsers.twitter import TwitterParser, VxTwitterResponse


def test_twitter_parser_extracts_stats() -> None:
    result = TwitterParser()._collect_result(
        VxTwitterResponse(
            article=None,
            date_epoch=1_785_100_611,
            fetched_on=1_785_133_440,
            likes=1_372,
            replies=46,
            retweets=162,
            text="post",
            user_name="viramimoza",
            user_screen_name="viramimoza",
            user_profile_image_url="",
        )
    )

    assert result.extra["stats"] == {"reply": 46, "share": 162, "like": 1_372}


def test_twitter_parser_preserves_post_urls() -> None:
    quoted_url = "https://x.com/quoted/status/2"
    result = TwitterParser()._collect_result(
        VxTwitterResponse(
            article=None,
            date_epoch=1_785_100_611,
            fetched_on=1_785_133_440,
            likes=1,
            text="post",
            user_name="author",
            user_screen_name="author",
            user_profile_image_url="",
            qrt=VxTwitterResponse(
                article=None,
                date_epoch=1_785_100_610,
                fetched_on=1_785_133_440,
                likes=1,
                text="quoted post",
                user_name="quoted",
                user_screen_name="quoted",
                user_profile_image_url="",
            ),
            qrtURL=quoted_url,
        ),
        "https://x.com/author/status/1",
    )

    assert result.url == "https://x.com/author/status/1"
    assert result.repost is not None
    assert result.repost.url == quoted_url
