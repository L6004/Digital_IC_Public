"""Configure math and diagrams without changing the Markdown sources."""
import re

from markdown.blockprocessors import BlockProcessor
from markdown.extensions import Extension
from markdown.extensions.tables import TableProcessor
from markdown.preprocessors import Preprocessor
from pymdownx.superfences import fence_code_format


class MathBlockSpacing(Preprocessor):
    # At this priority fenced code and raw HTML are already protected by
    # Markdown placeholders. Indented code is deliberately not matched.
    delimiter = re.compile(r"^(?P<quote>(?:>[ \t]?)*)[ ]{0,3}\$\$[ \t]*$")

    def run(self, lines):
        result = []
        opening = None
        for index, line in enumerate(lines):
            match = self.delimiter.fullmatch(line)
            if not match:
                continue
            quote = match.group("quote")
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


class MathBlockSpacingExtension(Extension):
    def extendMarkdown(self, md):
        md.preprocessors.register(MathBlockSpacing(md), "math_block_spacing", 15)
        if "arithmatex-block" in md.parser.blockprocessors:
            renderer = md.parser.blockprocessors["arithmatex-block"]
            md.parser.blockprocessors.register(
                MultilineMathBlockProcessor(md.parser, renderer), "multiline_math_block", 79.95)


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
    for extension_type in (MathBlockSpacingExtension, MathTableExtension):
        if not any(isinstance(extension, extension_type) for extension in config["markdown_extensions"]):
            config["markdown_extensions"].append(extension_type())
    fences = config["mdx_configs"].setdefault("pymdownx.superfences", {}).setdefault("custom_fences", [])
    if not any(fence.get("name") == "mermaid" for fence in fences):
        fences.append({"name": "mermaid", "class": "mermaid", "format": fence_code_format})
    return config
