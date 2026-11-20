"""Small content preparation helpers shared by the importer and card renderer."""
from html.parser import HTMLParser

import nh3

SEMANTIC_TAGS = {"p", "br", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "strong", "em", "b", "i", "blockquote", "a", "code", "pre", "hr"}


def _clean_html(value, tags):
    return nh3.clean(
        value or "", tags=tags, attributes={"a": {"href", "title"}},
        url_schemes={"http", "https", "mailto"}, clean_content_tags={"script", "style", "iframe", "object"},
        strip_comments=True, link_rel="noopener noreferrer",
    )


def sanitize_html(value):
    return _clean_html(value, SEMANTIC_TAGS)


class _Text(HTMLParser):
    block_tags = {"p", "br", "div", "section", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "hr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in self.block_tags:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in self.block_tags:
            self.parts.append(" ")


def plain_text(value):
    parser = _Text()
    # Keep block boundaries until extraction so adjacent headings/divs do not
    # collapse into one word when tags outside the stored allowlist disappear.
    parser.feed(_clean_html(value, SEMANTIC_TAGS | _Text.block_tags))
    parser.close()
    return " ".join("".join(parser.parts).split())


def shorten(value, limit):
    if len(value) <= limit:
        return value
    prefix = value[:limit - 1]
    if not value[limit - 1].isspace() and not prefix.endswith(" "):
        prefix = prefix.rsplit(" ", 1)[0] if " " in prefix else ""
    return prefix.rstrip() + "…"


def short_description(excerpt, body):
    return shorten(plain_text(excerpt) or plain_text(body), 500)
