"""Standalone course presentation policy, independent from publication consent."""
from pathlib import Path
import hashlib
import json
import re

import yaml

MODES = {"auto", "article", "download", "pdf", "hidden"}
POLICY_NAME = "course-display.yml"


def split_document(raw):
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", raw, re.S)
    if not match:
        return {}, raw
    meta = yaml.safe_load(match[1]) or {}
    if not isinstance(meta, dict):
        raise ValueError("文档 YAML 元数据必须是字典")
    return meta, raw[match.end():].lstrip("\n")


def checked_path(docs, relative):
    docs = Path(docs).resolve()
    if (not isinstance(relative, str) or not relative.startswith("50_courses/")
            or any(part in {"", ".", ".."} for part in relative.split("/"))
            or "\\" in relative or ":" in relative):
        raise ValueError("请使用 docs/50_courses 内的规范相对路径")
    path = docs / relative
    if not path.resolve().is_relative_to(docs):
        raise ValueError("课程路径超出文库范围")
    cursor = docs
    for part in relative.split("/"):
        cursor /= part
        if cursor.is_symlink():
            raise ValueError("课程展示设置不支持符号链接")
    return path


def validate_setting(docs, relative, setting, require_exists=False):
    path = checked_path(docs, relative)
    if path.suffix.lower() != ".md" or len(Path(relative).parts) < 3:
        raise ValueError("显示控制仅适用于课程 Markdown 文档")
    if (not isinstance(setting, dict) or set(setting) - {"mode", "pdf"}
            or setting.get("mode", "auto") not in MODES
            or not isinstance(setting.get("pdf", ""), str)):
        raise ValueError("无效的课程展示方式")
    if len(Path(relative).parts) == 3 and path.name == "index.md" and setting.get("mode", "auto") not in {"auto", "article"}:
        raise ValueError("课程主页须保持正文展示")
    if require_exists and not path.is_file():
        raise ValueError("课程文档不存在")
    pdf = setting.get("pdf", "")
    if pdf:
        target = checked_path(docs, pdf)
        if target.suffix.lower() != ".pdf" or Path(pdf).parts[:2] != Path(relative).parts[:2]:
            raise ValueError("请选择同一课程中的 PDF 文件")
        if require_exists and not target.is_file():
            raise ValueError("关联 PDF 不存在")
    if require_exists and setting.get("mode") == "pdf" and not pdf and not path.with_suffix(".pdf").is_file():
        raise ValueError("PDF 展示需要关联 PDF，或存在同名 PDF")


class PolicyLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        keys = [self.construct_object(key, deep=deep) for key, _ in node.value]
        if any(not isinstance(key, str) for key in keys) or len(keys) != len(set(keys)):
            raise ValueError("课程展示设置含重复或无效键")
        return super().construct_mapping(node, deep=deep)


def load_policy(docs):
    filename = Path(docs).resolve().parent / POLICY_NAME
    policy = yaml.load(filename.read_text(encoding="utf-8"), Loader=PolicyLoader) if filename.exists() else {"version": 1, "documents": {}}
    if (not isinstance(policy, dict) or set(policy) != {"version", "documents"}
            or type(policy["version"]) is not int or policy["version"] != 1
            or not isinstance(policy["documents"], dict)):
        raise ValueError("course-display.yml 格式无效")
    for relative, setting in policy["documents"].items():
        validate_setting(docs, relative, setting)
    return policy


def revision(setting):
    return hashlib.sha256(json.dumps(setting, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def presentation(path, docs, policy=None):
    docs = Path(docs).resolve()
    path = Path(path)
    relative = path.relative_to(docs).as_posix()
    if not relative.startswith("50_courses/") or path.suffix.lower() != ".md":
        return {"mode": "article", "pdf": "", "marp": False}
    policy = load_policy(docs) if policy is None else policy
    setting = policy["documents"].get(relative, {})
    meta, _ = split_document(path.read_text(encoding="utf-8-sig"))
    marp = meta.get("marp") is True
    mode = setting.get("mode", "auto")
    pdf = setting.get("pdf", "")
    candidate = checked_path(docs, pdf) if pdf else path.with_suffix(".pdf")
    pdf = candidate.relative_to(docs).as_posix() if candidate.is_file() else ""
    if mode == "auto":
        mode = ("pdf" if pdf else "download") if marp else "article"
    if mode == "pdf" and not pdf:
        raise ValueError(f"{relative}: PDF 展示需要已存在的关联 PDF")
    return {"mode": mode, "pdf": pdf if mode == "pdf" else "", "marp": marp}
