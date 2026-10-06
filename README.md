# mdcheck — 本地 Markdown 文档一致性检查工具

`mdcheck` 递归扫描工程内的 Markdown 文件，校验内部链接、heading anchor
与图片引用是否与磁盘上的真实文件一致。**所有输入（Markdown、索引、配置、
报告）均来自本地工程，工具不访问 GitHub、网页、搜索引擎或任何外部服务。**

## 使用方法

```bash
python -m mdcheck [根目录] [--config 配置文件] [--format text|json]
```

- 根目录默认为当前目录。
- 配置文件默认为 `<根目录>/mdcheck.toml`，不存在时使用内置默认配置。
- `--format` 默认为 `text`（终端文本），可选 `json`。

### 退出码

| 退出码 | 含义 |
| ------ | ---- |
| 0 | 未发现问题 |
| 1 | 发现问题（错误或警告） |
| 2 | 工具自身错误（配置错误、文件不可读、根目录不存在等） |

## Anchor 生成规则

anchor 由 heading 纯文本（去除行内 Markdown 标记与 HTML 标签后）按
GitHub 风格的稳定规则生成：

1. 去除首尾空白，全部转小写（Unicode aware）。
2. 删除标点与符号；保留 Unicode 字母、数字、`-`、`_` 及组合记号。
3. 空白字符（空格、Tab 等）替换为 `-`。
4. 同一文档内重复 heading 依次追加 `-1`、`-2` 后缀，保证唯一且稳定。

示例：

| Heading | Anchor |
| ------- | ------ |
| `## 安装步骤` | `#安装步骤` |
| `## Café au lait` | `#café-au-lait` |
| `## 你好，世界` | `#你好世界`（逗号被删除） |
| 第二个 `## 重复` | `#重复-1` |

链接中的 anchor 与生成结果精确匹配（区分大小写，生成结果均为小写）。

## 检查范围

- 递归扫描 `.md` / `.markdown` 文件（忽略规则见下文）。
- 解析 ATX（`#`）与 Setext（`===` / `---`）heading。
- 校验行内链接 `[text](dest)` 与图片 `![alt](src)`：
  - 相对文件链接是否真实存在（含子目录、`..` 与百分号编码路径）。
  - 文件内与跨文件的 `#anchor` 是否存在；heading 被修改或文件被
    重命名后，对应的失效引用会被报告为 `missing-anchor` /
    `missing-file`，并给出来源文件与准确行号。
- 重复 heading 生成的 anchor 冲突报告为 `duplicate-anchor` 警告。
- 围栏代码块（```` ``` ```` 与 `~~~`）和行内代码中的伪链接一律忽略。
- 外部链接（`http(s)://`、`mailto:`、`//...` 等带 scheme 的目标）跳过。
- 非 Markdown 目标（如图片）只校验文件存在，不校验 anchor。

暂不校验引用式链接（`[text][ref]`）与 HTML 标签内的链接。

## 配置（mdcheck.toml）

```toml
# 额外忽略的目录名（默认已含 .git/.hg/.svn/node_modules/__pycache__）
ignore_dirs = ["vendor", "dist"]

# fnmatch 风格的忽略规则，匹配相对根目录的路径（含任意父级命中即忽略）
ignore = ["drafts/**", "*.tmp.md"]

# 单文件最大字节数，超过则跳过并报告 file-skipped 警告
max_file_size = 1048576
```

配置错误（TOML 无法解析、未知键、类型错误、显式指定的配置文件不存在）
会在 stderr 给出明确信息并以退出码 2 结束。

## 输出

文本输出每条问题一行：`<文件>:<行号>: <级别>: <说明> [<类型>]`，末尾附汇总。
JSON 输出包含 `files_scanned`、`error_count`、`warning_count` 与 `issues`
数组（含 `file`、`line`、`severity`、`type`、`message`、`target` 字段）。

## 测试

全部测试在终端内运行，不启动文档网站或浏览器：

```bash
python -m pytest tests/ -v
```

覆盖场景：合法链接、失效文件、失效 anchor（含跨文件与 heading 重命名）、
Unicode heading、重复标题、代码块中的伪链接、忽略规则、配置错误、
最大文件大小、图片引用与 JSON 输出格式。
