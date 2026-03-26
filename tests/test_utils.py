from core.utils import strip_code_fences


class TestStripCodeFences:
    def test_plain_json_unchanged(self):
        text = '{"key": "value"}'
        assert strip_code_fences(text) == '{"key": "value"}'

    def test_strip_json_fence(self):
        text = '```json\n{"key": "value"}\n```'
        assert strip_code_fences(text) == '{"key": "value"}'

    def test_strip_plain_fence(self):
        text = '```\n{"key": "value"}\n```'
        assert strip_code_fences(text) == '{"key": "value"}'

    def test_strip_multiline(self):
        text = '```json\n{\n  "list": [1, 2, 3]\n}\n```'
        assert strip_code_fences(text) == '{\n  "list": [1, 2, 3]\n}'

    def test_no_fence_passthrough(self):
        assert strip_code_fences("plain text") == "plain text"

    def test_surrounding_whitespace(self):
        text = '  \n```json\n{}\n```\n  '
        assert strip_code_fences(text) == '{}'

    def test_opening_fence_only(self):
        text = '```json\n{"key": "value"}'
        # Only opening fence, no closing — still strips the opening line
        assert strip_code_fences(text) == '{"key": "value"}'

