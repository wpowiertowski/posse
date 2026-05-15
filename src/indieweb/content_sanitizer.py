"""
Allowlist sanitizer for webmention e-content.

Webmentions arrive with HTML extracted from arbitrary third-party sites.
The Ghost theme widget sanitizes again before rendering, but storing
already-cleaned content guards against:

- Stored XSS if the theme is replaced or another consumer reads the
  /api/webmentions JSON directly.
- Reliability bugs where mf2py over-extracts content and pulls in
  JSON-LD, inline CSS, or other non-display markup from <script> /
  <style> elements, breaking the rendered formatting.

The allowlist (p, br, a, strong, em, blockquote, code, pre) matches the
widget's ``sanitizeWebmentionHtmlContent`` so server-side and
client-side filtering stay aligned.
"""

from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse

_ALLOWED_TAGS = frozenset({"p", "br", "a", "strong", "em", "blockquote", "code", "pre"})
_VOID_TAGS = frozenset({"br"})
# Tags whose body content should be discarded entirely, not surfaced as
# text. mf2py's e-content extraction can scoop up JSON-LD or inline CSS
# from these, which then leaks into the rendered reply.
_DROP_CONTENT_TAGS = frozenset({"script", "style"})


class _ContentSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._drop_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if self._drop_depth:
            if tag in _DROP_CONTENT_TAGS:
                self._drop_depth += 1
            return

        if tag in _DROP_CONTENT_TAGS:
            self._drop_depth = 1
            return

        if tag not in _ALLOWED_TAGS:
            return

        if tag == "a":
            href = _safe_href(dict(attrs).get("href"))
            if href:
                self._parts.append(
                    f'<a href="{escape(href, quote=True)}" '
                    f'rel="nofollow noopener noreferrer">'
                )
            else:
                self._parts.append("<a>")
        else:
            self._parts.append(f"<{tag}>")

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        if self._drop_depth:
            return
        if tag in _VOID_TAGS:
            self._parts.append(f"<{tag}>")
        elif tag in _ALLOWED_TAGS:
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if self._drop_depth:
            if tag in _DROP_CONTENT_TAGS:
                self._drop_depth = max(0, self._drop_depth - 1)
            return
        if tag in _ALLOWED_TAGS and tag not in _VOID_TAGS:
            self._parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._drop_depth:
            return
        self._parts.append(escape(data, quote=False))

    def result(self) -> str:
        # If parsing left us inside an unterminated <script>/<style>,
        # discard nothing further — the input was malformed.
        return "".join(self._parts)


def _safe_href(href) -> str:
    if not href or not isinstance(href, str):
        return ""
    href = href.strip()
    if not href:
        return ""
    try:
        parsed = urlparse(href)
    except ValueError:
        return ""
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    return href


def sanitize_content_html(html_input: str) -> str:
    """Return HTML containing only a small allowlist of formatting tags.

    Disallowed tags are dropped but their text content is preserved,
    except for ``<script>`` and ``<style>`` whose entire body is
    discarded. All attributes are stripped except ``href`` on ``<a>``,
    which is restricted to ``http``/``https``.
    """
    if not html_input:
        return ""

    parser = _ContentSanitizer()
    try:
        parser.feed(html_input)
        parser.close()
    except Exception:
        return escape(html_input, quote=False)
    return parser.result()


def sanitize_content_text(text_input: str) -> str:
    """Return plain text with all HTML tags stripped.

    Used for the ``content_text`` field which is supposed to be the
    plain-text rendering of a reply but may still contain stray markup
    from over-eager mf2py extraction (e.g. JSON-LD payloads).
    """
    if not text_input:
        return ""

    class _TextOnly(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self._parts: list[str] = []
            self._drop_depth = 0

        def handle_starttag(self, tag: str, attrs: list) -> None:
            if tag in _DROP_CONTENT_TAGS:
                self._drop_depth += 1

        def handle_endtag(self, tag: str) -> None:
            if tag in _DROP_CONTENT_TAGS and self._drop_depth:
                self._drop_depth -= 1

        def handle_data(self, data: str) -> None:
            if self._drop_depth:
                return
            self._parts.append(data)

    parser = _TextOnly()
    try:
        parser.feed(text_input)
        parser.close()
    except Exception:
        return text_input
    return "".join(parser._parts)
