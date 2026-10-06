"""mdcheck 端到端测试：全部在终端内运行，不启动浏览器或文档网站。"""

import json

import pytest

from mdcheck.cli import EXIT_ISSUES, EXIT_OK, EXIT_TOOL_ERROR, main


def write(root, rel, content):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def run(root, capsys, *extra):
    code = main([str(root), *extra])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_valid_links_and_anchors(tmp_path, capsys):
    write(tmp_path, "index.md", "# 首页\n\n[文档](docs/guide.md#安装)\n[锚点](#首页)\n")
    write(tmp_path, "docs/guide.md", "# 指南\n\n## 安装\n\n[返回](../index.md#首页)\n")
    code, out, _ = run(tmp_path, capsys)
    assert code == EXIT_OK
    assert "0 个错误" in out


def test_missing_file_reports_line(tmp_path, capsys):
    write(tmp_path, "index.md", "# A\n\n文本\n\n[坏链接](no/such-file.md)\n")
    code, out, _ = run(tmp_path, capsys)
    assert code == EXIT_ISSUES
    assert "index.md:5" in out
    assert "missing-file" in out


def test_missing_anchor_same_file(tmp_path, capsys):
    write(tmp_path, "a.md", "# 标题\n\n[跳转](#不存在的锚点)\n")
    code, out, _ = run(tmp_path, capsys)
    assert code == EXIT_ISSUES
    assert "a.md:3" in out
    assert "missing-anchor" in out


def test_missing_anchor_cross_file_after_rename(tmp_path, capsys):
    # 模拟 heading 被修改后，跨文件引用失效的场景
    write(tmp_path, "guide.md", "# 指南\n\n## 新名字\n")
    write(tmp_path, "index.md", "# 首页\n\n[旧引用](guide.md#旧名字)\n")
    code, out, _ = run(tmp_path, capsys)
    assert code == EXIT_ISSUES
    assert "missing-anchor" in out
    assert "guide.md" in out


def test_unicode_headings(tmp_path, capsys):
    write(
        tmp_path,
        "u.md",
        "# Café au lait\n\n## 你好，世界\n\n[一](#café-au-lait)\n[二](#你好世界)\n",
    )
    code, out, _ = run(tmp_path, capsys)
    assert code == EXIT_OK, out


def test_duplicate_headings_get_stable_suffixed_anchors(tmp_path, capsys):
    write(
        tmp_path,
        "dup.md",
        "# Intro\n\n## 重复\n\n## 重复\n\n[一](#重复)\n[二](#重复-1)\n",
    )
    code, out, _ = run(tmp_path, capsys, "--format", "json")
    assert code == EXIT_ISSUES  # 重复 heading 产生警告
    report = json.loads(out)
    assert report["error_count"] == 0
    duplicates = [i for i in report["issues"] if i["type"] == "duplicate-anchor"]
    assert len(duplicates) == 1
    assert duplicates[0]["line"] == 5
    assert duplicates[0]["severity"] == "warning"


def test_links_inside_code_blocks_are_ignored(tmp_path, capsys):
    content = (
        "# 标题\n"
        "\n"
        "```markdown\n"
        "[伪链接](not-real.md)\n"
        "![伪图片](not-real.png)\n"
        "# 伪标题\n"
        "```\n"
        "\n"
        "行内代码 `[伪链接](also-not-real.md)` 同样忽略。\n"
        "\n"
        "~~~\n"
        "[另一个伪链接](nope.md)\n"
        "~~~\n"
    )
    write(tmp_path, "code.md", content)
    code, out, _ = run(tmp_path, capsys)
    assert code == EXIT_OK, out


def test_ignore_dirs_and_patterns(tmp_path, capsys):
    write(tmp_path, "index.md", "# 首页\n")
    write(tmp_path, "drafts/bad.md", "[坏](missing.md)\n")
    write(tmp_path, "notes/skip.tmp.md", "[坏](missing.md)\n")
    write(tmp_path, "vendor/pkg/bad.md", "[坏](missing.md)\n")
    write(
        tmp_path,
        "mdcheck.toml",
        'ignore_dirs = ["vendor"]\nignore = ["drafts/**", "*.tmp.md"]\n',
    )
    code, out, _ = run(tmp_path, capsys, "--format", "json")
    assert code == EXIT_OK, out
    report = json.loads(out)
    assert report["files_scanned"] == 1


def test_max_file_size_skips_large_files(tmp_path, capsys):
    write(tmp_path, "big.md", "[坏](missing.md)\n" + "x" * 100 + "\n")
    write(tmp_path, "mdcheck.toml", "max_file_size = 10\n")
    code, out, _ = run(tmp_path, capsys, "--format", "json")
    assert code == EXIT_ISSUES
    report = json.loads(out)
    assert report["files_scanned"] == 0
    assert report["issues"][0]["type"] == "file-skipped"
    assert report["issues"][0]["severity"] == "warning"


@pytest.mark.parametrize(
    "config_text",
    [
        "this is not toml = =",
        'unknown_key = 1\n',
        'ignore_dirs = "not-a-list"\n',
        'max_file_size = -5\n',
        'max_file_size = "big"\n',
    ],
)
def test_invalid_config_reports_error(tmp_path, capsys, config_text):
    write(tmp_path, "index.md", "# 首页\n")
    write(tmp_path, "mdcheck.toml", config_text)
    code, _, err = run(tmp_path, capsys)
    assert code == EXIT_TOOL_ERROR
    assert "配置错误" in err


def test_missing_explicit_config_file(tmp_path, capsys):
    write(tmp_path, "index.md", "# 首页\n")
    code, _, err = run(tmp_path, capsys, "--config", str(tmp_path / "nope.toml"))
    assert code == EXIT_TOOL_ERROR
    assert "配置错误" in err


def test_missing_root_directory(tmp_path, capsys):
    code = main([str(tmp_path / "ghost")])
    assert code == EXIT_TOOL_ERROR


def test_image_references(tmp_path, capsys):
    write(tmp_path, "index.md", "# 首页\n\n![好图](img/ok.png)\n\n![坏图](img/gone.png)\n")
    write(tmp_path, "img/ok.png", "fake-png-bytes")
    code, out, _ = run(tmp_path, capsys)
    assert code == EXIT_ISSUES
    assert "index.md:5" in out
    assert "missing-file" in out
    assert "ok.png" not in out


def test_external_links_are_skipped(tmp_path, capsys):
    write(
        tmp_path,
        "ext.md",
        "# 外链\n\n[网页](https://example.com/a#b)\n[邮件](mailto:a@b.c)\n[协议相对](//example.com/x)\n",
    )
    code, out, _ = run(tmp_path, capsys)
    assert code == EXIT_OK, out


def test_json_output_schema(tmp_path, capsys):
    write(tmp_path, "index.md", "# A\n\n[坏](gone.md)\n")
    code, out, _ = run(tmp_path, capsys, "--format", "json")
    assert code == EXIT_ISSUES
    report = json.loads(out)
    assert report["files_scanned"] == 1
    assert report["error_count"] == 1
    issue = report["issues"][0]
    assert issue["file"] == "index.md"
    assert issue["line"] == 3
    assert issue["type"] == "missing-file"
    assert issue["severity"] == "error"
    assert issue["target"] == "gone.md"


def test_subdirectory_relative_links(tmp_path, capsys):
    write(tmp_path, "index.md", "# 首页\n\n[子页](sub/page.md)\n")
    write(tmp_path, "sub/page.md", "# 子页\n\n[回首页](../index.md#首页)\n[图](../img/a.png)\n")
    write(tmp_path, "img/a.png", "fake")
    code, out, _ = run(tmp_path, capsys)
    assert code == EXIT_OK, out


def test_setext_headings(tmp_path, capsys):
    write(tmp_path, "s.md", "标题一\n=====\n\n标题二\n-----\n\n[一](#标题一)\n[二](#标题二)\n")
    code, out, _ = run(tmp_path, capsys)
    assert code == EXIT_OK, out
