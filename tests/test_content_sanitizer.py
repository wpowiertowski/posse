"""Tests for the webmention e-content sanitizer."""

from indieweb.content_sanitizer import (
    sanitize_content_html,
    sanitize_content_text,
)


class TestSanitizeContentHtml:
    def test_empty(self):
        assert sanitize_content_html("") == ""
        assert sanitize_content_html(None) == ""  # type: ignore[arg-type]

    def test_allowlisted_tags_preserved(self):
        html = "<p>Hello <strong>world</strong></p>"
        assert sanitize_content_html(html) == "<p>Hello <strong>world</strong></p>"

    def test_all_allowed_tags(self):
        html = (
            "<p>p <br>br <strong>s</strong> <em>e</em> "
            "<blockquote>bq</blockquote> <code>c</code> <pre>pr</pre></p>"
        )
        out = sanitize_content_html(html)
        for tag in ("<p>", "<br>", "<strong>", "<em>", "<blockquote>", "<code>", "<pre>"):
            assert tag in out

    def test_disallowed_tag_kept_as_text(self):
        html = "<p>Hello <span>nested</span> world</p>"
        assert sanitize_content_html(html) == "<p>Hello nested world</p>"

    def test_nested_div_dropped_but_inner_preserved(self):
        html = "<div><p>hi</p></div>"
        assert sanitize_content_html(html) == "<p>hi</p>"

    def test_script_content_dropped_entirely(self):
        """The bug that motivated this: JSON-LD inside <script> must not
        leak through as visible text."""
        html = (
            '<p>Real reply.</p>'
            '<script type="application/ld+json">'
            '{"@context":"https://schema.org","@type":"Person","name":"x"}'
            '</script>'
        )
        out = sanitize_content_html(html)
        assert out == "<p>Real reply.</p>"
        assert "schema.org" not in out
        assert "@context" not in out

    def test_style_content_dropped_entirely(self):
        html = "<style>.x{color:red}</style><p>hi</p>"
        assert sanitize_content_html(html) == "<p>hi</p>"

    def test_nested_script_in_disallowed_tag(self):
        html = "<div>before<script>bad()</script>after</div>"
        assert sanitize_content_html(html) == "beforeafter"

    def test_attributes_stripped(self):
        html = '<p class="x" id="y" onclick="alert(1)">hi</p>'
        assert sanitize_content_html(html) == "<p>hi</p>"

    def test_anchor_http_href_preserved(self):
        html = '<a href="https://example.com/post">link</a>'
        out = sanitize_content_html(html)
        assert 'href="https://example.com/post"' in out
        assert 'rel="nofollow noopener noreferrer"' in out

    def test_anchor_http_scheme_allowed(self):
        html = '<a href="http://example.com">link</a>'
        out = sanitize_content_html(html)
        assert 'href="http://example.com"' in out

    def test_anchor_javascript_href_dropped(self):
        html = '<a href="javascript:alert(1)">click</a>'
        out = sanitize_content_html(html)
        assert "javascript" not in out
        assert "<a>click</a>" == out

    def test_anchor_data_href_dropped(self):
        html = '<a href="data:text/html,<script>alert(1)</script>">x</a>'
        out = sanitize_content_html(html)
        assert "data:" not in out
        assert "<script>" not in out
        assert "alert" not in out

    def test_anchor_vbscript_dropped(self):
        html = '<a href="vbscript:msgbox(1)">x</a>'
        out = sanitize_content_html(html)
        assert "vbscript" not in out

    def test_anchor_relative_url_dropped(self):
        # No netloc → can't trust origin → drop
        html = '<a href="/relative/path">x</a>'
        out = sanitize_content_html(html)
        assert "relative" not in out
        assert out == "<a>x</a>"

    def test_anchor_href_quote_escaped(self):
        html = '<a href=\'https://example.com/"><script>alert(1)</script>\'>x</a>'
        out = sanitize_content_html(html)
        assert "<script>" not in out
        assert "&quot;" in out or '"' not in out.replace('href="', "").replace('">', "")

    def test_iframe_dropped(self):
        html = '<iframe src="https://evil.com"></iframe><p>hi</p>'
        assert sanitize_content_html(html) == "<p>hi</p>"

    def test_img_dropped(self):
        html = '<img src="x" onerror="alert(1)"><p>hi</p>'
        assert sanitize_content_html(html) == "<p>hi</p>"

    def test_text_html_entities_escaped(self):
        html = "<p>5 < 6 and a&b</p>"
        out = sanitize_content_html(html)
        assert "<p>" in out
        assert "&lt;" in out
        assert "&amp;" in out
        assert "</p>" in out

    def test_existing_entity_preserved_as_escaped(self):
        html = "<p>&amp;lt;</p>"
        # convert_charrefs decodes the entity to "<lt;" then re-escapes
        # the literal < as &lt;, which is still safe.
        out = sanitize_content_html(html)
        assert "<p>" in out and "</p>" in out
        assert "<lt" not in out  # the literal "<" must be escaped

    def test_html_comments_dropped(self):
        html = "<p>hi<!-- secret --></p>"
        out = sanitize_content_html(html)
        assert "secret" not in out
        assert out == "<p>hi</p>"

    def test_malformed_input_doesnt_crash(self):
        html = "<p>unclosed <strong>still <em>open"
        out = sanitize_content_html(html)
        assert "unclosed" in out
        assert "<script>" not in out

    def test_svg_with_inner_script_dropped(self):
        html = '<svg><script>alert(1)</script></svg><p>ok</p>'
        out = sanitize_content_html(html)
        assert "alert" not in out
        assert "<p>ok</p>" in out

    def test_self_closing_br(self):
        html = "<p>line1<br/>line2</p>"
        out = sanitize_content_html(html)
        assert "<br>" in out
        assert "line1" in out and "line2" in out


class TestSanitizeContentText:
    def test_empty(self):
        assert sanitize_content_text("") == ""
        assert sanitize_content_text(None) == ""  # type: ignore[arg-type]

    def test_plain_text_passthrough(self):
        assert sanitize_content_text("hello world") == "hello world"

    def test_tags_stripped(self):
        assert sanitize_content_text("<p>hello</p>") == "hello"

    def test_script_body_dropped(self):
        text = '<script type="application/ld+json">{"foo":1}</script>real text'
        assert sanitize_content_text(text) == "real text"

    def test_style_body_dropped(self):
        text = "<style>.x{color:red}</style>real text"
        assert sanitize_content_text(text) == "real text"

    def test_entities_decoded(self):
        # convert_charrefs=True decodes named entities to text
        assert sanitize_content_text("a &amp; b") == "a & b"
