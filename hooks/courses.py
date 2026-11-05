"""Discover course folders and render catalogs from the files already on disk."""
from __future__ import annotations

import logging
import os
import re
from html import escape
from pathlib import Path
from urllib.parse import quote

try:
    from scripts.course_display import split_document, load_policy, presentation
except ModuleNotFoundError:  # Standalone public export.
    from course_display import split_document, load_policy, presentation

LOG = logging.getLogger("mkdocs.plugins.courses")
COURSES_DIR = "50_courses"
CATALOG_MARKER = "<!-- course-catalog -->"
RESOURCES_MARKER = "<!-- course-resources -->"
CODE_PAGE = "course-code.md"
SECTIONS = {
    "notes": ("知识整理", {".md", ".pdf"}),
    "assignments": ("作业参考", {".md", ".pdf", ".zip"}),
    "code": ("参考代码", {
        ".md", ".v", ".sv", ".vh", ".svh", ".vhd", ".vhdl", ".py", ".c", ".h",
        ".cpp", ".hpp", ".tcl", ".sdc", ".xdc", ".m", ".ipynb", ".s", ".asm",
        ".sh", ".ps1", ".bat", ".cmd", ".txt", ".json", ".yaml", ".yml", ".toml",
        ".csv", ".hex", ".mem", ".zip", ".cmake",
    }),
}


def markdown_text(value):
    """Treat metadata and filenames as text, even inside Markdown tables/links."""
    text = escape(" ".join(str(value).split()), quote=False)
    return re.sub(r"([\\`*_{\}\[\]()#!|])", r"\\\1", text)


def relative_link(target, page):
    return quote(Path(os.path.relpath(target, page.parent)).as_posix(), safe="/.-_")


def document_title(path):
    meta, body = split_document(path.read_text(encoding="utf-8-sig"))
    return meta.get("title") or next(
        (line[2:].strip() for line in body.splitlines() if line.startswith("# ")), path.stem
    )


def discover_courses(docs_dir):
    docs_dir = Path(docs_dir).resolve()
    root = docs_dir / COURSES_DIR
    if not root.is_dir():
        return []
    courses = []
    policy = load_policy(docs_dir)
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or folder.name.startswith((".", "_")):
            continue
        if not folder.resolve().is_relative_to(root.resolve()):
            continue
        index = folder / "index.md"
        if not index.is_file():
            LOG.warning("课程目录缺少 index.md，未加入课程页：%s", folder)
            continue
        meta, _ = split_document(index.read_text(encoding="utf-8-sig"))
        order = meta.get("course_order", 100)
        if type(order) is not int:
            raise ValueError(f"{index}: course_order 必须为整数")
        resources = {}
        for section, (_, suffixes) in SECTIONS.items():
            items = []
            for path in sorted((folder / section).rglob("*")):
                if not path.is_file() or any(part.startswith((".", "_")) for part in path.relative_to(folder).parts):
                    continue
                if not path.resolve().is_relative_to(docs_dir):
                    continue
                if path.suffix.lower() not in suffixes and not (section == "code" and path.name in {"Makefile", "CMakeLists.txt"}):
                    continue
                display = presentation(path, docs_dir, policy)
                if display["mode"] == "hidden":
                    continue
                items.append({"path": path, "title": document_title(path) if path.suffix.lower() == ".md" else path.stem,
                              "display": display})
            linked_pdfs = {item["display"]["pdf"] for item in items if item["display"]["pdf"]}
            items = [item for item in items if item["path"].relative_to(docs_dir).as_posix() not in linked_pdfs]
            resources[section] = items
        courses.append({
            "path": index, "title": document_title(index),
            "description": meta.get("description", "课程知识整理与作业参考。"),
            "semester": meta.get("semester", ""), "order": order,
            "example": meta.get("example") is True, "resources": resources,
            "docs_dir": docs_dir,
        })
    return sorted(courses, key=lambda course: (course["order"], str(course["title"]), course["path"].as_posix()))


def render_catalog(courses, page):
    if not courses:
        return "课程资料正在整理中，后续会在这里按课程展示。\n"
    totals = {section: sum(len(course["resources"][section]) for course in courses) for section in SECTIONS}
    lines = [
        f"**{len(courses)} 门课程** · {totals['notes']} 份知识整理 · {totals['assignments']} 份作业参考 · {totals['code']} 份源码资料",
        "", '<div class="grid cards course-cards" markdown>', "",
    ]
    for course in courses:
        link = relative_link(course["path"], page)
        lines += [f"-   ### [{markdown_text(course['title'])}]({link})", ""]
        badges = (["示例课程"] if course["example"] else []) + ([markdown_text(course["semester"])] if course["semester"] else [])
        if badges:
            lines += ["    **" + " · ".join(badges) + "**", ""]
        lines += [f"    {markdown_text(course['description'])}", "", "    ---", ""]
        counts = " · ".join(f"{label} {len(course['resources'][section])}" for section, label in (("notes", "笔记"), ("assignments", "作业"), ("code", "源码")))
        lines += [f"    {counts}", "", f"    [进入课程 →]({link})", ""]
    lines += ["</div>", ""]
    return "\n".join(lines)


def render_resources(course, use_directory_urls=True):
    lines = []
    for section, (title, _) in SECTIONS.items():
        lines += [f"## {title}", ""]
        items = course["resources"][section]
        if not items:
            lines += ["资料整理中。", ""]
            continue
        if section == "code":
            lines += [render_code_tree(course, use_directory_urls), ""]
            continue
        lines += ["| 资料 | 格式 | 位置 |", "| --- | --- | --- |"]
        for item in items:
            path = item["path"]
            is_markdown = path.suffix.lower() == ".md"
            label = markdown_text(item["title"] if is_markdown else path.name)
            kind = "Markdown" if is_markdown else path.suffix.lstrip(".").upper() or "源码"
            display = item.get("display", {"mode": "article"})
            link = relative_link(path, course["path"])
            attributes = ""
            if display["mode"] == "download":
                link = relative_link(download_path(path, course["docs_dir"]), course["path"])
                label += "（下载）"
                attributes = '{ download="' + escape(path.name, quote=True) + '" }'
            elif display["mode"] == "pdf":
                kind = "PDF · Markdown 下载"
            location = markdown_text(path.relative_to(course["path"].parent / section).as_posix())
            lines.append(f"| [{label}]({link}){attributes} | {kind} | {location} |")
        lines.append("")
    return "\n".join(lines)


def download_path(path, docs):
    return Path(docs) / "course-downloads" / Path(path).relative_to(docs)


def render_code_tree(course, use_directory_urls=True):
    root = {}
    for item in course["resources"]["code"]:
        node = root
        parts = item["path"].relative_to(course["path"].parent / "code").parts
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = item

    def render(node):
        rows = ['<ul class="course-file-tree">']
        for name, child in sorted(node.items(), key=lambda pair: (isinstance(pair[1].get("path"), Path), pair[0].casefold())):
            label = escape(name)
            if not isinstance(child.get("path"), Path):
                rows += [f'<li><details open><summary><span aria-hidden="true">▱</span> {label}</summary>', render(child), '</details></li>']
            else:
                relative = child["path"].relative_to(course["path"].parent / "code").as_posix()
                link = CODE_PAGE.removesuffix(".md") + ("/" if use_directory_urls else ".html") + "?file=" + quote(relative, safe="")
                rows.append(f'<li><a href="{escape(link, quote=True)}">{label}</a></li>')
        return "\n".join([*rows, '</ul>'])
    return '<div class="course-code-tree">\n' + render(root) + '\n</div>'


def insert_catalog(markdown, marker, content):
    return markdown.replace(marker, content) if marker in markdown else markdown.rstrip() + "\n\n" + content
