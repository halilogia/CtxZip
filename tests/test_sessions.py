"""Synthetic source-format examples; no real conversations or credentials."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ctxzip
from ctxzip_core import summarizing


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source' / 'session.jsonl'
        self.source.parent.mkdir()
        self.archive = self.root / 'archive'
        self.pk = self.archive / 'Demo'
        self.settings = copy.deepcopy(ctxzip.DEFAULT_SETTINGS)
        self.settings.update(aktif_oturum_dk=0, cilt_bolum_sayisi=2)
        self.settings['kaynaklar'] = {'codex': [str(self.source.parent)]}
        self.addCleanup(mock.patch.stopall)
        mock.patch('builtins.print').start()

    def write_source(self, count):
        records = [{'type': 'session_meta', 'payload': {'cwd': '/projects/Demo', 'git': {'branch': 'main'}}}]
        for n in range(count):
            for role, text in [('user', f'Question {n}'), ('assistant', f'Answer {n}')]:
                records.append({'type': 'response_item', 'timestamp': '2026-01-01T10:00:00Z',
                                'payload': {'type': 'message', 'role': role,
                                            'content': [{'type': 'input_text', 'text': text}]}})
        self.source.write_text('\n'.join(json.dumps(r) for r in records) + '\n{broken', encoding='utf-8')
        os.utime(self.source, (1, 1))

    def pipeline(self):
        ctxzip.collect(self.settings, self.archive)
        ctxzip.write_transcripts(self.settings, self.archive, 'Demo')
        ctxzip.summarize(self.settings, self.archive, 'Demo', True)

    def test_repeat_growth_shrink_and_manual_edits(self):
        self.write_source(2)
        self.pipeline()
        first = self.pk / 'bolumler' / 'B0001.md'
        first.write_text(first.read_text(encoding='utf-8').replace(ctxzip.SUMMARY_PLACEHOLDER, 'Manual decision'), encoding='utf-8')
        edited = first.read_bytes()
        self.pipeline()
        self.assertEqual(len(ctxzip.load_summary_state(self.pk)['bolumler']), 1)
        self.assertTrue(ctxzip.is_manually_edited(first))
        self.write_source(3)
        self.pipeline()
        state = ctxzip.load_summary_state(self.pk)
        self.assertEqual([(b['tur_baslangic'], b['tur_bitis']) for b in state['bolumler']], [(1, 2), (3, 3)])
        self.assertEqual(state['ciltler'], [])
        self.write_source(1)
        self.pipeline()
        self.assertEqual(ctxzip.load_summary_state(self.pk), state)
        self.assertEqual(first.read_bytes(), edited)
        self.assertEqual(len(list((self.pk / 'raw' / 'codex').glob('*.onceki.jsonl'))), 1)
        ctxzip.build_context(self.settings, self.archive, 'Demo', 12000, None)
        context = (self.pk / 'BAGLAM.md').read_text(encoding='utf-8')
        self.assertIn('Manual decision', context)
        self.assertNotIn(ctxzip.SUMMARY_PLACEHOLDER, context)

    def test_active_tail_waits(self):
        self.write_source(1)
        self.settings['aktif_oturum_dk'] = 10**9
        self.pipeline()
        self.assertEqual(ctxzip.load_summary_state(self.pk)['bolumler'], [])

    def test_failure_keeps_progress_and_retry_does_not_duplicate(self):
        self.write_source(2)
        self.settings.update(bolum_token=1, cilt_bolum_sayisi=99)
        self.settings['llm']['model'] = 'test-model'
        ctxzip.collect(self.settings, self.archive)
        # A later project must not run after a chapter provider failure.
        later = self.archive / 'Zulu' / 'gelen'
        later.mkdir(parents=True)
        (later / 'note.txt').write_text('Example', encoding='utf-8')
        with mock.patch.object(summarizing, 'call_llm', side_effect=['First', RuntimeError('offline')]):
            ctxzip.summarize(self.settings, self.archive, None, False)
        self.assertFalse((later.parent / 'durum.json').exists())
        self.assertEqual(len(ctxzip.load_summary_state(self.pk)['bolumler']), 1)
        first = (self.pk / 'bolumler' / 'B0001.md').read_bytes()
        with mock.patch.object(summarizing, 'call_llm', return_value='Second') as call:
            ctxzip.summarize(self.settings, self.archive, 'Demo', False)
            self.assertEqual(call.call_count, 1)
        self.assertEqual(len(ctxzip.load_summary_state(self.pk)['bolumler']), 2)
        self.assertEqual((self.pk / 'bolumler' / 'B0001.md').read_bytes(), first)

    def test_volume_uses_edits_and_preserves_edited_volume(self):
        self.write_source(2)
        self.settings['bolum_token'] = 1
        self.pipeline()
        for path in (self.pk / 'bolumler').glob('B????.md'):
            path.write_text(path.read_text(encoding='utf-8').replace(ctxzip.SUMMARY_PLACEHOLDER, 'Reviewed decision'), encoding='utf-8')
        self.pipeline()
        prompt = (self.pk / 'ciltler' / 'C001.istem.md').read_text(encoding='utf-8')
        self.assertEqual(prompt.count('Reviewed decision'), 2)
        volume = self.pk / 'ciltler' / 'C001.md'
        volume.write_text(volume.read_text(encoding='utf-8').replace(ctxzip.SUMMARY_PLACEHOLDER, 'Reviewed volume'), encoding='utf-8')
        saved = volume.read_bytes()
        self.settings['llm']['model'] = 'test-model'
        with mock.patch.object(summarizing, 'call_llm') as call:
            ctxzip.summarize(self.settings, self.archive, 'Demo', False)
            call.assert_not_called()
        self.assertEqual(volume.read_bytes(), saved)
        self.assertEqual(len(ctxzip.load_summary_state(self.pk)['ciltler']), 1)

    def test_dump_and_manual_prompt_redact_secrets(self):
        self.write_source(1)
        fake = 'sk-' + 'Z' * 32
        self.source.write_text(self.source.read_text(encoding='utf-8').replace('Question 0', fake), encoding='utf-8')
        self.pipeline()
        for directory in ['dokum', 'bolumler']:
            for path in (self.pk / directory).glob('*.md'):
                self.assertNotIn(fake, path.read_text(encoding='utf-8'))

    def test_claude_tools_images_thinking_and_metadata(self):
        records = [
            {'type': 'user', 'cwd': '/projects/Demo', 'gitBranch': 'main', 'message': {'content': [{'type': 'image'}]}},
            {'type': 'user', 'message': {'content': '<system-reminder>hidden</system-reminder>Hello'}},
            {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'Done'}, {'type': 'thinking', 'thinking': 'Consider'}, {'type': 'tool_use', 'name': 'Read', 'input': {'path': 'demo.py'}}]}},
            {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'is_error': True, 'content': 'missing'}]}},
        ]
        self.source.write_text('\n'.join(json.dumps(r) for r in records), encoding='utf-8')
        turns, info = ctxzip.parse_claude_turns(self.source, False)
        self.assertEqual(len(turns), 1)
        self.assertEqual(info['dal'], 'main')
        self.assertEqual(turns[0].text(), '_[1 görsel eklendi]_\n**Kullanıcı:** Hello\n**Asistan:** Done\n  - → Read: demo.py\n  - ✗ araç hatası: missing')
        self.assertIn('Consider', ctxzip.parse_claude_turns(self.source, True)[0][0].text())

    def test_artifact_and_manual_readers(self):
        folder = self.root / 'artifacts'
        folder.mkdir()
        path = folder / 'task.md'
        path.write_text(' Demo task ', encoding='utf-8')
        turns, _ = ctxzip.parse_antigravity_turns(folder, False)
        self.assertEqual(turns[0].text(), '**Artefakt `task.md`:**\n\nDemo task')
        self.assertEqual(ctxzip.parse_manual_turns(path, False)[0][0].text(), 'Demo task')


if __name__ == '__main__':
    unittest.main()
