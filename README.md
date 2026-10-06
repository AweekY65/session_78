# mdcheck — 本地 Markdown 文档一致性检查工具

`mdcheck` 递归扫描本地工程中的 Markdown 文件，检查相对文件链接、heading
anchor、图片引用和重复标题，帮助在文件重命名或标题修改后发现失效引用。

**完全离线**：工具只读取本地文件系统，不访问 GitHub、网页、搜索引擎或任何
外部服务；仅依赖 Python 标准库（Python ≥ 3.9）。

## 使用方法

```bash
python -m mdcheck [目录] [--format text|json] [--config 配置文件]
```

也可以安装为命令（`pip install .` 后使用 `mdcheck`）。

### 退出码

| 退出码 | 含义 |
| ------ | ---- |
| `0` | 未发现任何问题 |
| `1` | 发现一致性问题（失效链接、失效 anchor、重复标题等） |
| `2` | 工具自身错误（配置错误、目录不存在、文件读取失败等） |

### 输出格式

- `--format text`（默认）：终端文本，每条问题一行，格式为
  `文件:行号: 类型: 描述`，末尾附统计摘要。
- `--format json`：结构化 JSON，包含 `summary`、`skipped` 和 `issues`
  三个部分，每个 issue 带 `type`、`file`、`line`、`message`、`target` 字段。

## 检查范围

- 递归扫描 `*.md` / `*.markdown` 文件，解析 ATX（`# 标题`）和 Setext
  （`===` / `---`）heading。
- 检查行内链接 `[text](dest)`、图片 `![alt](dest)` 和链接引用定义
  `[id]: dest`。
- 支持跨文件引用：`[x](docs/api.md#函数)` 会解析到目标文件并校验 anchor。
- 支持百分号编码路径（如 `sub%20dir/my%20file.md`）。
- 围栏代码块（```` ``` ```` 和 `~~~`）与行内代码中的伪链接、伪标题一律忽略。
- 外部链接（`http:`、`https:`、`mailto:` 等带 scheme 的目标）直接跳过。
- 非 Markdown 文件上的 `#anchor` 引用报告为 `invalid-anchor`。
- 每个问题都报告来源文件与准确行号。

### 问题类型

| 类型 | 含义 |
| ---- | ---- |
| `missing-file` | 相对文件链接目标不存在 |
| `missing-image` | 图片引用目标不存在 |
| `missing-anchor` | 目标文件中不存在该 heading anchor（附相似 anchor 建议） |
| `invalid-anchor` | 在非 Markdown 文件上使用了 `#anchor` |
| `duplicate-heading` | 同一文件中重复标题导致 anchor 歧义 |
| `read-error` | 文件无法读取或不是合法 UTF-8 |

## Anchor 生成规则

采用与 GitHub（github-slugger）一致的稳定规则，Unicode 感知：

1. 取标题纯文本（去除行内代码、强调、链接等格式标记）。
2. 转小写（Unicode 感知，如 `Über` → `über`）。
3. 保留字母、数字、`-` 和 `_`，删除其余标点与符号（含 emoji）。
4. 空白字符替换为 `-`。
5. 同一文件中重复的标题按出现顺序追加 `-1`、`-2`……后缀，保证无关标题
   变动时已有 anchor 保持稳定。

示例：

| 标题 | Anchor |
| ---- | ------ |
| `## Hello World` | `hello-world` |
| `## 你好 世界` | `你好-世界` |
| `## Foo, Bar & Baz!` | `foo-bar--baz` |
| 第二个 `## Intro` | `intro-1` |

重复标题会报告 `duplicate-heading` 问题：此时 `#intro` 指向第一个标题，
存在歧义，建议修改标题或显式链接到 `#intro-1`。

## 配置

默认读取扫描根目录下的 `.mdcheck.json`（或 `mdcheck.json`），也可用
`--config` 指定其他路径。所有配置项可选：

```json
{
  "ignore_dirs": [".git", "node_modules"],
  "ignore": ["drafts/*", "*.todo.md"],
  "max_file_size": 1048576
}
```

- `ignore_dirs`：目录名列表，扫描时整体跳过（任意层级均生效）。
- `ignore`：glob 模式列表，对工程相对路径或文件名匹配（fnmatch 语义，
  `*` 可跨目录分隔符）。
- `max_file_size`：单文件最大字节数，超过则跳过并在报告中列出。

配置错误（文件不存在、JSON 非法、未知键、类型错误、`max_file_size`
非正整数等）会在 stderr 输出明确原因并以退出码 `2` 结束。

被跳过的文件不会参与 anchor 校验：指向它们的文件链接仍检查存在性，
但其内部 anchor 无法验证时不会误报。

## 测试

全部测试在终端执行，不启动文档网站或浏览器：

```bash
python -m pytest
```

覆盖：合法链接、失效文件、失效 anchor、Unicode 标题、重复标题、代码块中
的伪链接、忽略规则、配置错误、JSON/文本输出与退出码。
