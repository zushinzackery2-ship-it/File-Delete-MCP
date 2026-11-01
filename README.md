<div align="center">

# File-Delete-MCP

**给 Codex 等 Agent 提供受控的文件删除能力**

*预览开票 → 移入 `.del` → 确认后永久清空*

![Python](https://img.shields.io/badge/Python-3.12%2B-blue?style=flat-square)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?style=flat-square)
![MCP](https://img.shields.io/badge/MCP-stdio-green?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)

</div>

---

> [!NOTE]
> **仓库边界**  
> 本仓库只提供一个工作区级的删除 MCP，不负责文件浏览、移动、复制或版本控制操作。

## 功能概览

| 功能 | 说明 |
|:-----|:-----|
| **删除预检** | 解析相对/绝对路径，检查越界、`.del`、非空目录、git 脏文件、体积与数量，签发一次性票据 |
| **可恢复删除** | `trash_paths` 将文件移入工作区 `.del/<batch>/files/`，保留原始相对路径与 manifest |
| **永久清空** | `purge_del` 按批次、天数或全部清空 `.del`，同样需要票据 |
| **防误删** | 票据绑定路径、`recursive` 和文件指纹，过期或文件变化即拒绝执行 |

## 核心 API

| 分类 | API | 说明 |
|:-----|:----|:-----|
| **预检** | `preview_delete(scope, paths, recursive, batch_ids, older_than_days, all)` | 返回 `ticket`、`risk`、`blockers`、`warnings` 与条目统计 |
| **删除** | `trash_paths(paths, ticket, recursive, accept_warnings)` | 将预览过的路径移入 `.del` |
| **清空** | `purge_del(ticket, batch_ids, older_than_days, all, accept_warnings)` | 永久删除匹配的 `.del` 批次 |

`risk` 为 `warn` 时必须显式传 `accept_warnings=true`；`risk` 为 `block` 时不签发票据。

## `.del` 布局

```text
.del/
├── .gitignore
└── 20261102T153000-7f3a/
    ├── manifest.json
    └── files/
        └── src/foo.py
```

## 构建

```bat
uv venv --python 3.13
uv pip install --python .venv\Scripts\python.exe -e ".[dev]"
.venv\Scripts\python.exe -m pytest
```

## Codex 配置

```toml
[mcp_servers.file-delete]
type = "stdio"
command = 'D:\Projects\File-Delete-MCP\.venv\Scripts\python.exe'
args = ["-m", "file_delete_mcp"]
enabled = true
startup_timeout_sec = 60
tool_timeout_sec = 120
```

工作区根默认取 MCP 进程当前目录，也可用 `--root` 或 `FILE_DELETE_ROOT` 固定。相对路径按工作区根解析，绝对路径必须落在根内。

> [!CAUTION]
> MCP 运行在 Codex 沙箱之外。`--root` 不要指向磁盘根或用户目录。

---

<div align="center">

**Platform:** Windows | **License:** MIT

</div>
