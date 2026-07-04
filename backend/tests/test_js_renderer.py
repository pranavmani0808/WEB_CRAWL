from app.crawler.js_renderer import looks_js_rendered


REACT_SHELL = """<!doctype html><html><head><title>My App</title>
<script src="/static/js/main.abc123.js"></script></head>
<body><div id="root"></div></body></html>"""

NEXT_SHELL = """<html><body><div id="__next"></div>
<script src="/_next/static/chunks/main.js"></script></body></html>"""

NOSCRIPT_PAGE = """<html><body>
<noscript>You need to enable JavaScript to run this app.</noscript>
<div class="loading"></div>
<script src="/app.js"></script></body></html>"""

SCRIPT_HEAVY_EMPTY = """<html><head>
<script src="/a.js"></script><script src="/b.js"></script>
<script src="/c.js"></script><script>window.__DATA__={}</script>
</head><body><div class="spinner"></div></body></html>"""

NORMAL_PAGE = """<html><head><title>Article</title></head><body>
<h1>A real server-rendered article</h1>
<p>""" + ("Lots of visible words here. " * 40) + """</p>
<script src="/analytics.js"></script></body></html>"""


def test_detects_react_root_shell():
    assert looks_js_rendered(REACT_SHELL, word_count=2) is True


def test_detects_next_shell():
    assert looks_js_rendered(NEXT_SHELL, word_count=0) is True


def test_detects_noscript_hint():
    assert looks_js_rendered(NOSCRIPT_PAGE, word_count=10) is True


def test_detects_script_heavy_empty_page():
    assert looks_js_rendered(SCRIPT_HEAVY_EMPTY, word_count=5) is True


def test_normal_server_rendered_page_not_flagged():
    assert looks_js_rendered(NORMAL_PAGE, word_count=250) is False


def test_high_word_count_never_flagged_even_with_shell_markup():
    # Server-rendered apps hydrate into #root/#app too - but then the div is
    # NOT empty and word count is high, so no render should happen.
    assert looks_js_rendered(REACT_SHELL, word_count=500) is False


def test_short_page_with_no_scripts_not_flagged():
    html = "<html><body><h1>404</h1><p>Not found</p></body></html>"
    assert looks_js_rendered(html, word_count=3) is False


def test_detects_inline_data_script_page():
    # Shape of quotes.toscrape.com/js: almost no visible text, one library
    # script plus one big inline script holding the page's actual data.
    html = (
        '<html><head><script src="/static/jquery.js"></script></head>'
        "<body><div class='quotes'></div><script>var data = ["
        + '{"text": "quote", "author": "someone"},' * 60
        + "];</script></body></html>"
    )
    assert looks_js_rendered(html, word_count=16) is True
