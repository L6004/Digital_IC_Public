# 课程展示控制

本地工作台顶部的 **课程显示设置** 可按文档选择展示方式、关联 PDF，并保存设置。它只修改根目录的 `course-display.yml`；课程 Markdown、PDF 和代码原文件不会改写。保存后本地预览自动重建。

| 方式 | 网页效果 |
| --- | --- |
| 自动识别 | 普通 Markdown 展示正文；`marp: true` 使用同名 PDF，未找到 PDF 时仅下载源码 |
| Markdown 正文 | 显式渲染 Markdown，包括手动覆盖 Marp 自动识别 |
| 仅下载源文件 | 课程资源表提供 Markdown 下载；不将正文加入网页和搜索 |
| 展示 PDF + 下载源码 | 在页面嵌入 PDF，提供 PDF 打开、下载及 Markdown 源文件下载 |
| 不在网站展示 | 从课程列表、页面、导航和搜索中排除该 Markdown |

也可以用外部编辑器修改配置。以下是路径格式示例，不代表已有资料：

```yaml
version: 1
documents:
  50_courses/example/assignments/slides.md:
    mode: pdf
    pdf: 50_courses/example/assignments/slides-export.pdf
  50_courses/example/notes/template.md:
    mode: download
  50_courses/example/notes/draft.md:
    mode: hidden
```

路径从 `docs/` 内部开始；PDF 必须在同一课程中。`mode` 可选 `auto`、`article`、`download`、`pdf`、`hidden`。删除某个配置项即恢复自动识别。课程入口 `index.md` 保持正文展示。

显示方式与公开权限相互独立。更改显示方式不会发布任何文档，也不会自动授权附件。公开时仍需审核文档及关联 PDF；提供源码下载意味着被授权文档的原始 Markdown（含 front matter）会供访问者下载。隐藏不是保密设置，已经公开过的原文件可能仍保留在仓库历史中。

课程主页的参考代码按目录树显示。点击文件后进入只读代码查看器，支持文件切换、标签页、语法高亮、折叠、行号、查找、跳转行、自动换行、复制、下载和全屏。支持 UTF-8、带 BOM 的 UTF-16，以及常见 GB 编码；超过 2 MiB、二进制或无法识别编码的文件提供下载。查看器不运行代码，不修改源码。

公开导出只携带已授权文档的显示设置和代码附件。仅更新网站功能时，应只同步渲染脚本、样式、配置和清单；不要运行会同步整个内容库的发布命令。

代码查看器源文件为 `studio/code-viewer.js`；修改后运行 `npm run build:code-viewer` 更新静态浏览器包。
