"""Configure math and diagrams without changing the Markdown sources."""
import re
import xml.etree.ElementTree as ET

from markdown.blockprocessors import BlockProcessor, BlockQuoteProcessor, ListIndentProcessor
from markdown.extensions import Extension
from markdown.extensions.tables import TableProcessor
from markdown.preprocessors import Preprocessor
from pymdownx.superfences import fence_code_format


class QuotedTabIndentation(Preprocessor):
    """Count indentation tabs from the quote's content, as Typora does."""

    quote = re.compile(r"^[ ]{0,3}>[ ]?")
    fence = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
    raw = re.compile(r"^[ \t]*<(pre|code|script|style|textarea)(?:\s|>)", re.I)

    def split_quotes(self, line, limit=None):
        prefixes = []
        while limit is None or len(prefixes) < limit:
            match = self.quote.match(line)
            if not match:
                break
            prefixes.append(match[0])
            line = line[match.end():]
            # Only structural indentation changes. Tabs in prose/TeX stay
            # with Markdown's normal whitespace handling.
            indent = re.match(r"[ \t]*", line)[0]
            line = indent.expandtabs(self.md.tab_length) + line[len(indent):]
        return ''.join(prefixes), line, len(prefixes)

    def run(self, lines):
        output = []
        fenced = None
        raw = None
        for line in lines:
            limit = fenced[2] if fenced else raw[1] if raw else None
            prefix, content, depth = self.split_quotes(line, limit)
            output.append(prefix + content)
            if raw:
                if re.search(r"</" + raw[0] + r"\s*>", content, re.I):
                    raw = None
                continue
            match = self.fence.match(content)
            if fenced:
                if match and match[1][0] == fenced[0] and len(match[1]) >= fenced[1] and not match[2].strip():
                    fenced = None
            elif match:
                fenced = (match[1][0], len(match[1]), depth)
            else:
                match = self.raw.match(content)
                if match and not re.search(r"</" + match[1] + r"\s*>", content, re.I):
                    raw = (match[1], depth)
        return output


class GitHubAlertProcessor(BlockQuoteProcessor):
    """Reuse Material's accessible admonition styling for Typora/GitHub alerts."""

    marker = re.compile(r"^[ ]{0,3}>[ ]?\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\][ \t]*(?:\n|$)", re.I)
    styles = {'note': 'note', 'tip': 'tip', 'important': 'example',
              'warning': 'warning', 'caution': 'danger'}

    def test(self, parent, block):
        return bool(self.marker.match(block))

    def run(self, parent, blocks):
        block = blocks.pop(0)
        match = self.marker.match(block)
        kind = match[1].lower()
        alert = ET.SubElement(parent, 'div', {
            'class': f'admonition {self.styles[kind]} github-alert-{kind}', 'role': 'note'})
        ET.SubElement(alert, 'p', {'class': 'admonition-title'}).text = kind.capitalize()
        content = '\n'.join(self.clean(line) for line in block[match.end():].split('\n'))
        self.parser.state.set('blockquote')
        self.parser.parseChunk(alert, content)
        self.parser.state.reset()


class QuotedContentExtension(Extension):
    def extendMarkdown(self, md):
        md.preprocessors.register(QuotedTabIndentation(md), 'quoted_tab_indentation', 31)
        md.parser.blockprocessors.register(GitHubAlertProcessor(md.parser), 'github_alerts', 20.1)


class MathBlockSpacing(Preprocessor):
    # At this priority fenced code and raw HTML are already protected by
    # Markdown placeholders. Preserve container indentation so list processors
    # can remove it before the math renderer runs; standalone code stays code.
    delimiter = re.compile(r"^(?P<quote>(?:[ ]{0,3}>[ \t]?)*)?(?P<indent>[ ]*)\$\$[ \t]*$")

    def run(self, lines):
        result = []
        opening = None
        for index, line in enumerate(lines):
            if opening is not None and line.strip() and not line.startswith(opening[1]):
                opening = None
            match = self.delimiter.fullmatch(line)
            if not match:
                continue
            quote = (match.group("quote") or "") + match.group("indent")
            if opening is None:
                opening = (index, quote)
            elif quote == opening[1]:
                result.append((opening[0], index, quote))
                opening = None
        before = {start: quote for start, _, quote in result}
        after = {end: quote for _, end, quote in result}
        spaced = []
        for index, line in enumerate(lines):
            if index in before:
                spaced.append(before[index].rstrip())
            spaced.append(line)
            if index in after:
                spaced.append(after[index].rstrip())
        return spaced


class MultilineMathBlockProcessor(BlockProcessor):
    """Pass a complete $$ block to Arithmatex, including internal blank lines."""

    opening = re.compile(r"^\$\$[ \t]*(?:\n|$)")
    closing = re.compile(r"^\$\$[ \t]*$", re.MULTILINE)

    def __init__(self, parser, renderer):
        super().__init__(parser)
        self.renderer = renderer

    def test(self, parent, block):
        return bool(self.opening.match(block)) and not self.renderer.test(parent, block)

    def run(self, parent, blocks):
        for index, block in enumerate(blocks[1:], 1):
            closing = self.closing.search(block)
            if closing is None:
                continue
            complete = "\n\n".join([*blocks[:index], block[:closing.end()]])
            if not self.renderer.test(parent, complete):
                return False
            # Keep the configured renderer's wrappers and TeX escaping behavior.
            self.renderer.run(parent, [complete])
            del blocks[:index + 1]
            remainder = block[closing.end():].lstrip("\n")
            if remainder:
                blocks.insert(0, remainder)
            return True
        return False


class MathListIndentProcessor(ListIndentProcessor):
    """Keep a multi-paragraph formula together when descending into a list."""

    def run(self, parent, blocks):
        level, _ = self.get_level(parent, blocks[0])
        prefix = " " * (self.tab_length * level)
        opening = re.compile(r"^" + prefix + r"\$\$[ \t]*(?:\n|$)")
        closing = re.compile(r"^" + prefix + r"\$\$[ \t]*$", re.MULTILINE)
        match = opening.match(blocks[0])
        if match and not closing.search(blocks[0], match.end()):
            for index, block in enumerate(blocks):
                # A dedent ends this list's math candidate. Do not capture a
                # later formula from another item, or indented literal code.
                if any(line.strip() and not line.startswith(prefix) for line in block.splitlines()):
                    break
                if index and closing.search(block):
                    blocks[:index + 1] = ["\n\n".join(blocks[:index + 1])]
                    break
        return super().run(parent, blocks)


class MathBlockSpacingExtension(Extension):
    def extendMarkdown(self, md):
        md.preprocessors.register(MathBlockSpacing(md), "math_block_spacing", 15)
        if "arithmatex-block" in md.parser.blockprocessors:
            renderer = md.parser.blockprocessors["arithmatex-block"]
            md.parser.blockprocessors.register(
                MultilineMathBlockProcessor(md.parser, renderer), "multiline_math_block", 79.95)
            md.parser.blockprocessors.register(MathListIndentProcessor(md.parser), "indent", 90)


class MathTableProcessor(TableProcessor):
    """Protect TeX pipes during cell splitting, then return the original TeX."""

    def _split(self, row):
        patterns = self.parser.md.inlinePatterns
        if "|" not in row or "arithmatex-inline" not in patterns:
            return super()._split(row)
        # Inline code takes precedence over math. Mask it only for detection so
        # a literal dollar inside code cannot capture a later cell delimiter.
        scan = list(row)
        if "backtick" in patterns:
            for match in patterns["backtick"].getCompiledRegExp().finditer(row):
                scan[match.start():match.end()] = "\x02" * (match.end() - match.start())
        protected = list(row)
        marker = "\x00"
        while marker in row:
            marker += "\x00"
        # Use the configured math renderer's own delimiter and escape rules.
        pattern = patterns["arithmatex-inline"].getCompiledRegExp()
        for match in pattern.finditer("".join(scan)):
            for index in range(match.start(), match.end()):
                if row[index] == "|":
                    protected[index] = marker
        return [cell.replace(marker, "|") for cell in super()._split("".join(protected))]


class MathTableExtension(Extension):
    def extendMarkdown(self, md):
        if "table" in md.parser.blockprocessors:
            original = md.parser.blockprocessors["table"]
            if isinstance(original, TableProcessor):
                md.parser.blockprocessors.register(MathTableProcessor(md.parser, original.config), "table", 75)


def on_config(config):
    for extension_type in (QuotedContentExtension, MathBlockSpacingExtension, MathTableExtension):
        if not any(isinstance(extension, extension_type) for extension in config["markdown_extensions"]):
            config["markdown_extensions"].append(extension_type())
    fences = config["mdx_configs"].setdefault("pymdownx.superfences", {}).setdefault("custom_fences", [])
    if not any(fence.get("name") == "mermaid" for fence in fences):
        fences.append({"name": "mermaid", "class": "mermaid", "format": fence_code_format})
    languages = config["mdx_configs"].setdefault("pymdownx.highlight", {}).setdefault("extend_pygments_lang", [])
    if not any(language.get("name") == "assembly" for language in languages):
        languages.append({"name": "assembly", "lang": "gas"})
    return config
