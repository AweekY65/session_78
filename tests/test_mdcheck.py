"""End-to-end tests for mdcheck. Everything runs locally in tmp dirs."""

import json

import pytest

from mdcheck.anchors import assign_anchors, slugify
from mdcheck.checker import check
from mdcheck.cli import EXIT_ERROR, EXIT_ISSUES, EXIT_OK, main
from mdcheck.config import Config, ConfigError, load_config


def write(root, rel, content):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def run_check(root, config=None):
    return check(root, config or Config())


def issue_types(result):
    return [issue.type for issue in result.issues]


# ---------------------------------------------------------------- anchors


def test_slugify_basic():
    assert slugify("Hello World") == "hello-world"
    assert slugify("Foo, Bar & Baz!") == "foo-bar--baz"
    assert slugify("snake_case stays") == "snake_case-stays"


def test_slugify_unicode():
    assert slugify("你好 世界") == "你好-世界"
    assert slugify("Über alles") == "über-alles"
    assert slugify("日本語 テスト") == "日本語-テスト"


def test_assign_anchors_duplicates():
    assert assign_anchors(["Intro", "Intro", "intro", "Other"]) == [
        "intro",
        "intro-1",
        "intro-2",
        "other",
    ]


# ---------------------------------------------------------------- links


def test_valid_links_pass(tmp_path):
    write(tmp_path, "a.md", "# Title\n\nSee [b](b.md) and [sec](b.md#section-one).\n")
    write(tmp_path, "b.md", "# B\n\n## Section One\n\nBack to [a](a.md#title).\n")
    result = run_check(tmp_path)
    assert result.issues == []
    assert main([str(tmp_path)]) == EXIT_OK


def test_missing_file(tmp_path):
    write(tmp_path, "a.md", "# A\n\nLine two.\n\n[gone](missing.md)\n")
    result = run_check(tmp_path)
    assert issue_types(result) == ["missing-file"]
    issue = result.issues[0]
    assert issue.file == "a.md"
    assert issue.line == 5
    assert main([str(tmp_path)]) == EXIT_ISSUES


def test_missing_anchor_cross_file(tmp_path):
    write(tmp_path, "a.md", "# A\n[ref](b.md#real-sections)\n")
    write(tmp_path, "b.md", "# B\n\n## Real Section\n")
    result = run_check(tmp_path)
    assert issue_types(result) == ["missing-anchor"]
    issue = result.issues[0]
    assert issue.file == "a.md"
    assert issue.line == 2
    assert "real-section" in issue.message  # did-you-mean suggestion


def test_missing_anchor_same_file(tmp_path):
    write(tmp_path, "a.md", "# A\n\n[jump](#nowhere)\n")
    result = run_check(tmp_path)
    assert issue_types(result) == ["missing-anchor"]


def test_heading_rename_breaks_reference(tmp_path):
    write(tmp_path, "a.md", "# A\n[ref](b.md#old-name)\n")
    write(tmp_path, "b.md", "# New Name\n")
    result = run_check(tmp_path)
    assert issue_types(result) == ["missing-anchor"]


def test_file_rename_breaks_reference(tmp_path):
    write(tmp_path, "a.md", "# A\n[ref](old-name.md)\n")
    write(tmp_path, "new-name.md", "# Renamed\n")
    result = run_check(tmp_path)
    assert issue_types(result) == ["missing-file"]


def test_unicode_heading_anchor(tmp_path):
    write(tmp_path, "a.md", "# 你好 世界\n\n[self](#你好-世界)\n[other](b.md#日本語-テスト)\n")
    write(tmp_path, "b.md", "# 日本語 テスト\n")
    result = run_check(tmp_path)
    assert result.issues == []


def test_unicode_anchor_mismatch(tmp_path):
    write(tmp_path, "a.md", "# 你好 世界\n\n[bad](#你好-世界-1)\n")
    result = run_check(tmp_path)
    assert issue_types(result) == ["missing-anchor"]


def test_duplicate_headings(tmp_path):
    write(
        tmp_path,
        "a.md",
        "# Doc\n\n## Intro\n\n## Intro\n\n[first](#intro)\n[second](#intro-1)\n",
    )
    result = run_check(tmp_path)
    assert "duplicate-heading" in issue_types(result)
    # The disambiguated links themselves still resolve.
    assert "missing-anchor" not in issue_types(result)
    dup = next(i for i in result.issues if i.type == "duplicate-heading")
    assert dup.line == 5


def test_code_block_links_ignored(tmp_path):
    write(
        tmp_path,
        "a.md",
        "# Real\n\n```markdown\n[fake](missing.md)\n# Fake Heading\n```\n\n"
        "Inline `[also-fake](missing.md)` code.\n\n"
        "~~~\n![fake](missing.png)\n~~~\n",
    )
    result = run_check(tmp_path)
    assert result.issues == []


def test_images_checked(tmp_path):
    write(tmp_path, "a.md", "# A\n\n![ok](img.png)\n![bad](gone.png)\n")
    write(tmp_path, "img.png", b"\x89PNG\r\n\x1a\n")
    result = run_check(tmp_path)
    assert issue_types(result) == ["missing-image"]
    assert result.issues[0].line == 4


def test_external_links_skipped(tmp_path):
    write(
        tmp_path,
        "a.md",
        "# A\n\n[web](https://example.com/x)\n[mail](mailto:a@b.c)\n"
        "[def][r]\n\n[r]: https://example.com/y\n",
    )
    result = run_check(tmp_path)
    assert result.issues == []


def test_reference_definition_checked(tmp_path):
    write(tmp_path, "a.md", "# A\n\n[def][r]\n\n[r]: missing.md\n")
    result = run_check(tmp_path)
    assert issue_types(result) == ["missing-file"]
    assert result.issues[0].line == 5


def test_percent_encoded_and_nested_paths(tmp_path):
    write(tmp_path, "sub dir/my file.md", "# Target\n")
    write(tmp_path, "a.md", "# A\n[x](sub%20dir/my%20file.md#target)\n")
    result = run_check(tmp_path)
    assert result.issues == []


def test_anchor_on_non_markdown_file(tmp_path):
    write(tmp_path, "a.md", "# A\n[x](data.json#frag)\n")
    write(tmp_path, "data.json", "{}")
    result = run_check(tmp_path)
    assert issue_types(result) == ["invalid-anchor"]


# ---------------------------------------------------------------- ignore rules


def test_ignore_dirs(tmp_path):
    write(tmp_path, "a.md", "# A\n[ok](b.md)\n")
    write(tmp_path, "b.md", "# B\n")
    write(tmp_path, "node_modules/pkg/bad.md", "# X\n[bad](missing.md)\n")
    result = run_check(tmp_path)
    assert result.issues == []
    assert result.files_checked == 2


def test_ignore_glob(tmp_path):
    write(tmp_path, "a.md", "# A\n")
    write(tmp_path, "drafts/bad.md", "# X\n[bad](missing.md)\n")
    config = Config(ignore=("drafts/*",))
    result = run_check(tmp_path, config)
    assert result.issues == []
    assert result.files_skipped == [("drafts/bad.md", "ignore rule")]


def test_max_file_size(tmp_path):
    write(tmp_path, "a.md", "# A\n")
    write(tmp_path, "big.md", "# Big\n[bad](missing.md)\n" + "x" * 100)
    config = Config(max_file_size=50)
    result = run_check(tmp_path, config)
    assert result.issues == []
    assert len(result.files_skipped) == 1
    assert result.files_skipped[0][0] == "big.md"


# ---------------------------------------------------------------- config


def test_config_file_loaded_from_root(tmp_path):
    write(tmp_path, ".mdcheck.json", '{"ignore": ["skip.md"]}')
    write(tmp_path, "skip.md", "# X\n[bad](missing.md)\n")
    assert main([str(tmp_path)]) == EXIT_OK


def test_config_invalid_json(tmp_path):
    write(tmp_path, ".mdcheck.json", "{not json")
    assert main([str(tmp_path)]) == EXIT_ERROR


def test_config_unknown_key(tmp_path):
    write(tmp_path, ".mdcheck.json", '{"igonre": []}')
    assert main([str(tmp_path)]) == EXIT_ERROR


def test_config_bad_types(tmp_path):
    write(tmp_path, "bad1.json", '{"ignore_dirs": "node_modules"}')
    write(tmp_path, "bad2.json", '{"max_file_size": -1}')
    write(tmp_path, "bad3.json", '{"max_file_size": true}')
    write(tmp_path, "bad4.json", '["not", "an", "object"]')
    for name in ("bad1.json", "bad2.json", "bad3.json", "bad4.json"):
        with pytest.raises(ConfigError):
            load_config(tmp_path, str(tmp_path / name))


def test_config_missing_explicit_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path, str(tmp_path / "nope.json"))


def test_missing_root_directory():
    assert main(["/definitely/not/a/real/dir"]) == EXIT_ERROR


# ---------------------------------------------------------------- output


def test_json_output(tmp_path, capsys):
    write(tmp_path, "a.md", "# A\n[bad](missing.md)\n")
    code = main([str(tmp_path), "--format", "json"])
    assert code == EXIT_ISSUES
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["issue_count"] == 1
    assert payload["issues"][0]["type"] == "missing-file"
    assert payload["issues"][0]["file"] == "a.md"
    assert payload["issues"][0]["line"] == 2


def test_text_output(tmp_path, capsys):
    write(tmp_path, "a.md", "# A\n[bad](missing.md)\n")
    main([str(tmp_path)])
    out = capsys.readouterr().out
    assert "a.md:2: missing-file:" in out
    assert "1 issue(s) found" in out


def test_config_error_message_on_stderr(tmp_path, capsys):
    write(tmp_path, ".mdcheck.json", "{broken")
    code = main([str(tmp_path)])
    assert code == EXIT_ERROR
    assert "configuration error" in capsys.readouterr().err
