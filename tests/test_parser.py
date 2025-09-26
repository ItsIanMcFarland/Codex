import pathlib

from hotel_social_discover import parser


def test_normalize_url_removes_tracking():
    url = "https://facebook.com/page?utm_source=test&ref=home#section"
    normalized = parser.normalize_url(url)
    assert normalized == "https://facebook.com/page?ref=home"


def test_parse_social_links_detects_platforms():
    html = pathlib.Path("fixtures/sample_page.html").read_text()
    bucket, others = parser.parse_social_links(html, "https://example.com")
    assert bucket["facebook"] == ["https://www.facebook.com/samplehotel"]
    assert bucket["instagram"] == ["https://instagram.com/samplehotel"]
    assert bucket["x"] == ["https://twitter.com/samplehotel"]
    assert bucket["youtube"] == ["https://www.youtube.com/channel/abc"]
    assert bucket["linkedin"] == ["https://www.linkedin.com/company/samplehotel"]
    assert bucket["tiktok"] == ["https://tiktok.com/@samplehotel"]
    assert "https://www.pinterest.com/samplehotel" in others


def test_is_js_heavy_handles_short_content():
    assert parser.is_js_heavy("<html></html>")
