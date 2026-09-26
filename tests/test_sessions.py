"""Synthetic source-format examples; no real conversations or credentials."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ctxzip
from ctxzip_core.events import EventKind, SourceRef
from ctxzip_core.git_state import GitSnapshot
from ctxzip_core.context_pack import parse_metadata_block
from ctxzip_core.knowledge import (
    ConstraintRecord, DecisionRecord, EventReference, FileMentionRecord, KnowledgeStatus,
    KnowledgeStore, OpenQuestionRecord, QuestionStatus, RecordActor, TaskRecord, TaskStatus,
    TestEvidence, TestResult,
)
from ctxzip_core.parser_claude import parse_claude_session
from ctxzip_core.source_freshness import chapter_source_hash
from ctxzip_core import summarizing, source_collection, transcripts


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
        previous_sources = list((self.pk / 'raw' / 'codex').glob('*.onceki.jsonl'))
        self.assertEqual(len(previous_sources), 2)
        self.assertEqual(len({path.name for path in previous_sources}), 2)
        self.assertEqual(len({source_collection.file_hash(path) for path in previous_sources}), 2)
        self.pipeline()
        self.assertEqual(len(list((self.pk / 'raw' / 'codex').glob('*.onceki.jsonl'))), 2)
        ctxzip.build_context(self.settings, self.archive, 'Demo', 12000, None)
        context = (self.pk / 'BAGLAM.md').read_text(encoding='utf-8')
        self.assertIn('Manual decision', context)
        self.assertNotIn(ctxzip.SUMMARY_PLACEHOLDER, context)

    def test_same_size_source_rewrites_keep_each_content_version_once(self):
        self.write_source(1)
        ctxzip.collect(self.settings, self.archive)
        active = self.pk / 'raw' / 'codex' / 'session.jsonl'
        original = active.read_bytes()
        rewritten = original.replace(b'Question 0', b'Question X')
        self.assertEqual(len(rewritten), len(original))
        self.source.write_bytes(rewritten)

        ctxzip.collect(self.settings, self.archive)
        versions = list((self.pk / 'raw' / 'codex').glob('*.onceki.jsonl'))
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0].read_bytes(), original)
        self.assertIn(source_collection.file_hash(versions[0]), versions[0].name)

        ctxzip.collect(self.settings, self.archive)
        self.assertEqual(len(list((self.pk / 'raw' / 'codex').glob('*.onceki.jsonl'))), 1)

        second_rewrite = rewritten.replace(b'Question X', b'Question Y')
        self.source.write_bytes(second_rewrite)
        ctxzip.collect(self.settings, self.archive)
        versions = list((self.pk / 'raw' / 'codex').glob('*.onceki.jsonl'))
        self.assertEqual(len(versions), 2)
        self.assertEqual({path.read_bytes() for path in versions}, {original, rewritten})

    def test_transcript_pipeline_persists_and_reconciles_event_snapshots(self):
        self.write_source(1)
        ctxzip.collect(self.settings, self.archive)
        ctxzip.write_transcripts(self.settings, self.archive, 'Demo')
        event_dir = self.pk / '.ctxzip-events' / 'codex'
        snapshots = list(event_dir.glob('*.json'))
        self.assertEqual(len(snapshots), 1)
        first = json.loads(snapshots[0].read_text(encoding='utf-8'))
        self.assertEqual(first['schema'], 'ctxzip.event-snapshot')
        self.assertEqual(first['schema_version'], 2)
        self.assertTrue(first['events'])
        self.assertEqual(first['events'][0]['source']['parser_version'], '1')

        ctxzip.write_transcripts(self.settings, self.archive, 'Demo')
        self.assertEqual(len(list(event_dir.glob('*.json'))), 1)
        self.assertEqual(json.loads(snapshots[0].read_text(encoding='utf-8')), first)

        self.write_source(2)
        ctxzip.collect(self.settings, self.archive)
        previous_source = source_collection.find_source_version(
            self.pk, "codex", "session", first["source_hash"],
        )
        self.assertIsNotNone(previous_source)
        self.assertEqual(source_collection.file_hash(previous_source), first["source_hash"])
        ctxzip.write_transcripts(self.settings, self.archive, 'Demo')
        updated = json.loads(snapshots[0].read_text(encoding='utf-8'))
        self.assertNotEqual(updated['source_hash'], first['source_hash'])
        self.assertNotEqual(updated['events'][0]['id'], first['events'][0]['id'])
        self.assertEqual(len(list(event_dir.glob('*.json'))), 1)

    def test_source_version_resolution_validates_identity_and_hash(self):
        self.write_source(1)
        ctxzip.collect(self.settings, self.archive)
        active = self.pk / "raw" / "codex" / "session.jsonl"
        digest = source_collection.file_hash(active)

        self.assertEqual(
            source_collection.find_source_version(self.pk, "codex", "session", digest), active.resolve(),
        )
        self.assertIsNone(
            source_collection.find_source_version(self.pk, "codex", "session", "f" * 64),
        )
        for source_id, session_id, source_hash in (
            ("../raw", "session", digest),
            ("codex", "../session", digest),
            ("codex", "session", "not-a-hash"),
        ):
            with self.subTest(source_id=source_id, session_id=session_id):
                with self.assertRaises(ValueError):
                    source_collection.find_source_version(
                        self.pk, source_id, session_id, source_hash,
                    )

    def test_chatgpt_export_import_keeps_sessions_separate_and_is_idempotent(self):
        project = self.archive / 'Demo'
        incoming = project / 'gelen'
        incoming.mkdir(parents=True)
        fixture = Path(__file__).parent / 'fixtures' / 'chatgpt' / 'conversations.json.fixture'
        export = incoming / 'conversations.json'
        original = fixture.read_bytes()
        export.write_bytes(original)
        self.settings['kaynaklar'] = {'claude_code': [], 'codex': [], 'antigravity_brain': []}

        ctxzip.collect(self.settings, self.archive)
        raw_sessions = sorted((project / 'raw' / 'chatgpt').glob('*.json'))
        self.assertEqual(len(raw_sessions), 2)
        self.assertEqual(export.read_bytes(), original)
        self.assertEqual(len([row for row in ctxzip.list_sessions(project) if row[0] == 'chatgpt']), 2)

        ctxzip.write_transcripts(self.settings, self.archive, 'Demo')
        ctxzip.summarize(self.settings, self.archive, 'Demo', True)
        state = ctxzip.load_summary_state(project)
        self.assertEqual(len(state['bolumler']), 2)
        self.assertEqual(len({chapter['oturum'] for chapter in state['bolumler']}), 2)

        ctxzip.collect(self.settings, self.archive)
        ctxzip.write_transcripts(self.settings, self.archive, 'Demo')
        ctxzip.summarize(self.settings, self.archive, 'Demo', True)
        self.assertEqual(ctxzip.load_summary_state(project), state)
        self.assertEqual(len(list((project / 'dokum').glob('*.md'))), 2)
        self.assertEqual(len(list((project / '.ctxzip-events' / 'chatgpt').glob('*.json'))), 2)

    def test_malformed_chatgpt_export_is_rejected_without_rewriting_source(self):
        project = self.archive / 'Demo'
        incoming = project / 'gelen'
        incoming.mkdir(parents=True)
        export = incoming / 'conversations.json'
        export.write_text('{not-json', encoding='utf-8')
        self.settings['kaynaklar'] = {'claude_code': [], 'codex': [], 'antigravity_brain': []}
        with self.assertRaisesRegex(ValueError, 'ChatGPT.*geçersiz'):
            ctxzip.collect(self.settings, self.archive)
        self.assertEqual(export.read_text(encoding='utf-8'), '{not-json')
        self.assertFalse((project / 'raw' / 'chatgpt').exists())

        fixture = Path(__file__).parent / 'fixtures' / 'chatgpt' / 'conversations.json.fixture'
        malformed = json.loads(fixture.read_text(encoding='utf-8'))
        malformed[1]['current_node'] = 'missing-node'
        export.write_text(json.dumps(malformed), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'eksik düğüm'):
            ctxzip.collect(self.settings, self.archive)
        self.assertFalse((project / 'raw' / 'chatgpt').exists())

    def test_numbered_chatgpt_export_files_import_as_individual_sessions(self):
        project = self.archive / 'Demo'
        incoming = project / 'gelen'
        incoming.mkdir(parents=True)
        fixture = Path(__file__).parent / 'fixtures' / 'chatgpt' / 'conversations.json.fixture'
        conversations = json.loads(fixture.read_text(encoding='utf-8'))
        paths = [incoming / 'conversations-1.json', incoming / 'conversations_2.json']
        paths[0].write_text(json.dumps([conversations[0]]), encoding='utf-8')
        paths[1].write_text(json.dumps(conversations[1]), encoding='utf-8')
        originals = [path.read_bytes() for path in paths]
        self.settings['kaynaklar'] = {'claude_code': [], 'codex': [], 'antigravity_brain': []}

        ctxzip.collect(self.settings, self.archive)

        self.assertEqual([path.read_bytes() for path in paths], originals)
        self.assertEqual(len(list((project / 'raw' / 'chatgpt').glob('*.json'))), 2)

    def test_antigravity_deleted_artifacts_are_archived_removed_and_event_cache_cleared(self):
        source_root = self.root / 'antigravity-brain'
        source_session = source_root / 'artifact-session'
        source_session.mkdir(parents=True)
        artifact = source_session / 'task.md'
        artifact.write_text('Sanitized Antigravity artifact.', encoding='utf-8')
        self.settings['kaynaklar'] = {'antigravity_brain': [str(source_root)]}
        self.settings['proje_takma_adlari'] = {'artifact-session': 'Demo'}

        ctxzip.collect(self.settings, self.archive)
        ctxzip.write_transcripts(self.settings, self.archive, 'Demo')
        event_files = list((self.pk / '.ctxzip-events' / 'antigravity').glob('*.json'))
        self.assertEqual(len(event_files), 1)
        active_artifact = self.pk / 'raw' / 'antigravity' / 'artifact-session' / 'task.md'
        self.assertTrue(active_artifact.exists())

        artifact.unlink()
        ctxzip.collect(self.settings, self.archive)
        self.assertFalse(active_artifact.exists())
        history = list((self.pk / 'raw' / 'antigravity-history' / 'artifact-session').glob('*.md'))
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].read_text(encoding='utf-8'), 'Sanitized Antigravity artifact.')

        ctxzip.write_transcripts(self.settings, self.archive, 'Demo')
        self.assertFalse(event_files[0].exists())

    def test_process_exit_after_chapter_write_recovers_without_duplicate_summary(self):
        self.write_source(1)
        ctxzip.collect(self.settings, self.archive)
        ctxzip.write_transcripts(self.settings, self.archive, 'Demo')
        script = (
            "from pathlib import Path; import copy, os, ctxzip; from ctxzip_core import transcripts; "
            "from ctxzip_core import summarizing; "
            "settings=copy.deepcopy(ctxzip.DEFAULT_SETTINGS); "
            "settings.update(aktif_oturum_dk=0, bolum_token=12000, cilt_bolum_sayisi=5); "
            "settings['llm']['model']='process-test'; "
            "summarizing.call_llm=lambda *args: 'Recovered summary'; "
            "summarizing.save_summary_state=lambda *args: os._exit(73); "
            "summarizing.summarize_project(settings, Path(os.environ['CTXZIP_TEST_PROJECT']), False)"
        )
        environment = os.environ.copy()
        environment['CTXZIP_TEST_PROJECT'] = str(self.pk)
        interrupted = subprocess.run(
            [sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
            capture_output=True, text=True, encoding='utf-8', env=environment, check=False,
        )

        self.assertEqual(interrupted.returncode, 73, interrupted.stdout + interrupted.stderr)
        orphan = self.pk / 'bolumler' / 'B0001.md'
        self.assertTrue(orphan.exists())
        self.assertEqual(ctxzip.load_summary_state(self.pk)['bolumler'], [])

        with mock.patch.object(summarizing, 'call_llm', return_value='Recovered summary'):
            summarizing.summarize_project(self.settings, self.pk, manual=False)

        state = ctxzip.load_summary_state(self.pk)
        self.assertEqual(len(state['bolumler']), 1)
        self.assertEqual(state['bolumler'][0]['dosya'], 'B0001.md')
        self.assertEqual(len(list((self.pk / 'bolumler').glob('B*.md'))), 1)

    def test_process_exit_between_event_snapshot_and_transcript_retries_cleanly(self):
        self.write_source(1)
        ctxzip.collect(self.settings, self.archive)
        script = (
            "from pathlib import Path; import os, ctxzip; from ctxzip_core import transcripts; "
            "transcripts.atomic_write_text=lambda *args, **kwargs: os._exit(74); "
            "ctxzip.write_transcripts(ctxzip.DEFAULT_SETTINGS, Path(os.environ['CTXZIP_TEST_ARCHIVE']), 'Demo')"
        )
        environment = os.environ.copy()
        environment['CTXZIP_TEST_ARCHIVE'] = str(self.archive)
        environment['PYTHONIOENCODING'] = 'utf-8'
        interrupted = subprocess.run(
            [sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
            capture_output=True, text=True, encoding='utf-8', env=environment, check=False,
        )

        self.assertEqual(interrupted.returncode, 74, interrupted.stdout + interrupted.stderr)
        event_dir = self.pk / '.ctxzip-events' / 'codex'
        self.assertEqual(len(list(event_dir.glob('*.json'))), 1)
        transcript_dir = self.pk / 'dokum'
        self.assertFalse(list(transcript_dir.glob('*.md')) if transcript_dir.exists() else [])

        ctxzip.write_transcripts(self.settings, self.archive, 'Demo')
        self.assertEqual(len(list(event_dir.glob('*.json'))), 1)
        self.assertEqual(len(list(transcript_dir.glob('*.md'))), 1)

    def test_process_exit_during_source_collection_batch_retries_without_duplicates(self):
        self.write_source(1)
        second_source = self.source.parent / 'z-session.jsonl'
        second_source.write_text(self.source.read_text(encoding='utf-8'), encoding='utf-8')
        script = (
            "import copy, os; from pathlib import Path; import ctxzip; "
            "from ctxzip_core import source_collection; "
            "real_copy=source_collection.atomic_copy2; calls=0;\n"
            "def copy_or_exit(source, target):\n"
            " global calls\n"
            " calls += 1\n"
            " if calls == 2: os._exit(75)\n"
            " return real_copy(source, target)\n"
            "source_collection.atomic_copy2=copy_or_exit; "
            "settings=copy.deepcopy(ctxzip.DEFAULT_SETTINGS); "
            "settings['kaynaklar']={'codex':[os.environ['CTXZIP_TEST_SOURCE_ROOT']]}; "
            "ctxzip.collect(settings, Path(os.environ['CTXZIP_TEST_ARCHIVE']))"
        )
        environment = os.environ.copy()
        environment['CTXZIP_TEST_SOURCE_ROOT'] = str(self.source.parent)
        environment['CTXZIP_TEST_ARCHIVE'] = str(self.archive)

        interrupted = subprocess.run(
            [sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
            capture_output=True, text=True, encoding='utf-8', env=environment, check=False,
        )

        self.assertEqual(interrupted.returncode, 75, interrupted.stdout + interrupted.stderr)
        archived = self.pk / 'raw' / 'codex'
        self.assertEqual([path.name for path in archived.glob('*.jsonl')], ['session.jsonl'])

        ctxzip.collect(self.settings, self.archive)

        self.assertEqual(
            sorted(path.name for path in archived.glob('*.jsonl')),
            ['session.jsonl', 'z-session.jsonl'],
        )
        self.assertEqual(len(list(ctxzip.list_sessions(self.pk))), 2)

    def test_context_task_and_file_select_relevant_edited_summary(self):
        self.pk.mkdir(parents=True)
        chapters = self.pk / 'bolumler'
        chapters.mkdir()
        recent = chapters / 'B0001.md'
        relevant = chapters / 'B0002.md'
        ctxzip.write_summary_file(recent, {'tur': 'bolum'}, 'Recent unrelated', 'Theme update in docs/theme.md. ' + ('unrelated notes. ' * 120))
        ctxzip.write_summary_file(relevant, {'tur': 'bolum'}, 'Older parser decision',
                                  'Keep reviewed parser timeout handling in src/parser.py.')
        # A user's edit must remain the selected text and must not be regenerated.
        edited = relevant.read_text(encoding='utf-8').replace('Keep reviewed', 'Manually reviewed')
        relevant.write_text(edited, encoding='utf-8')
        ctxzip.save_summary_state(self.pk, {'bolumler': [
            {'no': 1, 'dosya': recent.name, 'oturum': 'synthetic/1', 'tur_baslangic': 1, 'tur_bitis': 1, 'cilt': None},
            {'no': 2, 'dosya': relevant.name, 'oturum': 'synthetic/2', 'tur_baslangic': 1, 'tur_bitis': 1, 'cilt': None},
        ], 'ciltler': []})
        budget = 100
        ctxzip.build_context(
            self.settings, self.archive, 'Demo', budget, None,
            task='parser timeout', files=('src\\parser.py',), explain=True,
        )
        context = (self.pk / 'BAGLAM.md').read_text(encoding='utf-8')
        self.assertIn('Manually reviewed parser timeout', context)
        self.assertNotIn('Theme update', context)

    def test_context_marks_summary_with_changed_file_reference_possibly_stale(self):
        self.pk.mkdir(parents=True)
        self.settings['language'] = 'en'
        chapter_dir = self.pk / 'bolumler'
        chapter_dir.mkdir()
        summary_path = chapter_dir / 'B0001.md'
        ctxzip.write_summary_file(
            summary_path,
            {
                'tur': 'bolum', 'no': 1, 'dosyalar': 'src/parser.py',
                'validity_paths': 'src/parser.py', 'validity_head_sha': 'a' * 40,
            },
            'Parser timeout decision',
            'Keep the reviewed timeout policy for the parser.',
        )
        original_summary = summary_path.read_bytes()
        ctxzip.save_summary_state(self.pk, {
            'bolumler': [{
                'no': 1, 'dosya': 'B0001.md', 'oturum': 'codex/synthetic',
                'tur_baslangic': 1, 'tur_bitis': 1, 'cilt': None,
            }],
            'ciltler': [],
        })
        snapshot = GitSnapshot(
            True, 'main', 'b' * 40, True, '1' * 64, '2' * 64, '3' * 64,
            ('src/parser.py',), ('src/parser.py',), 'd' * 64,
        )

        ctxzip.build_context(
            self.settings, self.archive, 'Demo', 4000, None,
            task='parser timeout policy', changed_files=snapshot.changed_files,
            git_snapshot=snapshot,
        )

        context = (self.pk / 'BAGLAM.md').read_text(encoding='utf-8')
        self.assertIn('Parser timeout decision (possibly stale)', context)
        self.assertIn('Keep the reviewed timeout policy for the parser.', context)
        self.assertEqual(summary_path.read_bytes(), original_summary)

        self.settings['language'] = 'tr'
        ctxzip.build_context(
            self.settings, self.archive, 'Demo', 4000, None,
            task='parser timeout policy', changed_files=snapshot.changed_files,
            git_snapshot=snapshot,
        )
        localized_context = (self.pk / 'BAGLAM.md').read_text(encoding='utf-8')
        self.assertIn('Parser timeout decision (muhtemelen eski)', localized_context)
        self.assertEqual(summary_path.read_bytes(), original_summary)

        clean_snapshot = GitSnapshot(
            True, 'main', 'b' * 40, False, '1' * 64, '2' * 64, '3' * 64,
            (), (), 'd' * 64,
        )
        ctxzip.build_context(
            self.settings, self.archive, 'Demo', 4000, None,
            task='parser timeout policy', git_snapshot=clean_snapshot,
        )
        changed_head_context = (self.pk / 'BAGLAM.md').read_text(encoding='utf-8')
        self.assertIn('Parser timeout decision (muhtemelen eski)', changed_head_context)

        matching_snapshot = GitSnapshot(
            True, 'main', 'a' * 40, False, '1' * 64, '2' * 64, '3' * 64,
            (), (), 'd' * 64,
        )
        ctxzip.build_context(
            self.settings, self.archive, 'Demo', 4000, None,
            task='parser timeout policy', git_snapshot=matching_snapshot,
        )
        matching_head_context = (self.pk / 'BAGLAM.md').read_text(encoding='utf-8')
        self.assertNotIn('Parser timeout decision (muhtemelen eski)', matching_head_context)
        self.assertEqual(summary_path.read_bytes(), original_summary)

    def test_context_deduplicates_overlapping_chapter_source_ranges(self):
        self.pk.mkdir(parents=True)
        chapters = self.pk / 'bolumler'
        chapters.mkdir()
        for number, first, last, body in (
            (1, 1, 3, 'Earlier Chapter claim.'),
            (2, 3, 4, 'Later Chapter claim.'),
        ):
            filename = f'B{number:04d}.md'
            ctxzip.write_summary_file(
                chapters / filename,
                {'tur': 'bolum', 'no': number, 'kaynak': 'codex/shared-session',
                 'turlar': f'T{first}-T{last}'},
                f'Chapter {number}', body,
            )
        ctxzip.save_summary_state(self.pk, {'bolumler': [
            {'no': 1, 'dosya': 'B0001.md', 'oturum': 'codex/shared-session',
             'tur_baslangic': 1, 'tur_bitis': 3, 'cilt': None},
            {'no': 2, 'dosya': 'B0002.md', 'oturum': 'codex/shared-session',
             'tur_baslangic': 3, 'tur_bitis': 4, 'cilt': None},
        ], 'ciltler': []})
        self.settings['language'] = 'en'

        with mock.patch('builtins.print') as output:
            ctxzip.build_context(self.settings, self.archive, 'Demo', 4000, None, explain=True)

        context = (self.pk / 'BAGLAM.md').read_text(encoding='utf-8')
        explanation = ' '.join(str(arg) for call in output.call_args_list for arg in call.args)
        self.assertIn('Later Chapter claim.', context)
        self.assertIn('Earlier Chapter claim.', context)
        self.assertNotIn('Excluded Chapter 1', explanation)

    def test_context_deduplicates_overlapping_volume_source_ranges(self):
        self.pk.mkdir(parents=True)
        chapters_dir = self.pk / 'bolumler'
        chapters_dir.mkdir()
        volumes_dir = self.pk / 'ciltler'
        volumes_dir.mkdir()
        chapters = []
        for number in range(1, 5):
            filename = f'B{number:04d}.md'
            ctxzip.write_summary_file(
                chapters_dir / filename,
                {'tur': 'bolum', 'no': number, 'kaynak': 'codex/shared-session',
                 'turlar': f'T{number}-T{number}'},
                f'Chapter {number}', f'Chapter {number} body.',
            )
            chapters.append({
                'no': number, 'dosya': filename, 'oturum': 'codex/shared-session',
                'tur_baslangic': number, 'tur_bitis': number,
                'cilt': 1 if number < 4 else 2,
            })
        for number, chapters_in_volume, body in (
            (1, [1, 2, 3], 'Earlier Volume claim.'),
            (2, [3, 4], 'Later Volume claim.'),
        ):
            ctxzip.write_summary_file(
                volumes_dir / f'C{number:03d}.md',
                {'tur': 'cilt', 'no': number,
                 'bolumler': f"B{chapters_in_volume[0]}-B{chapters_in_volume[-1]}"},
                f'Volume {number}', body,
            )
        # The state simulates overlapping legacy volume membership for Chapter 3.
        ctxzip.save_summary_state(self.pk, {
            'bolumler': chapters,
            'ciltler': [
                {'no': 1, 'dosya': 'C001.md', 'bolumler': [1, 2, 3]},
                {'no': 2, 'dosya': 'C002.md', 'bolumler': [3, 4]},
            ],
        })
        self.settings['language'] = 'en'

        with mock.patch('builtins.print') as output:
            ctxzip.build_context(self.settings, self.archive, 'Demo', 4000, None, explain=True)

        context = (self.pk / 'BAGLAM.md').read_text(encoding='utf-8')
        explanation = ' '.join(str(arg) for call in output.call_args_list for arg in call.args)
        self.assertIn('Later Volume claim.', context)
        self.assertIn('Earlier Volume claim.', context)
        self.assertNotIn('Excluded Volume 1', explanation)

    def test_context_excludes_fully_covered_summary_and_explains_it(self):
        self.pk.mkdir(parents=True)
        chapters_dir = self.pk / 'bolumler'
        chapters_dir.mkdir()
        ctxzip.write_summary_file(
            chapters_dir / 'B0001.md',
            {'tur': 'bolum', 'no': 1, 'kaynak': 'codex/session', 'turlar': 'T2-T2'},
            'Narrow chapter', 'Redundant narrow claim.',
        )
        ctxzip.write_summary_file(
            chapters_dir / 'B0002.md',
            {'tur': 'bolum', 'no': 2, 'kaynak': 'codex/session', 'turlar': 'T1-T3'},
            'Complete chapter', 'Complete source coverage claim.',
        )
        ctxzip.save_summary_state(self.pk, {'bolumler': [
            {'no': 1, 'dosya': 'B0001.md', 'oturum': 'codex/session',
             'tur_baslangic': 2, 'tur_bitis': 2, 'cilt': None},
            {'no': 2, 'dosya': 'B0002.md', 'oturum': 'codex/session',
             'tur_baslangic': 1, 'tur_bitis': 3, 'cilt': None},
        ], 'ciltler': []})
        self.settings['language'] = 'en'

        with mock.patch('builtins.print') as output:
            ctxzip.build_context(self.settings, self.archive, 'Demo', 4000, None, explain=True)

        context = (self.pk / 'BAGLAM.md').read_text(encoding='utf-8')
        explanation = ' '.join(str(arg) for call in output.call_args_list for arg in call.args)
        self.assertIn('Complete source coverage claim.', context)
        self.assertNotIn('Redundant narrow claim.', context)
        self.assertIn('full source range is already covered', explanation)

    def test_context_keeps_manually_edited_summary_even_when_range_is_covered(self):
        self.pk.mkdir(parents=True)
        chapters_dir = self.pk / 'bolumler'
        chapters_dir.mkdir()
        edited_path = chapters_dir / 'B0001.md'
        ctxzip.write_summary_file(
            edited_path,
            {'tur': 'bolum', 'no': 1, 'kaynak': 'codex/session', 'turlar': 'T2-T2'},
            'Edited narrow chapter', 'Original generated claim.',
        )
        edited_path.write_text(
            edited_path.read_text(encoding='utf-8').replace(
                'Original generated claim.', 'User-curated clarification.',
            ),
            encoding='utf-8',
        )
        ctxzip.write_summary_file(
            chapters_dir / 'B0002.md',
            {'tur': 'bolum', 'no': 2, 'kaynak': 'codex/session', 'turlar': 'T1-T3'},
            'Complete chapter', 'Complete source coverage claim.',
        )
        ctxzip.save_summary_state(self.pk, {'bolumler': [
            {'no': 1, 'dosya': 'B0001.md', 'oturum': 'codex/session',
             'tur_baslangic': 2, 'tur_bitis': 2, 'cilt': None},
            {'no': 2, 'dosya': 'B0002.md', 'oturum': 'codex/session',
             'tur_baslangic': 1, 'tur_bitis': 3, 'cilt': None},
        ], 'ciltler': []})

        ctxzip.build_context(self.settings, self.archive, 'Demo', 4000, None)

        context = (self.pk / 'BAGLAM.md').read_text(encoding='utf-8')
        self.assertIn('User-curated clarification.', context)

    def test_context_from_current_git_diff_uses_changed_paths(self):
        self.pk.mkdir(parents=True)
        chapters = self.pk / 'bolumler'
        chapters.mkdir()
        recent = chapters / 'B0001.md'
        relevant = chapters / 'B0002.md'
        ctxzip.write_summary_file(recent, {'tur': 'bolum'}, 'Recent theme update', 'Theme changed in docs/theme.css. ' + ('unrelated note. ' * 120))
        ctxzip.write_summary_file(relevant, {'tur': 'bolum'}, 'Parser fix', 'Parser timeout behavior in src/parser.py.')
        ctxzip.save_summary_state(self.pk, {'bolumler': [
            {'no': 1, 'dosya': recent.name, 'oturum': 'synthetic/1', 'tur_baslangic': 1, 'tur_bitis': 1, 'cilt': None},
            {'no': 2, 'dosya': relevant.name, 'oturum': 'synthetic/2', 'tur_baslangic': 1, 'tur_bitis': 1, 'cilt': None},
        ], 'ciltler': []})
        settings_path = self.root / 'settings.json'
        settings = copy.deepcopy(ctxzip.DEFAULT_SETTINGS)
        settings.update(arsiv_klasoru=str(self.archive), language='en')
        settings_path.write_text(json.dumps(settings), encoding='utf-8')
        token_budget = 100
        with mock.patch.object(ctxzip.sys, 'argv', [
            'ctxzip.py', '--settings', str(settings_path), '--language', 'en',
            'context', 'Demo', '--token', str(token_budget), '--from-git-diff', '--explain',
        ]), mock.patch.object(
            ctxzip, 'capture_git_snapshot', return_value=SimpleNamespace(
                is_repository=True, changed_files=('src/parser.py',), branch='main',
                head_sha='a' * 40, dirty=True, fingerprint='b' * 64,
            ),
        ) as capture:
            ctxzip.main()
        capture.assert_called_once()
        context = (self.pk / 'BAGLAM.md').read_text(encoding='utf-8')
        self.assertIn('Parser timeout behavior', context)
        self.assertNotIn('Theme changed', context)

    def test_context_planner_includes_provenanced_knowledge_and_marks_stale_tests(self):
        self.pk.mkdir(parents=True)
        self.settings['language'] = 'en'
        store = KnowledgeStore(self.pk / 'knowledge')
        source = SourceRef('codex', 'fixture-session', 'a' * 64, '1', 4, 8)
        reference = EventReference('event:synthetic', source)
        old_decision = DecisionRecord(
            'decision:old', 'Use the legacy parser.', KnowledgeStatus.CONFIRMED,
            RecordActor.USER, '2026-01-01T00:00:00Z', (reference,),
        )
        store.add_decision(old_decision)
        fake_secret = 'sk-' + 'R' * 32
        active_decision = DecisionRecord(
            'decision:active', f'Keep this API token={fake_secret} private.',
            KnowledgeStatus.CONFIRMED, RecordActor.USER, '2026-01-02T00:00:00Z',
            (reference,), supersedes=old_decision.id,
            validity_paths=('ctxzip_core/parsers.py',), validity_head_sha='a' * 40,
        )
        store.add_decision(active_decision)
        store.add_decision(DecisionRecord(
            'decision:parser-events', 'Keep parser events linked to source hashes.',
            KnowledgeStatus.CONFIRMED, RecordActor.USER, '2026-01-04T00:00:00Z',
            (reference,),
        ))
        store.add_decision(DecisionRecord(
            'decision:theme', 'Refresh theme colors in the documentation.',
            KnowledgeStatus.CONFIRMED, RecordActor.USER, '2026-01-05T00:00:00Z',
            (reference,),
        ))
        old_constraint = ConstraintRecord(
            'constraint:old-privacy', 'Keep all files in a single archive directory.', 'privacy',
            KnowledgeStatus.CONFIRMED, RecordActor.USER, '2026-01-01T00:00:00Z', (reference,),
        )
        store.add_constraint(old_constraint)
        store.add_constraint(ConstraintRecord(
            'constraint:privacy', 'Never commit private sessions.', 'privacy',
            KnowledgeStatus.CONFIRMED, RecordActor.USER, '2026-01-02T00:00:00Z', (reference,),
            supersedes=old_constraint.id,
        ))
        store.add_test_evidence(TestEvidence(
            'test:old-pass', RecordActor.TEST_RUNNER, 'python -m unittest', TestResult.PASSED,
            0, '2026-01-03T00:00:00Z', ('tests',), 'main', 'a' * 40, 'c' * 64, True,
        ))
        store.add_file_mention(FileMentionRecord(
            'file:parser', 'ctxzip_core/parsers.py', 'parse_session', KnowledgeStatus.OBSERVED,
            RecordActor.AGENT, '2026-01-02T00:00:00Z', (reference,),
        ))
        store.add_file_mention(FileMentionRecord(
            'file:theme', 'docs/theme.css', None, KnowledgeStatus.OBSERVED,
            RecordActor.AGENT, '2026-01-03T00:00:00Z', (reference,),
        ))
        store.add_task(TaskRecord(
            'task:parser', 'Validate parser event extraction.', TaskStatus.IN_PROGRESS,
            RecordActor.AGENT, '2026-01-02T00:00:00Z', (reference,),
        ))
        store.add_open_question(OpenQuestionRecord(
            'question:source', 'Which source adapter should be validated next?', QuestionStatus.OPEN,
            RecordActor.AGENT, '2026-01-02T00:00:00Z', (reference,),
        ))
        snapshot = GitSnapshot(
            True, 'main', 'b' * 40, True, '1' * 64, '2' * 64, '3' * 64,
            ('ctxzip_core/parsers.py',), ('ctxzip_core/parsers.py',), 'd' * 64,
        )

        with mock.patch('builtins.print') as output:
            ctxzip.build_context(
                self.settings, self.archive, 'Demo', 5000, None,
                task='parser events', git_snapshot=snapshot, changed_files=snapshot.changed_files,
                files=('ctxzip_core/parsers.py',), symbols=('parse_session',), explain=True,
            )

        context = (self.pk / 'BAGLAM.md').read_text(encoding='utf-8')
        metadata = parse_metadata_block(context)
        self.assertEqual(metadata['schema_version'], 1)
        self.assertEqual(metadata['language'], 'en')
        self.assertEqual(metadata['budget']['limit'], 5000)
        self.assertEqual(metadata['git']['head_sha'], 'b' * 40)
        self.assertTrue(any('fixture-session#T4/R8' in source for source in metadata['sources']))
        self.assertIn('## Current task', context)
        self.assertIn('## Hard constraints', context)
        self.assertIn('Never commit private sessions.', context)
        self.assertNotIn('single archive directory', context)
        self.assertIn('## Active decisions', context)
        self.assertIn('Decision (confirmed) (possibly stale)', context)
        self.assertIn('Keep parser events linked to source hashes.', context)
        self.assertIn('Refresh theme colors in the documentation.', context)
        self.assertLess(
            context.index('Keep parser events linked to source hashes.'),
            context.index('Refresh theme colors in the documentation.'),
        )
        self.assertIn('## Current repository state', context)
        self.assertIn('## Test evidence', context)
        self.assertIn('Freshness: stale', context)
        self.assertIn('## Relevant files and symbols', context)
        self.assertIn('parse_session', context)
        self.assertIn('File and symbol mention (possibly stale)', context)
        self.assertLess(context.index('ctxzip_core/parsers.py'), context.index('docs/theme.css'))
        self.assertIn('## Open tasks', context)
        self.assertIn('## Open questions', context)
        self.assertIn('fixture-session#T4/R8@aaaaaaaaaaaa', context)
        self.assertNotIn('Use the legacy parser', context)
        self.assertNotIn(fake_secret, context)
        self.assertIn('[REDACTED]', context)
        explanation = ' '.join(str(arg) for call in output.call_args_list for arg in call.args)
        self.assertIn('task term overlap', explanation)
        self.assertIn('file match ctxzip_core/parsers.py', explanation)
        self.assertIn('symbol match parse_session', explanation)

        ctxzip.build_context(
            self.settings, self.archive, 'Demo', 5000, None,
            task='parser events',
        )
        unknown_context = (self.pk / 'BAGLAM.md').read_text(encoding='utf-8')
        self.assertIn('File and symbol mention (freshness unknown)', unknown_context)

    def test_balanced_context_profile_reports_reserved_capacity(self):
        self.pk.mkdir(parents=True)
        self.settings['language'] = 'en'
        with mock.patch('builtins.print') as output:
            ctxzip.build_context(
                self.settings, self.archive, 'Demo', 12000, None,
                explain=True, budget_profile='balanced',
            )
        rendered = ' '.join(str(argument) for call in output.call_args_list for argument in call.args)
        self.assertIn('balanced allocates ~1500 tokens to recent raw turns (~0 used)', rendered)
        self.assertIn('~750 safety tokens', rendered)

    def test_balanced_context_includes_only_uncovered_recent_raw_turns(self):
        self.pk.mkdir(parents=True)
        self.settings['language'] = 'en'
        raw_dir = self.pk / 'raw' / 'codex'
        raw_dir.mkdir(parents=True)
        source_path = raw_dir / 'session-raw.jsonl'
        records = [{
            'type': 'session_meta', 'timestamp': '2026-01-01T00:00:00Z', 'ordinal': 1,
            'payload': {'cwd': '/workspace/demo', 'git': {'branch': 'main'}},
        }]
        messages = [
            ('user', 'This raw turn is already covered.'),
            ('assistant', 'Old answer.'),
            ('user', 'Uncovered recent request alpha.'),
            ('assistant', 'Uncovered recent answer alpha.'),
            ('user', 'Uncovered recent request beta.'),
            ('assistant', 'Uncovered recent answer beta.'),
        ]
        for ordinal, (role, text) in enumerate(messages, start=2):
            records.append({
                'type': 'response_item', 'timestamp': f'2026-01-01T00:00:{ordinal:02d}Z',
                'ordinal': ordinal,
                'payload': {
                    'type': 'message', 'role': role,
                    'content': [{'type': 'input_text' if role == 'user' else 'output_text', 'text': text}],
                },
            })
        source_path.write_text('\n'.join(json.dumps(record) for record in records) + '\n', encoding='utf-8')
        chapter_dir = self.pk / 'bolumler'
        chapter_dir.mkdir()
        ctxzip.write_summary_file(
            chapter_dir / 'B0001.md', {'tur': 'bolum', 'kaynak': 'codex/session-raw', 'turlar': 'T1-T1'},
            'Covered Chapter', 'This Chapter summarizes the first source turn.',
        )
        ctxzip.save_summary_state(self.pk, {
            'bolumler': [{
                'no': 1, 'dosya': 'B0001.md', 'oturum': 'codex/session-raw',
                'tur_baslangic': 1, 'tur_bitis': 1, 'cilt': None,
            }],
            'ciltler': [],
        })

        ctxzip.build_context(
            self.settings, self.archive, 'Demo', 32000, None,
            budget_profile='balanced', explain=True,
        )

        context = (self.pk / 'BAGLAM.md').read_text(encoding='utf-8')
        metadata = parse_metadata_block(context)
        self.assertIn('## Recent raw turns', context)
        self.assertIn('Uncovered recent request alpha.', context)
        self.assertIn('Uncovered recent request beta.', context)
        self.assertNotIn('This raw turn is already covered.', context)
        self.assertIn('## Relevant history', context)
        self.assertTrue(any('codex/session-raw#T2@' in source for source in metadata['sources']))
        self.assertTrue(any('codex/session-raw#T3@' in source for source in metadata['sources']))
        self.assertFalse(any('codex/session-raw#T1@' in source for source in metadata['sources']))
        self.assertGreater(metadata['budget']['recent_raw_used'], 0)
        self.assertEqual(
            metadata['budget']['recent_raw_allocation'],
            metadata['budget']['recent_raw_used'] + metadata['budget']['recent_raw_reserved'],
        )

    def test_changed_chapter_source_is_replaced_by_raw_turns_without_editing_summary(self):
        self.write_source(1)
        self.pipeline()
        chapter_path = self.pk / 'bolumler' / 'B0001.md'
        chapter_metadata, _body = ctxzip.read_summary_body(chapter_path)
        ctxzip.write_summary_file(
            chapter_path, chapter_metadata, 'Chapter 1', 'Generated old summary.',
        )
        generated_summary = chapter_path.read_bytes()

        changed_source = self.source.read_text(encoding='utf-8')
        changed_source = changed_source.replace('Question 0', 'Changed source question')
        changed_source = changed_source.replace('Answer 0', 'Changed source answer')
        self.source.write_text(changed_source, encoding='utf-8')
        os.utime(self.source, (1, 1))
        ctxzip.collect(self.settings, self.archive)

        ctxzip.build_context(
            self.settings, self.archive, 'Demo', 32000, None, budget_profile='balanced',
        )

        context = (self.pk / 'BAGLAM.md').read_text(encoding='utf-8')
        metadata = parse_metadata_block(context)
        self.assertIn('Changed source question', context)
        self.assertIn('Changed source answer', context)
        self.assertNotIn('Generated old summary.', context)
        self.assertTrue(any('codex/session' in source and '#T1@' in source for source in metadata['sources']))
        self.assertEqual(chapter_path.read_bytes(), generated_summary)
        self.assertFalse(ctxzip.is_manually_edited(chapter_path))

        # A readable but shortened source that no longer covers the Chapter range is stale too.
        source_lines = self.source.read_text(encoding='utf-8').splitlines()
        self.source.write_text('\n'.join(source_lines[:2]) + '\n', encoding='utf-8')
        os.utime(self.source, (1, 1))
        ctxzip.collect(self.settings, self.archive)
        ctxzip.build_context(
            self.settings, self.archive, 'Demo', 32000, None, budget_profile='balanced',
        )
        shrunk_context = (self.pk / 'BAGLAM.md').read_text(encoding='utf-8')
        self.assertIn('Changed source question', shrunk_context)
        self.assertNotIn('Generated old summary.', shrunk_context)
        self.assertEqual(chapter_path.read_bytes(), generated_summary)

    def test_parser_version_mismatch_skips_volume_and_keeps_current_chapters(self):
        self.settings['language'] = 'en'
        self.write_source(2)
        self.pipeline()
        session_key = ctxzip.load_summary_state(self.pk)['bolumler'][0]['oturum']
        source_path = next((self.pk / 'raw' / 'codex').glob('*.jsonl'))
        turns, _session = ctxzip.read_session(
            'codex', source_path, self.settings, self.settings['language'],
        )
        first_hash = chapter_source_hash(
            turns, 1, 1, self.settings['bolum_token'], self.settings['language'],
        )
        second_hash = chapter_source_hash(
            turns, 2, 2, self.settings['bolum_token'], self.settings['language'],
        )
        self.assertIsNotNone(first_hash)
        self.assertIsNotNone(second_hash)

        chapter_dir = self.pk / 'bolumler'
        for number, source_hash, body in (
            (1, first_hash, 'First chapter summary'),
            (2, second_hash, 'Current sibling chapter summary'),
        ):
            ctxzip.write_summary_file(
                chapter_dir / f'B{number:04d}.md',
                {'tur': 'bolum', 'no': number, 'kaynak': session_key,
                 'source_language': self.settings['language'],
                 'parser_version': '0' if number == 1 else ctxzip.PARSER_VERSIONS['codex'],
                 'turlar': f'T{number}-T{number}', 'kaynak_hash': source_hash},
                f'Chapter {number}', body,
            )
        (self.pk / 'ciltler').mkdir(exist_ok=True)
        ctxzip.write_summary_file(
            self.pk / 'ciltler' / 'C001.md', {'tur': 'cilt', 'no': 1, 'bolumler': 'B1-B2'},
            'Volume 1', 'Old volume summary',
        )
        ctxzip.save_summary_state(self.pk, {
            'bolumler': [
                {'no': 1, 'dosya': 'B0001.md', 'oturum': session_key,
                 'tur_baslangic': 1, 'tur_bitis': 1, 'cilt': 1},
                {'no': 2, 'dosya': 'B0002.md', 'oturum': session_key,
                 'tur_baslangic': 2, 'tur_bitis': 2, 'cilt': 1},
            ],
            'ciltler': [{'no': 1, 'dosya': 'C001.md', 'bolumler': [1, 2]}],
        })

        self.settings['language'] = 'tr'
        self.assertEqual(ctxzip._stale_chapter_files(self.pk, self.settings,
                         ctxzip.load_summary_state(self.pk)), {'B0001.md'})
        ctxzip.build_context(
            self.settings, self.archive, 'Demo', 32000, None, budget_profile='balanced',
        )

        context = (self.pk / 'BAGLAM.md').read_text(encoding='utf-8')
        self.assertIn('Question 0', context)
        self.assertIn('Current sibling chapter summary', context)
        self.assertNotIn('Old volume summary', context)
        self.assertNotIn('First chapter summary', context)

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

    def test_chapter_file_orphan_is_reused_after_state_write_failure(self):
        self.write_source(1)
        ctxzip.collect(self.settings, self.archive)
        ctxzip.write_transcripts(self.settings, self.archive, 'Demo')

        with mock.patch.object(summarizing, 'save_summary_state', side_effect=OSError('simulated state failure')):
            with self.assertRaisesRegex(OSError, 'simulated state failure'):
                summarizing.summarize_project(self.settings, self.pk, manual=True)

        orphan = self.pk / 'bolumler' / 'B0001.md'
        self.assertTrue(orphan.exists())
        self.assertEqual(ctxzip.load_summary_state(self.pk)['bolumler'], [])
        edited_content = orphan.read_text(encoding='utf-8').replace(
            ctxzip.SUMMARY_PLACEHOLDER, 'User recovered this interrupted Chapter.'
        )
        orphan.write_text(edited_content, encoding='utf-8')
        summarizing.summarize_project(self.settings, self.pk, manual=True)
        state = ctxzip.load_summary_state(self.pk)
        self.assertEqual(len(state['bolumler']), 1)
        self.assertEqual(state['bolumler'][0]['dosya'], 'B0001.md')
        self.assertIn('User recovered this interrupted Chapter.', orphan.read_text(encoding='utf-8'))
        self.assertEqual(sorted(path.name for path in (self.pk / 'bolumler').glob('B*.md')
                                if not path.name.endswith('.istem.md')), ['B0001.md'])

    def test_process_exit_after_chapter_prompt_preserves_user_edit_on_retry(self):
        self.write_source(1)
        ctxzip.collect(self.settings, self.archive)
        ctxzip.write_transcripts(self.settings, self.archive, 'Demo')
        script = """
import os
from pathlib import Path
import ctxzip
from ctxzip_core import summarizing

summarizing.write_summary_file = lambda *args, **kwargs: os._exit(77)
settings = dict(ctxzip.DEFAULT_SETTINGS)
settings['kaynaklar'] = {'codex': []}
summarizing.summarize_project(settings, Path(os.environ['CTXZIP_TEST_PROJECT']), manual=True)
"""
        environment = os.environ.copy()
        environment['CTXZIP_TEST_PROJECT'] = str(self.pk)
        environment['PYTHONIOENCODING'] = 'utf-8'
        interrupted = subprocess.run(
            [sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
            capture_output=True, text=True, encoding='utf-8', env=environment, check=False,
        )
        self.assertEqual(interrupted.returncode, 77, interrupted.stdout + interrupted.stderr)

        prompt = self.pk / 'bolumler' / 'B0001.istem.md'
        edited_prompt = prompt.read_bytes() + b'\nUser prompt edit after interruption.\n'
        prompt.write_bytes(edited_prompt)
        summarizing.summarize_project(self.settings, self.pk, manual=True)

        self.assertEqual(prompt.read_bytes(), edited_prompt)
        self.assertEqual(len(ctxzip.load_summary_state(self.pk)['bolumler']), 1)
        self.assertEqual(len(list((self.pk / 'bolumler').glob('B????.md'))), 1)

    def test_process_exit_after_volume_prompt_preserves_user_edit_on_retry(self):
        self.write_source(1)
        self.settings['cilt_bolum_sayisi'] = 2
        self.pipeline()
        chapter = self.pk / 'bolumler' / 'B0001.md'
        chapter.write_text(
            chapter.read_text(encoding='utf-8').replace(ctxzip.SUMMARY_PLACEHOLDER, 'Completed chapter'),
            encoding='utf-8',
        )
        script = """
import os
from pathlib import Path
import ctxzip
from ctxzip_core import summarizing

summarizing.write_summary_file = lambda *args, **kwargs: os._exit(77)
settings = dict(ctxzip.DEFAULT_SETTINGS)
settings.update(aktif_oturum_dk=0, cilt_bolum_sayisi=1)
settings['kaynaklar'] = {'codex': []}
summarizing.summarize_project(settings, Path(os.environ['CTXZIP_TEST_PROJECT']), manual=True)
"""
        environment = os.environ.copy()
        environment['CTXZIP_TEST_PROJECT'] = str(self.pk)
        environment['PYTHONIOENCODING'] = 'utf-8'
        interrupted = subprocess.run(
            [sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
            capture_output=True, text=True, encoding='utf-8', env=environment, check=False,
        )
        self.assertEqual(interrupted.returncode, 77, interrupted.stdout + interrupted.stderr)

        prompt = self.pk / 'ciltler' / 'C001.istem.md'
        edited_prompt = prompt.read_bytes() + b'\nUser prompt edit after interruption.\n'
        prompt.write_bytes(edited_prompt)
        self.settings['cilt_bolum_sayisi'] = 1
        summarizing.summarize_project(self.settings, self.pk, manual=True)

        self.assertEqual(prompt.read_bytes(), edited_prompt)
        state = ctxzip.load_summary_state(self.pk)
        self.assertEqual(len(state['ciltler']), 1)
        self.assertEqual(state['bolumler'][0]['cilt'], 1)
        self.assertEqual(len(list((self.pk / 'ciltler').glob('C[0-9][0-9][0-9].md'))), 1)

    def test_invalid_orphan_blocks_summary_without_rewriting_file(self):
        chapter_dir = self.pk / 'bolumler'
        chapter_dir.mkdir(parents=True)
        invalid_orphan = chapter_dir / 'B0001.md'
        ctxzip.write_summary_file(
            invalid_orphan, {'tur': 'cilt', 'no': 1, 'bolumler': 'B1-B2'},
            'Unexpected Volume', 'Preserve this file.',
        )
        original = invalid_orphan.read_bytes()
        self.settings['language'] = 'en'

        with mock.patch('builtins.print') as output:
            result = summarizing.summarize_project(self.settings, self.pk, manual=False)

        self.assertIs(result, False)
        self.assertEqual(invalid_orphan.read_bytes(), original)
        self.assertFalse((self.pk / 'durum.json').exists())

        printed = ' '.join(str(arg) for call in output.call_args_list for arg in call.args)
        self.assertIn('Cannot safely recover B0001.md', printed)

    def test_collect_retry_finishes_remaining_source_after_copy_failure(self):
        self.write_source(1)
        second_source = self.source.parent / 'z-session.jsonl'
        second_source.write_text(self.source.read_text(encoding='utf-8'), encoding='utf-8')
        real_copy = ctxzip.atomic_copy2
        copy_calls = 0

        def fail_second_copy(source, target):
            nonlocal copy_calls
            copy_calls += 1
            if copy_calls == 2:
                raise OSError('simulated source copy failure')
            return real_copy(source, target)

        with mock.patch.object(source_collection, 'atomic_copy2', side_effect=fail_second_copy):
            with self.assertRaisesRegex(OSError, 'simulated source copy failure'):
                ctxzip.collect(self.settings, self.archive)

        archived = self.pk / 'raw' / 'codex'
        self.assertEqual(len(list(archived.glob('*.jsonl'))), 1)
        ctxzip.collect(self.settings, self.archive)
        archived_files = sorted(archived.glob('*.jsonl'))
        self.assertEqual([path.name for path in archived_files], ['session.jsonl', 'z-session.jsonl'])
        self.assertEqual(len(list(ctxzip.list_sessions(self.pk))), 2)

    def test_transcript_retry_rewrites_partial_batch_without_duplicate_files(self):
        self.write_source(1)
        second_source = self.source.parent / 'z-session.jsonl'
        second_source.write_text(self.source.read_text(encoding='utf-8'), encoding='utf-8')
        ctxzip.collect(self.settings, self.archive)
        real_write = transcripts.atomic_write_text
        write_calls = 0

        def fail_second_write(path, content, encoding='utf-8'):
            nonlocal write_calls
            write_calls += 1
            if write_calls == 2:
                raise OSError('simulated transcript write failure')
            return real_write(path, content, encoding)

        with mock.patch.object(transcripts, 'atomic_write_text', side_effect=fail_second_write):
            with self.assertRaisesRegex(OSError, 'simulated transcript write failure'):
                ctxzip.write_transcripts(self.settings, self.archive, 'Demo')

        transcript_dir = self.pk / 'dokum'
        self.assertEqual(len(list(transcript_dir.glob('*.md'))), 1)
        ctxzip.write_transcripts(self.settings, self.archive, 'Demo')
        self.assertEqual(len(list(transcript_dir.glob('*.md'))), 2)

    def test_multi_project_summary_retry_keeps_completed_project_idempotent(self):
        self.write_source(1)
        alpha_source = self.source
        alpha_content = alpha_source.read_text(encoding='utf-8').replace('/projects/Demo', '/projects/Alpha')
        alpha_source.write_text(alpha_content, encoding='utf-8')
        beta_source = alpha_source.parent / 'beta.jsonl'
        beta_source.write_text(alpha_content.replace('/projects/Alpha', '/projects/Beta'), encoding='utf-8')
        self.settings['llm']['model'] = 'test-model'
        ctxzip.collect(self.settings, self.archive)

        with mock.patch.object(summarizing, 'call_llm', side_effect=['Alpha summary', RuntimeError('offline')]):
            ctxzip.summarize(self.settings, self.archive, None, manual=False)

        alpha_dir = self.archive / 'Alpha'
        beta_dir = self.archive / 'Beta'
        self.assertEqual(len(ctxzip.load_summary_state(alpha_dir)['bolumler']), 1)
        self.assertEqual(ctxzip.load_summary_state(beta_dir)['bolumler'], [])

        with mock.patch.object(summarizing, 'call_llm', return_value='Beta summary') as call:
            ctxzip.summarize(self.settings, self.archive, None, manual=False)
            self.assertEqual(call.call_count, 1)
        self.assertEqual(len(ctxzip.load_summary_state(alpha_dir)['bolumler']), 1)
        self.assertEqual(len(ctxzip.load_summary_state(beta_dir)['bolumler']), 1)

    def test_process_exit_during_multi_project_summarization_recovers_orphan_once(self):
        self.write_source(1)
        alpha_source = self.source
        alpha_content = alpha_source.read_text(encoding='utf-8').replace('/projects/Demo', '/projects/Alpha')
        alpha_source.write_text(alpha_content, encoding='utf-8')
        beta_source = alpha_source.parent / 'beta.jsonl'
        beta_source.write_text(alpha_content.replace('/projects/Alpha', '/projects/Beta'), encoding='utf-8')
        ctxzip.collect(self.settings, self.archive)

        script = """
import copy, os
from pathlib import Path
import ctxzip
from ctxzip_core import summarizing

real_save = summarizing.save_summary_state
save_calls = 0
def exit_before_second_project_state(project_dir, state):
    global save_calls
    save_calls += 1
    if save_calls == 3:
        os._exit(77)
    return real_save(project_dir, state)

summarizing.save_summary_state = exit_before_second_project_state
settings = copy.deepcopy(ctxzip.DEFAULT_SETTINGS)
settings.update(aktif_oturum_dk=0, cilt_bolum_sayisi=5)
settings['kaynaklar'] = {'codex': []}
ctxzip.summarize(settings, Path(os.environ['CTXZIP_TEST_ARCHIVE']), None, True)
        """
        environment = os.environ.copy()
        environment['CTXZIP_TEST_ARCHIVE'] = str(self.archive)
        environment['PYTHONIOENCODING'] = 'utf-8'
        interrupted = subprocess.run(
            [sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
            capture_output=True, text=True, encoding='utf-8', env=environment, check=False,
        )

        self.assertEqual(interrupted.returncode, 77, interrupted.stdout + interrupted.stderr)
        alpha_dir = self.archive / 'Alpha'
        beta_dir = self.archive / 'Beta'
        self.assertEqual(len(ctxzip.load_summary_state(alpha_dir)['bolumler']), 1)
        self.assertEqual(ctxzip.load_summary_state(beta_dir)['bolumler'], [])
        beta_orphan = beta_dir / 'bolumler' / 'B0001.md'
        orphan_bytes = beta_orphan.read_bytes()
        self.assertTrue(orphan_bytes)

        ctxzip.summarize(self.settings, self.archive, None, True)

        self.assertEqual(len(ctxzip.load_summary_state(alpha_dir)['bolumler']), 1)
        self.assertEqual(len(ctxzip.load_summary_state(beta_dir)['bolumler']), 1)
        self.assertEqual(beta_orphan.read_bytes(), orphan_bytes)
        chapter_pattern = 'B[0-9][0-9][0-9][0-9].md'
        self.assertEqual(len(list((alpha_dir / 'bolumler').glob(chapter_pattern))), 1)
        self.assertEqual(len(list((beta_dir / 'bolumler').glob(chapter_pattern))), 1)
        self.assertEqual(len(list((alpha_dir / 'bolumler').glob('B*.istem.md'))), 1)
        self.assertEqual(len(list((beta_dir / 'bolumler').glob('B*.istem.md'))), 1)

    def test_orphan_volume_is_reconciled_after_final_state_write_failure(self):
        self.write_source(1)
        self.settings['cilt_bolum_sayisi'] = 1
        self.settings['llm']['model'] = 'test-model'
        ctxzip.collect(self.settings, self.archive)
        ctxzip.write_transcripts(self.settings, self.archive, 'Demo')
        save_state = summarizing.save_summary_state
        save_calls = 0

        def save_chapter_then_fail_volume(project_dir, state):
            nonlocal save_calls
            save_calls += 1
            if save_calls == 1:
                return save_state(project_dir, state)
            raise OSError('simulated volume state failure')

        with mock.patch.object(summarizing, 'call_llm', return_value='Generated summary'):
            with mock.patch.object(summarizing, 'save_summary_state', side_effect=save_chapter_then_fail_volume):
                with self.assertRaisesRegex(OSError, 'simulated volume state failure'):
                    summarizing.summarize_project(self.settings, self.pk, manual=False)

        persisted = ctxzip.load_summary_state(self.pk)
        self.assertEqual(persisted['ciltler'], [])
        self.assertIsNone(persisted['bolumler'][0]['cilt'])
        self.assertTrue((self.pk / 'ciltler' / 'C001.md').exists())
        orphan_volume = self.pk / 'ciltler' / 'C001.md'
        user_edited_volume = orphan_volume.read_text(encoding='utf-8').replace(
            'Generated summary', 'User recovered this interrupted Volume'
        )
        orphan_volume.write_text(user_edited_volume, encoding='utf-8')

        with mock.patch.object(summarizing, 'call_llm') as call:
            summarizing.summarize_project(self.settings, self.pk, manual=False)
            call.assert_not_called()
        recovered = ctxzip.load_summary_state(self.pk)
        self.assertEqual(len(recovered['bolumler']), 1)
        self.assertEqual(recovered['bolumler'][0]['cilt'], 1)
        self.assertEqual(len(recovered['ciltler']), 1)
        self.assertEqual(recovered['ciltler'][0]['dosya'], 'C001.md')
        self.assertIn('User recovered this interrupted Volume', orphan_volume.read_text(encoding='utf-8'))
        self.assertEqual(sorted(path.name for path in (self.pk / 'ciltler').glob('C*.md')), ['C001.md'])

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

    def test_volume_folding_skips_number_gaps_and_uses_contiguous_chapters(self):
        self.pk.mkdir(parents=True)
        chapter_dir = self.pk / 'bolumler'
        chapter_dir.mkdir()
        self.settings['cilt_bolum_sayisi'] = 5
        numbers = [1, 3, 4, 5, 6, 7]
        chapters = []
        for number in numbers:
            filename = f'B{number:04d}.md'
            ctxzip.write_summary_file(
                chapter_dir / filename,
                {'tur': 'bolum', 'no': number, 'kaynak': f'codex/session-{number}',
                 'turlar': 'T1-T1'},
                f'Chapter {number}',
                f'Completed Chapter {number}.',
            )
            chapters.append({
                'no': number, 'dosya': filename, 'oturum': f'codex/session-{number}',
                'tur_baslangic': 1, 'tur_bitis': 1, 'cilt': None,
            })
        state = {'bolumler': chapters, 'ciltler': []}

        created = summarizing.fold_volume(self.settings, self.pk, state, manual=True)

        self.assertEqual(created, 1)
        self.assertEqual(state['ciltler'][0]['bolumler'], [3, 4, 5, 6, 7])
        self.assertIsNone(state['bolumler'][0]['cilt'])
        metadata, _body = ctxzip.read_summary_body(self.pk / 'ciltler' / 'C001.md')
        self.assertEqual(metadata['bolumler'], 'B3-B7')

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

        parsed = parse_claude_session(self.source, True)
        turns_with_thinking, _ = ctxzip.parse_claude_turns(self.source, True)
        self.assertEqual(parsed.turns[0].text(), turns_with_thinking[0].text())
        self.assertEqual(
            [event.kind for event in parsed.events],
            [
                EventKind.METADATA,
                EventKind.USER_MESSAGE,
                EventKind.ASSISTANT_MESSAGE,
                EventKind.TOOL_CALL,
                EventKind.TOOL_RESULT,
            ],
        )
        self.assertNotIn(EventKind.REASONING_SUMMARY, [event.kind for event in parsed.events])
        self.assertTrue(all(event.source.source_hash for event in parsed.events))

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
