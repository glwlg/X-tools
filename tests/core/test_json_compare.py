from src.core.json_compare import compare_json_text


def test_compare_ignores_object_key_order():
    result = compare_json_text('{"b":2,"a":1}', '{"a":1,"b":2}')

    assert result.ok is True
    assert result.differences == []
    assert result.summary == "两个 JSON 语义一致"
    assert "没有行差异" in result.unified_diff


def test_compare_reports_added_removed_and_changed_paths():
    left = '{"name":"same","meta":{"enabled":true,"drop":1},"items":[1,2]}'
    right = '{"name":"same","meta":{"enabled":true,"add":2},"items":[1,3,4]}'

    result = compare_json_text(left, right)

    assert result.ok is True
    assert result.summary == "发现 4 处差异：新增 2，删除 1，变更 1"
    assert "- $.meta.drop: 1" in result.report
    assert "+ $.meta.add: 2" in result.report
    assert "~ $.items[1]: 2 -> 3" in result.report
    assert "+ $.items[2]: 4" in result.report


def test_compare_returns_parse_error_with_location():
    result = compare_json_text('{"ok": true}', '{"bad": }')

    assert result.ok is False
    assert result.summary == "解析失败"
    assert "右侧 JSON 解析失败" in result.error
    assert "第 1 行" in result.error
