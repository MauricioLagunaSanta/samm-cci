import sys
import types

from app.extraction import url_tools


def _fake_decoder(result):
    mod = types.ModuleType("googlenewsdecoder")
    mod.gnewsdecoder = lambda url, interval=None: result
    return mod


def test_resolver_formato_success(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "googlenewsdecoder", _fake_decoder({"success": True, "decoded_url": "https://m.com/a"})
    )
    assert url_tools.resolve_google_news_url("https://news.google.com/rss/articles/X") == "https://m.com/a"


def test_resolver_formato_antiguo_status(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "googlenewsdecoder", _fake_decoder({"status": True, "decoded_url": "https://m.com/b"})
    )
    assert url_tools.resolve_google_news_url("https://news.google.com/rss/articles/X") == "https://m.com/b"


def test_resolver_falla_devuelve_none(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "googlenewsdecoder", _fake_decoder({"success": False, "message": "x"})
    )
    assert url_tools.resolve_google_news_url("https://news.google.com/rss/articles/X") is None
