import unittest

from src.core.workflow_steps_codec import (
    find_unknown_placeholders,
    format_workflow_steps_text,
    parse_workflow_steps_text,
)


class TestWorkflowStepsCodec(unittest.TestCase):
    def test_parse_and_format_roundtrip(self):
        text = "url {clipboard} | 编码结果\nhash {prev} | MD5"

        steps = parse_workflow_steps_text(text)

        self.assertEqual(
            steps,
            [
                {"command": "url {clipboard}", "pick": "编码结果"},
                {"command": "hash {prev}", "pick": "MD5"},
            ],
        )

        out = format_workflow_steps_text(steps)
        self.assertEqual(out, text)

    def test_parse_optional_pick_and_ignores_blank_lines(self):
        text = "\n  timestamp now\nbase64 {input} | 编码结果\n  \n"

        steps = parse_workflow_steps_text(text)

        self.assertEqual(
            steps,
            [
                {"command": "timestamp now"},
                {"command": "base64 {input}", "pick": "编码结果"},
            ],
        )

        out = format_workflow_steps_text(steps)
        self.assertEqual(out, "timestamp now\nbase64 {input} | 编码结果")

    def test_find_unknown_placeholders_detects_dash_and_dot_tokens(self):
        text = "url {clip-board} {prev.value} {prev}"

        unknown = find_unknown_placeholders(text, {"clipboard", "prev", "input"})

        self.assertEqual(unknown, ["clip-board", "prev.value"])

    def test_find_unknown_placeholders_ignores_malformed_tokens(self):
        text = "hash {prev} {bad-token} {not.closed"

        unknown = find_unknown_placeholders(text, {"clipboard", "prev", "input"})

        self.assertEqual(unknown, ["bad-token"])

    def test_parse_pipe_edge_cases(self):
        text = "url {clipboard} |\n| only-pick\nhash {prev}|MD5"

        steps = parse_workflow_steps_text(text)

        self.assertEqual(
            steps,
            [
                {"command": "url {clipboard}"},
                {"command": "", "pick": "only-pick"},
                {"command": "hash {prev}", "pick": "MD5"},
            ],
        )

    def test_non_string_input_behavior(self):
        self.assertEqual(parse_workflow_steps_text(None), [])
        self.assertEqual(parse_workflow_steps_text(123), [])
        self.assertEqual(format_workflow_steps_text(None), "")

    def test_format_skips_invalid_entries_deterministically(self):
        steps = [
            None,
            {"command": "  "},
            {"command": "url {clipboard}", "pick": "编码结果"},
            {"command": 1, "pick": "x"},
            {"pick": "missing"},
            {"command": "hash {prev}", "pick": None},
            {"command": "timestamp now"},
        ]

        out = format_workflow_steps_text(steps)

        self.assertEqual(
            out,
            "url {clipboard} | 编码结果\nhash {prev}\ntimestamp now",
        )


if __name__ == "__main__":
    unittest.main()
