"""Resolve raw HTML image URLs at build time without rewriting source files.

Only Markdown's raw HTML stash is processed: ordinary Markdown images already
receive MkDocs' URL conversion and must not be resolved a second time.
This hook also runs in the standalone public repository.
"""
import logging
import posixpath
import re
from html import escape
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit, urlunsplit

from markdown.extensions import Extension
from markdown.postprocessors import Postprocessor
from mkdocs.utils import get_relative_url

LOG = logging.getLogger('mkdocs.plugins.html_images')
ATTRIBUTE = re.compile(r'''([^\s=<>/]+)\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)''')


class HTMLImageURLs(HTMLParser):
    def __init__(self, html, page, files):
        super().__init__(convert_charrefs=False)
        self.html, self.page, self.files = html, page, files
        self.edits = []
        self.literal = []
        self.line_offsets = [0] + [match.end() for match in re.finditer('\n', html)]

    def handle_starttag(self, tag, attrs):
        if tag in {'pre', 'code', 'script', 'style', 'textarea'}:
            self.literal.append(tag)
        if self.literal or tag != 'img':
            return
        src = dict(attrs).get('src')
        if not src:
            return
        url = urlsplit(src)
        if url.scheme or url.netloc or not url.path or url.path.startswith('/'):
            return
        source = self.page.file.src_uri
        target_path = posixpath.normpath(posixpath.join(
            posixpath.dirname(source), unquote(url.path).replace('\\', '/')))
        target = self.files.get_file_from_path(target_path)
        if target is None or not target.inclusion.is_included():
            LOG.warning('%s: HTML 图片找不到文件 %r（解析为 %s）；src 应相对于 Markdown 所在目录。',
                        source, src, target_path)
            return
        resolved = urlunsplit(('', '', get_relative_url(target.url, self.page.url), url.query, url.fragment))
        if resolved == src:
            return
        for match in ATTRIBUTE.finditer(self.get_starttag_text()):
            if match[1].lower() == 'src':
                line, column = self.getpos()
                start = self.line_offsets[line - 1] + column
                self.edits.append((start + match.start(), start + match.end(),
                                   'src="' + escape(resolved, quote=True) + '"'))
                break

    def handle_endtag(self, tag):
        if self.literal and tag == self.literal[-1]:
            self.literal.pop()

    def rewritten(self):
        self.feed(self.html)
        self.close()
        html = self.html
        for start, end, replacement in reversed(self.edits):
            html = html[:start] + replacement + html[end:]
        return html


class RawHTMLImages(Postprocessor):
    def __init__(self, md, extension):
        super().__init__(md)
        self.extension = extension
        self.stash = None
        self.processed = 0

    def run(self, text):
        if self.extension.page is not None:
            stash = self.md.htmlStash.rawHtmlBlocks
            # TOC generation also invokes postprocessors for heading labels.
            # Resolve each stash entry only once, even with many headings.
            if self.stash is not stash:
                self.stash, self.processed = stash, 0
            for index in range(self.processed, len(stash)):
                raw = stash[index]
                if isinstance(raw, str):
                    stash[index] = HTMLImageURLs(raw, self.extension.page, self.extension.files).rewritten()
            self.processed = len(stash)
        return text


class HTMLImagesExtension(Extension):
    page = None
    files = None

    def extendMarkdown(self, md):
        # Run immediately before Markdown restores raw HTML (priority 30).
        md.postprocessors.register(RawHTMLImages(md, self), 'raw_html_images', 31)


def on_config(config):
    if not any(isinstance(extension, HTMLImagesExtension) for extension in config['markdown_extensions']):
        config['markdown_extensions'].append(HTMLImagesExtension())
    return config


def on_page_markdown(markdown, page, config, files):
    for extension in config['markdown_extensions']:
        if isinstance(extension, HTMLImagesExtension):
            extension.page, extension.files = page, files
    return markdown
