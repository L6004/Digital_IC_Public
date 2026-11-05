"""Build-only course presentation and source explorer; safe for public export."""
from html import escape
import json
from pathlib import Path
import sys

from mkdocs.plugins import event_priority
from mkdocs.structure.files import File, InclusionLevel

# Both the source checkout and the standalone public repository use this hook.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from course_display import load_policy, presentation
from courses import (discover_courses, document_title, relative_link, download_path,
                     CODE_PAGE, CATALOG_MARKER, RESOURCES_MARKER, render_catalog, render_resources)


class Download(File):
    def is_documentation_page(self):
        return False


def _prune_nav(items, excluded):
    result = []
    for item in items or []:
        if isinstance(item, str):
            if item not in excluded:
                result.append(item)
        elif isinstance(item, dict):
            for title, target in item.items():
                if isinstance(target, list):
                    children = _prune_nav(target, excluded)
                    if children:
                        result.append({title: children})
                elif target not in excluded:
                    result.append({title: target})
    return result


def _add_code_navigation(items, home, source):
    """Keep generated viewers inside their course's active navigation branch."""
    if any(item == source or isinstance(item, dict) and source in item.values() for item in items or []):
        return True
    for index, item in enumerate(items or []):
        if item == home:
            items.insert(index + 1, {"参考代码": source})
            return True
        if isinstance(item, dict):
            for title, target in item.items():
                if isinstance(target, list):
                    if _add_code_navigation(target, home, source):
                        return True
                elif target == home:
                    item[title] = [home, {"参考代码": source}]
                    return True
    return False


def _download(files, config, path):
    docs = Path(config["docs_dir"])
    relative = download_path(path, docs).relative_to(docs).as_posix()
    if not files.get_file_from_path(relative):
        files.append(Download.generated(config, relative, content=path.read_bytes()))
    return files.get_file_from_path(relative)


def _landing(path, display, files, config):
    docs = Path(config["docs_dir"])
    asset = _download(files, config, path)
    title = document_title(path)
    body = f'<h1>{escape(str(title))}</h1>\n\n'
    body += f'[下载 Markdown 源文件]({relative_link(docs / asset.src_uri, path)}){{ download="{escape(path.name, quote=True)}" }}\n\n'
    if display["mode"] == "pdf":
        pdf = files.get_file_from_path(display["pdf"])
        source = files.get_file_from_path(path.relative_to(docs).as_posix())
        if pdf is None:
            raise ValueError(f'{path.name}: 关联 PDF 未包含在本次构建中')
        url = escape(pdf.url_relative_to(source), quote=True)
        body += f'<div class="course-pdf-actions"><a href="{url}" target="_blank" rel="noopener">在新窗口打开 PDF</a> · <a href="{url}" download>下载 PDF</a></div>\n'
        body += f'<iframe class="course-pdf-viewer" src="{url}" title="{escape(str(title), quote=True)} PDF"></iframe>\n'
    else:
        body += '此文件作为源文件提供下载，不渲染 Markdown 正文。\n'
    return '---\nsearch:\n  exclude: true\n---\n\n' + body


@event_priority(-20)
def on_files(files, config):
    docs = Path(config["docs_dir"]).resolve()
    policy = load_policy(docs)
    excluded = set()
    for file in list(files):
        if not file.src_uri.startswith("50_courses/") or not file.is_documentation_page():
            continue
        path = docs / file.src_uri
        if not path.is_file():
            continue
        display = presentation(path, docs, policy)
        if display["mode"] == "hidden":
            excluded.add(file.src_uri)
            files.remove(file)
        elif display["mode"] in {"download", "pdf"}:
            file.content_string = _landing(path, display, files, config)
            if display["mode"] == "download":
                excluded.add(file.src_uri)
                file.inclusion = InclusionLevel.NOT_IN_NAV
    config["nav"] = _prune_nav(config.get("nav"), excluded)
    for course in discover_courses(docs):
        items = course["resources"]["code"]
        if not items:
            continue
        source = course["path"].with_name(CODE_PAGE).relative_to(docs).as_posix()
        if files.get_file_from_path(source):
            raise ValueError(f"代码查看页名称被占用：{source}")
        page = File.generated(config, source, content="", inclusion=InclusionLevel.NOT_IN_NAV)
        manifest = []
        for item in items:
            path = item["path"]
            raw = _download(files, config, path) if path.suffix.lower() == ".md" else files.get_file_from_path(path.relative_to(docs).as_posix())
            if raw is None or not raw.inclusion.is_included():
                continue
            text, encoding = None, "utf-8"
            if path.stat().st_size <= 2 * 1024 * 1024 and path.suffix.lower() != ".zip":
                raw_bytes = path.read_bytes()
                encodings = ["utf-16"] if raw_bytes.startswith((b'\xff\xfe', b'\xfe\xff')) else ["utf-8-sig", "gb18030"]
                for candidate in encodings:
                    try:
                        decoded = raw_bytes.decode(candidate)
                        if any(ord(char) < 32 and char not in '\t\r\n\f' for char in decoded):
                            break
                        text = decoded
                        encoding = "utf-8" if candidate == "utf-8-sig" else ("utf-16be" if raw_bytes.startswith(b'\xfe\xff') else "utf-16le") if candidate == "utf-16" else candidate
                        break
                    except UnicodeDecodeError:
                        continue
            manifest.append({"path": path.relative_to(course["path"].parent / "code").as_posix(),
                             "url": raw.url_relative_to(page), "size": path.stat().st_size,
                             "preview": text is not None, "encoding": encoding})
        data_path = source.removesuffix(".md") + ".json"
        data = File.generated(config, data_path, content=json.dumps(manifest, ensure_ascii=False))
        files.append(data)
        page.content_string = ('---\ntitle: 参考代码\nsearch:\n  exclude: true\nhide: [toc]\n---\n\n'
                               f'<h1>{escape(str(course["title"]))} · 参考代码</h1>\n'
                               f'<div class="course-code-viewer" data-manifest="{escape(data.url_relative_to(page), quote=True)}" tabindex="-1">'
                               '<p role="status">正在载入代码目录…</p></div>\n')
        files.append(page)
        _add_code_navigation(config.get("nav"), course["path"].relative_to(docs).as_posix(), source)
    return files


def on_page_markdown(markdown, page, config, files):
    # Locally the navigation hook may already replace these markers.
    if CATALOG_MARKER not in markdown and RESOURCES_MARKER not in markdown:
        return markdown
    docs = Path(config["docs_dir"])
    courses = discover_courses(docs)
    if page.file.src_uri == "50_courses/index.md":
        return markdown.replace(CATALOG_MARKER, render_catalog(courses, docs / page.file.src_uri))
    for course in courses:
        if course["path"].relative_to(docs).as_posix() == page.file.src_uri:
            return markdown.replace(RESOURCES_MARKER, render_resources(course, config["use_directory_urls"]))
    return markdown


def on_serve(server, config, builder):
    policy = Path(config["docs_dir"]).parent / "course-display.yml"
    if policy.exists():
        server.watch(str(policy))
    return server
