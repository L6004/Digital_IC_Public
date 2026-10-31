"""Configure math and diagrams without changing the Markdown sources."""
import re

from markdown.extensions import Extension
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


class MathBlockSpacingExtension(Extension):
    def extendMarkdown(self, md):
        md.preprocessors.register(MathBlockSpacing(md), "math_block_spacing", 15)


def on_config(config):
    if not any(isinstance(extension, MathBlockSpacingExtension) for extension in config["markdown_extensions"]):
        config["markdown_extensions"].append(MathBlockSpacingExtension())
    fences = config["mdx_configs"].setdefault("pymdownx.superfences", {}).setdefault("custom_fences", [])
    if not any(fence.get("name") == "mermaid" for fence in fences):
        fences.append({"name": "mermaid", "class": "mermaid", "format": fence_code_format})
    return config
