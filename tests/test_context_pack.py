import unittest

from ctxzip_core.context_pack import FORMAT_ID, SCHEMA_VERSION, parse_metadata_block, render_metadata_block


class ContextPackFormatTests(unittest.TestCase):
    def test_metadata_round_trips_as_a_leading_machine_readable_block(self):
        metadata = {
            "format": FORMAT_ID,
            "schema_version": SCHEMA_VERSION,
            "project": "Demo --> archive",
            "generated_at": "2026-09-26T12:00:00+03:00",
            "language": "en",
            "budget": {
                "limit": 12000, "profile": "balanced",
                "recent_raw_allocation": 1500, "recent_raw_used": 0,
                "recent_raw_reserved": 1500, "safety_reserved": 750,
            },
            "estimated_tokens": 1400,
            "git": {"branch": "main", "head_sha": "a" * 40, "dirty": True},
            "sources": ["codex/session-->suffix#T2@sha256"],
        }
        rendered = render_metadata_block(metadata) + "\n\n# CtxZip Context Pack\n"

        self.assertEqual(parse_metadata_block(rendered), metadata)
        self.assertTrue(rendered.startswith("<!-- ctxzip-context-pack\n"))
        self.assertNotIn("session-->", rendered)

    def test_rejects_unknown_or_malformed_schema(self):
        with self.assertRaisesRegex(ValueError, "Unsupported context-pack schema"):
            parse_metadata_block(
                '<!-- ctxzip-context-pack\n{"format":"ctxzip-context-pack","schema_version":99}'
                '\n-->\n'
            )
        with self.assertRaisesRegex(ValueError, "not closed"):
            parse_metadata_block('<!-- ctxzip-context-pack\n{}')

    def test_renderer_requires_core_metadata(self):
        with self.assertRaisesRegex(ValueError, "missing required"):
            render_metadata_block({"format": FORMAT_ID, "schema_version": SCHEMA_VERSION})

    def test_rejects_invalid_budget_types(self):
        metadata = {
            "format": FORMAT_ID,
            "schema_version": SCHEMA_VERSION,
            "project": "Demo",
            "generated_at": "2026-09-26T12:00:00+03:00",
            "language": "en",
            "budget": {
                "limit": 1000, "profile": [],
                "recent_raw_reserved": 0, "safety_reserved": 0,
            },
            "estimated_tokens": 10,
            "git": None,
            "sources": [],
        }
        with self.assertRaisesRegex(ValueError, "invalid budget"):
            render_metadata_block(metadata)


if __name__ == "__main__":
    unittest.main()
