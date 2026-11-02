"""Splitting a review's bulky audio evidence is lossless, content-addressed and fails closed.

The first classes need no database. The last one runs on the real PostgreSQL test
database: the table constraints, PostgreSQL's own rendering of jsonb text, and the
operator tool's backup, apply, verify and restore cycle cannot be shown in memory.
"""
import base64
from copy import deepcopy
import gzip
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from content import textbook_review_evidence as ev
from content.textbook_catalog import canonical, digest
from content.textbook_release import RELEASE_SCHEMA, validate_release
from core.database import Database, IntegrityError, DatabaseError
from core.errors import ApiError
from repositories.textbook_repository import TextbookRepository
from scripts import split_textbook_review_evidence as tool
from services import textbook_directory_access as directory
from services import textbook_runtime_release_cache as runtime
from tests.support import fresh_test_config
from tests.test_textbook_publication import fixture


def recording(seed, size=1500):
    block = hashlib.sha256(seed.encode()).digest()
    return (block * (size // 32 + 1))[:size]


def plan(label):
    return {'schemaVersion': 'test.plan', 'label': label, 'teacher': {'name': 'T' * 40, 'voice': 'v' * 20},
            'notes': ['note-' + 'x' * 100 for _ in range(10)]}


def literal_audit(count=4):
    shared_plan = plan('shared')
    origins, segments = [], []
    for index in range(count):
        audio = base64.b64encode(recording('recording-%d' % index)).decode('ascii')
        source = {'sceneId': 'scene-%d' % index, 'audioBase64': audio, 'ttsReceipt': {'requestId': 'tts-%d' % index},
                  'requestPlan': None, 'short': base64.b64encode(b'small').decode('ascii')}
        origins.append({'kind': 'formal', 'plan': shared_plan, 'source': source,
                        'attempts': [{'role': 'routine', 'plan': shared_plan, 'source': source}]})
        segments.append({'sceneId': 'scene-%d' % index, 'target': source, 'text': '第%d句' % index,
                         'audioSha256': hashlib.sha256(recording('recording-%d' % index)).hexdigest()})
    return {'schemaVersion': 'mira.textbook.audio-audit.v3-asr-origin', 'origins': origins,
            'segments': segments, 'passed': True, 'sha256': 'f' * 64}


def strings(node):
    if isinstance(node, dict):
        for value in node.values():
            yield from strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from strings(value)
    elif isinstance(node, str):
        yield node


def review_with(literal):
    return {'reviewer': 'test', 'basis': 'original', 'alignmentConfirmed': True,
            'release': {'schemaVersion': 'x', 'sha256': 'a' * 64, 'media': [{'path': '/a'}],
                        'classroom': {'id': 'c', 'scenes': [{'id': 's1'}]},
                        'audioAudit': {'passed': True, 'segments': 4, 'sha256': 'f' * 64, 'literalAudit': literal}}}


class SplitAndRestoreTest(unittest.TestCase):
    def setUp(self):
        self.review = review_with(literal_audit())
        self.addCleanup(ev.configure, None)

    def split(self):
        return ev.split_review(self.review)

    def test_restoring_gives_back_exactly_the_original(self):
        split, evidence = self.split()
        restored = ev.restore_review(split, ev.MemoryStore(evidence))
        self.assertEqual(restored, self.review)
        self.assertEqual(digest(restored), digest(self.review))
        self.assertEqual(ev.pg_jsonb_text(restored), ev.pg_jsonb_text(self.review))

    def test_restored_text_equals_the_stored_text_byte_for_byte(self):
        split, evidence = self.split()
        original_text = ev.pg_jsonb_text(self.review)
        restored_text = ev.restore_review_text(ev.pg_jsonb_text(split), ev.MemoryStore(evidence))
        self.assertEqual(restored_text, original_text)

    def test_every_recording_is_kept_once_and_the_record_shrinks(self):
        split, evidence = self.split()
        literal = split['release']['audioAudit']['literalAudit']
        self.assertLess(len(ev.pg_jsonb_text(split)), len(ev.pg_jsonb_text(self.review)) // 3)
        self.assertEqual([text for text in strings(literal) if len(text) >= ev.MIN_BLOB_CHARS], [])
        self.assertEqual(literal[ev.MARKER]['blobs'], 4)
        self.assertEqual(literal[ev.MARKER]['objects'], 1)
        for sha, body in evidence.items():
            self.assertEqual(hashlib.sha256(body).hexdigest(), sha)
        recordings = {hashlib.sha256(recording('recording-%d' % i)).hexdigest() for i in range(4)}
        self.assertTrue(recordings <= set(evidence))
        self.assertEqual(len(evidence), 4 + 1)

    def test_a_short_base64_string_stays_where_it_was(self):
        split, _ = self.split()
        source = split['release']['audioAudit']['literalAudit']['origins'][0]['source']
        self.assertEqual(source['short'], base64.b64encode(b'small').decode('ascii'))

    def test_only_the_literal_audit_changes(self):
        split, _ = self.split()
        for part in ('classroom', 'media', 'sha256', 'schemaVersion'):
            self.assertEqual(split['release'][part], self.review['release'][part])
        self.assertEqual(split['release']['audioAudit']['sha256'], 'f' * 64)
        self.assertEqual({k: v for k, v in split.items() if k != 'release'},
                         {k: v for k, v in self.review.items() if k != 'release'})
        before = self.review['release']['audioAudit']
        self.assertEqual({k: v for k, v in split['release']['audioAudit'].items() if k != 'literalAudit'},
                         {k: v for k, v in before.items() if k != 'literalAudit'})

    def test_splitting_does_not_alter_its_input(self):
        snapshot = deepcopy(self.review)
        self.split()
        self.assertEqual(self.review, snapshot)

    def test_an_ordinary_review_passes_through(self):
        ordinary = {'release': {'audioAudit': {'literalAudit': {'sha256': 'f' * 64, 'segments': []}}}}
        self.assertFalse(ev.is_split(ordinary))
        self.assertIs(ev.restore_review(ordinary), ordinary)
        self.assertIs(ev.restore_split_review(ordinary), ordinary)
        for odd in (None, [], 'text', {'release': 3}, {'release': {'audioAudit': []}}):
            self.assertIs(ev.restore_split_review(odd), odd)

    def test_a_missing_item_fails_closed(self):
        split, evidence = self.split()
        evidence.pop(next(iter(evidence)))
        with self.assertRaises(ev.EvidenceError):
            ev.restore_review(split, ev.MemoryStore(evidence))
        ev.configure(ev.MemoryStore(evidence))
        with self.assertRaises(ApiError) as caught, self.assertLogs(ev.LOGGER, 'WARNING'):
            ev.restore_split_review(split)
        self.assertEqual(caught.exception.code, 'textbook_release_unavailable')

    def test_an_altered_item_fails_closed(self):
        split, evidence = self.split()
        sha = next(iter(evidence))
        evidence[sha] = evidence[sha] + b'!'
        with self.assertRaisesRegex(ev.EvidenceError, 'bytes its key names'):
            ev.restore_review(split, ev.MemoryStore(evidence))

    def test_repointed_references_are_caught_by_the_recorded_digest(self):
        split, evidence = self.split()
        origins = split['release']['audioAudit']['literalAudit']['origins']
        first, second = origins[0]['source']['audioBase64'], origins[1]['source']['audioBase64']
        origins[0]['source']['audioBase64'], origins[1]['source']['audioBase64'] = second, first
        # Counts and keys still agree, so only the digest of the original notices; at run time
        # the audit's own sealed digests (re-checked by validate_release) do.
        self.assertNotEqual(ev.restore_review(split, ev.MemoryStore(evidence)), self.review)
        with self.assertRaisesRegex(ev.EvidenceError, 'differs from the split original'):
            ev.restore_review(split, ev.MemoryStore(evidence), verify_digest=True)

    def test_the_marker_must_match_what_is_referenced(self):
        for change in ({'blobs': 3}, {'objects': 0}, {'scope': 'elsewhere'}, {'schemaVersion': 'other'}, {'originalSha256': 'z'}):
            split, evidence = self.split()
            split['release']['audioAudit']['literalAudit'][ev.MARKER].update(change)
            with self.assertRaises(ev.EvidenceError, msg=str(change)):
                ev.restore_review(split, ev.MemoryStore(evidence))
        split, evidence = self.split()
        split['release']['audioAudit']['literalAudit'][ev.MARKER]['extra'] = 1
        with self.assertRaises(ev.EvidenceError):
            ev.restore_review(split, ev.MemoryStore(evidence))

    def test_a_changed_skeleton_is_caught_by_the_recorded_digest(self):
        split, evidence = self.split()
        split['release']['audioAudit']['literalAudit']['passed'] = False
        with self.assertRaisesRegex(ev.EvidenceError, 'differs from the split original'):
            ev.restore_review(split, ev.MemoryStore(evidence), verify_digest=True)

    def test_malformed_references_are_rejected(self):
        for reference in ({ev.REF_KEY: 'nothex'}, {ev.REF_KEY: 'a' * 64, 'extra': 1}, ev.BLOB_PREFIX + 'short'):
            split, evidence = self.split()
            split['release']['audioAudit']['literalAudit']['origins'][0]['plan'] = reference
            with self.assertRaises(ev.EvidenceError):
                ev.restore_review(split, ev.MemoryStore(evidence))

    def test_shared_evidence_may_not_point_at_other_shared_evidence(self):
        split, evidence = self.split()
        literal = split['release']['audioAudit']['literalAudit']
        sha = literal['origins'][0]['plan'][ev.REF_KEY]
        other = canonical({'again': {ev.REF_KEY: sha}}).encode()
        evidence[hashlib.sha256(other).hexdigest()] = other
        literal['origins'][1]['plan'] = {ev.REF_KEY: hashlib.sha256(other).hexdigest()}
        literal[ev.MARKER]['objects'] = 2
        with self.assertRaisesRegex(ev.EvidenceError, 'other shared evidence'):
            ev.restore_review(split, ev.MemoryStore(evidence))

    def test_reserved_names_in_the_original_are_refused_before_anything_is_split(self):
        for hostile in ({ev.REF_KEY: 1}, ev.BLOB_PREFIX + 'anything'):
            literal = literal_audit()
            literal['origins'][0]['source']['note'] = hostile
            with self.assertRaises(ev.EvidenceError):
                ev.split_review(review_with(literal))

    def test_text_that_is_not_exactly_base64_is_left_alone(self):
        literal = literal_audit()
        raw = base64.b64encode(recording('odd', 3000)).decode('ascii')
        unpadded = base64.b64encode(recording('odd', 3001)).decode('ascii').rstrip('=')
        odd = {'wrapped': raw[:1200] + '\n' + raw[1200:], 'unpadded': unpadded,
               'trailing-bits': 'A' * 1200 + 'QR==', 'plain': 'not base64 at all ' * 100}
        self.assertNotEqual(len(unpadded) % 4, 0)
        literal['origins'][0]['source'].update(odd)
        review = review_with(literal)
        split, evidence = ev.split_review(review)
        self.assertEqual(ev.restore_review(split, ev.MemoryStore(evidence)), review)
        texts = set(strings(split))
        for body in evidence.values():
            try:
                texts |= set(strings(json.loads(body)))
            except ValueError:
                pass            # a recording is not JSON
        for name, value in odd.items():
            self.assertIn(value, texts, msg=name)

    def test_splitting_twice_or_without_an_audit_is_refused(self):
        split, _ = self.split()
        with self.assertRaisesRegex(ev.EvidenceError, 'already split'):
            ev.split_review(split)
        with self.assertRaises(ev.EvidenceError):
            ev.split_review({'release': {'audioAudit': {}}})

    def test_restore_gives_each_place_its_own_copy(self):
        split, evidence = self.split()
        restored = ev.restore_review(split, ev.MemoryStore(evidence))
        audit = restored['release']['audioAudit']['literalAudit']
        self.assertEqual(audit['origins'][0]['plan'], audit['origins'][1]['plan'])
        self.assertIsNot(audit['origins'][0]['plan'], audit['origins'][1]['plan'])

    def test_the_default_store_fails_closed_when_nothing_is_configured(self):
        split, _ = self.split()
        with patch('core.config.AppConfig.from_env', side_effect=RuntimeError('no environment')):
            ev.configure(None)
            with self.assertRaisesRegex(ev.EvidenceError, 'no evidence store is configured'):
                ev.restore_review(split)

    def test_postgresql_text_orders_keys_by_length_then_bytes(self):
        self.assertEqual(ev.pg_jsonb_text({'bb': 1, 'a': 2, 'ab': 3, '中': 4, 'c': [True, None, {'z': 1, 'yy': 2}]}),
                         '{"a": 2, "c": [true, null, {"z": 1, "yy": 2}], "ab": 3, "bb": 1, "中": 4}')


class ValidateReleaseHookTest(unittest.TestCase):
    """validate_release restores a split review before any digest is checked."""

    def setUp(self):
        self.addCleanup(ev.configure, None)
        self.manifest, build, release = fixture()
        review = json.loads(build['review_json'])
        release.pop('sha256')
        release['audioAudit']['literalAudit'] = literal_audit()
        release['sha256'] = digest(release)
        review['release'] = release
        self.build = {**build, 'review_json': canonical(review)}
        self.release = release
        split, self.evidence = ev.split_review(review)
        self.split_build = {**build, 'review_json': canonical(split)}

    def test_a_split_review_validates_exactly_like_the_original(self):
        self.assertEqual(validate_release(self.build, self.manifest), self.release)
        ev.configure(ev.MemoryStore(self.evidence))
        self.assertEqual(validate_release(self.split_build, self.manifest), self.release)

    def test_without_its_evidence_the_lesson_is_rejected(self):
        ev.configure(ev.MemoryStore({}))
        with self.assertRaises(ApiError), self.assertLogs(ev.LOGGER, 'WARNING'):
            validate_release(self.split_build, self.manifest)

    def test_an_ordinary_review_never_reads_the_store(self):
        class Exploding:
            def read(self, hashes):
                raise AssertionError('the evidence store must not be read for an ordinary review')
        ev.configure(Exploding())
        self.assertEqual(validate_release(self.build, self.manifest), self.release)

    def test_a_tampered_skeleton_is_still_rejected_by_the_existing_seals(self):
        review = json.loads(self.split_build['review_json'])
        review['release']['audioAudit']['passed'] = False
        ev.configure(ev.MemoryStore(self.evidence))
        with self.assertRaises(ApiError):
            validate_release({**self.split_build, 'review_json': canonical(review)}, self.manifest)

    def test_the_directory_cache_hit_returns_what_full_validation_returned(self):
        entry = {'releaseSha256': self.release['sha256'], 'releaseSchemaVersion': RELEASE_SCHEMA}
        ev.configure(ev.MemoryStore(self.evidence))
        self.assertEqual(directory._release_from_entry(TextbookRepository, self.split_build, entry), self.release)
        ev.configure(ev.MemoryStore({}))
        with self.assertLogs(ev.LOGGER, 'WARNING'):
            self.assertIsNone(directory._release_from_entry(TextbookRepository, self.split_build, entry))


class NoPreviewConnection:
    """Answers every query with no row: the bound preview is simply missing."""

    def execute(self, sql, params=()):
        return self

    def fetchone(self):
        return None


class ExporterPacksTheWholeReviewTest(unittest.TestCase):
    """A course package carries the review exactly as stored before the split."""

    def setUp(self):
        self.addCleanup(ev.configure, None)

    def snapshot(self, review_text, evidence):
        from services import course_archive_exporter as exporter_module
        manifest, build, release = fixture()
        course = {'id': 'course', 'version': '1', 'title': '天地人'}
        row = {**build, 'review_json': review_text}
        ev.configure(ev.MemoryStore(evidence))
        with TemporaryDirectory(dir=os.getenv('MIRA_TASK_TMPDIR') or os.getenv('TMPDIR')) as root:
            exporter = exporter_module.CourseArchiveExporter(project_root=root, media_store=object())
            with patch.object(exporter_module.releases, '_validated_release', return_value=(row, course, release, manifest)), \
                    patch.object(exporter_module.releases, 'release_metadata', return_value={}), \
                    patch.object(exporter_module.releases, 'delivery_media', return_value=[]):
                return exporter._textbook_snapshot(NoPreviewConnection(), build['content_key'])

    def test_a_split_review_is_restored_before_it_is_packed(self):
        review = review_with(literal_audit())
        original_text = ev.pg_jsonb_text(review)
        split, evidence = ev.split_review(review)
        snapshot = self.snapshot(ev.pg_jsonb_text(split), evidence)
        self.assertEqual(snapshot.documents['审核与发布记录.json'], original_text)
        self.assertEqual(snapshot.documents['数据库/教材构建记录.json']['review_json'], original_text)

    def test_an_ordinary_review_is_packed_unchanged(self):
        text = ev.pg_jsonb_text(review_with(literal_audit()))
        snapshot = self.snapshot(text, {})
        self.assertEqual(snapshot.documents['审核与发布记录.json'], text)


class TextbookReviewEvidenceDatabaseTest(unittest.TestCase):
    """The table, PostgreSQL's own text rendering, and the operator tool end to end."""

    @classmethod
    def setUpClass(cls):
        cls.config = fresh_test_config()
        cls.db = Database(cls.config['DATABASE_URL'])

    def setUp(self):
        self.addCleanup(ev.configure, None)
        self.addCleanup(runtime._clear_for_tests)
        self.addCleanup(directory._clear_validation_cache_for_tests)
        self.manifest, build, release = fixture()
        review = json.loads(build['review_json'])
        release.pop('sha256')
        release['audioAudit']['literalAudit'] = literal_audit(6)
        release['sha256'] = digest(release)
        review['release'] = release
        self.key = build['content_key']
        with self.db.transaction() as conn:
            for table in ('learning_textbook_review_evidence', 'learning_textbook_course_builds', 'learning_courses',
                          'learning_textbook_revisions', 'learning_textbook_editions'):
                conn.execute(f'DELETE FROM {table}')
            conn.execute("INSERT INTO learning_textbook_editions (edition_id,identity_sha256,identity_json,imported_at) "
                         "VALUES ('book',?,'{}',1)", ('e' * 64,))
            conn.execute("INSERT INTO learning_textbook_revisions (edition_id,revision_id,grade_code,subject,"
                         "manifest_sha256,manifest_json,imported_at) VALUES ('book','directory','primary_1','chinese',?,?,1)",
                         (digest(self.manifest), canonical(self.manifest)))
            conn.execute("INSERT INTO learning_courses (id,version,grade_code,subject,node_code,title,objective,status,"
                         "quality_status,content_origin,content_json,created_at,updated_at) VALUES "
                         "('course','1','primary_1','chinese','n1','Title','Objective','published','released',"
                         "'openmaic_generated',?,1,1)", (canonical({'title': '天地人'}),))
            conn.execute("INSERT INTO learning_textbook_course_builds (content_key,edition_id,revision_id,node_id,part_index,"
                         "teaching_revision,input_json,status,course_id,course_version,course_content_sha256,review_json,"
                         "created_at,updated_at) VALUES (?,'book','directory','u1-l1',1,'1',?,'published','course','1',?,?,1000,2000)",
                         (self.key, build['input_json'], build['course_content_sha256'], canonical(review)))
        with self.db.transaction() as conn:
            self.original_text = conn.execute('SELECT CAST(review_json AS TEXT) AS t FROM learning_textbook_course_builds '
                                              'WHERE content_key=?', (self.key,)).fetchone()['t']

    def stored(self):
        with self.db.transaction() as conn:
            return conn.execute('SELECT CAST(review_json AS TEXT) AS t, updated_at, created_at '
                                'FROM learning_textbook_course_builds WHERE content_key=?', (self.key,)).fetchone()

    def evidence_rows(self):
        with self.db.transaction() as conn:
            return conn.execute('SELECT count(*) AS n FROM learning_textbook_review_evidence').fetchone()['n']

    def test_the_table_only_accepts_bytes_under_their_own_hash(self):
        body = recording('table')
        sha = hashlib.sha256(body).hexdigest()
        with self.db.transaction() as conn:
            conn.execute('INSERT INTO learning_textbook_review_evidence (sha256,body,byte_length,created_at) VALUES (?,?,?,1)',
                         (sha, body, len(body)))
            conn.execute('INSERT INTO learning_textbook_review_evidence (sha256,body,byte_length,created_at) VALUES (?,?,?,2) '
                         'ON CONFLICT (sha256) DO NOTHING', (sha, body, len(body)))
        for key, size in (('0' * 64, len(body)), (sha[:-1] + ('0' if sha[-1] != '0' else '1'), len(body)), (sha, len(body) + 1)):
            with self.assertRaises(IntegrityError):
                with self.db.transaction() as conn:
                    conn.execute('INSERT INTO learning_textbook_review_evidence (sha256,body,byte_length,created_at) '
                                 'VALUES (?,?,?,1)', (key, body, size))
        with self.assertRaises(DatabaseError):
            with self.db.transaction() as conn:
                conn.execute("UPDATE learning_textbook_review_evidence SET body=? WHERE sha256=?", (b'other', sha))
        self.assertEqual(self.evidence_rows(), 1)

    def test_evidence_survives_a_round_trip_through_the_database(self):
        review = review_with(literal_audit())
        split, evidence = ev.split_review(review)
        with self.db.transaction() as conn:
            ev.store_evidence(conn, evidence, now=5)
            ev.store_evidence(conn, evidence, now=6)
        self.assertEqual(self.evidence_rows(), len(evidence))
        self.assertEqual(ev.restore_review(split, ev.DatabaseStore(self.db)), review)
        with self.db.transaction() as conn:
            self.assertEqual(ev.restore_review(split, ev.ConnectionStore(conn)), review)

    def test_python_text_rendering_matches_postgresql(self):
        values = [{'bb': 1, 'a': 2, 'ab': 3, '中': 4, '文字': [1, 2.5, -3, True, False, None, '引号"反斜杠\\斜杠/']},
                  {'k': 'tab\tnewline\nbell\x07 \x7f é 😀'}, [], {}, [[], [{}]], {'n': {'m': {'l': [0, 10 ** 12]}}},
                  # Alphabetical order (aaa, b, zz) differs from PostgreSQL's length-first order (b, zz, aaa).
                  {'aaa': 1, 'zz': {'yyy': 1, 'x': 2}, 'b': 3}]
        for value in values:
            with self.db.transaction() as conn:
                text = conn.execute('SELECT CAST(CAST(? AS jsonb) AS TEXT) AS t', (json.dumps(value),)).fetchone()['t']
            parsed = json.loads(text)
            self.assertEqual(ev.pg_jsonb_text(parsed), text, msg=text)
            # Keys arrive in another order (alphabetical); PostgreSQL's order must still come out.
            alphabetical = json.loads(json.dumps(parsed, sort_keys=True))
            self.assertEqual(ev.pg_jsonb_text(alphabetical), text, msg=text)

    def test_backup_apply_verify_and_restore(self):
        with TemporaryDirectory(dir=os.getenv('MIRA_TASK_TMPDIR') or os.getenv('TMPDIR')) as temporary:
            backup = Path(temporary) / 'backup'
            manifest = tool.backup_records(self.db, [self.key], backup)
            entry = {**tool.manifest_entry(manifest, self.key), 'database': manifest['database']}
            self.assertEqual(entry['originalReviewSha256'], hashlib.sha256(self.original_text.encode()).hexdigest())
            self.assertEqual(gzip.decompress((backup / entry['file']).read_bytes()).decode(), self.original_text)
            self.assertEqual(oct(backup.stat().st_mode & 0o777), '0o700')
            self.assertEqual(oct((backup / entry['file']).stat().st_mode & 0o777), '0o600')
            with self.assertRaises(FileExistsError):
                tool.backup_records(self.db, [self.key], backup)

            dry = tool.apply_record(self.db, entry, execute=False, now_ms=7)
            self.assertTrue(dry['dryRun'] and dry['restoresByteForByte'])
            self.assertEqual(self.stored()['t'], self.original_text)
            self.assertEqual(self.evidence_rows(), 0)

            report = tool.apply_record(self.db, entry, execute=True, now_ms=7)
            self.assertTrue(report['committed'])
            after = self.stored()
            self.assertLess(len(after['t']), len(self.original_text) // 2)
            self.assertEqual((after['updated_at'], after['created_at']), (2000, 1000))
            self.assertGreater(self.evidence_rows(), 0)
            self.assertTrue(ev.is_split(json.loads(after['t'])))

            ev.configure(self.db)
            with self.db.transaction() as conn:
                self.assertEqual(ev.restore_review_text(after['t'], ev.ConnectionStore(conn)), self.original_text)
            verified = tool.verify_records(self.db, [self.key], manifest_dir=backup, queue_dir=Path(temporary) / 'none')
            result = verified['releases'][0]
            self.assertTrue(result['split'] and result['restoresToOriginal'] and result['otherColumnsUnchanged'])
            self.assertTrue(result['runtimeReleaseOk'] and result['belowLimit'])
            # The trigger recomputed the directory row from the split record: it must equal the old one.
            self.assertIsNotNone(entry['directory'])
            self.assertTrue(result['directoryRowUnchanged'])
            self.assertIsNone(verified['archiveQueue'])

            restored = tool.restore_record(self.db, backup, manifest, self.key, execute=True)
            self.assertTrue(restored['committed'])
            self.assertEqual(self.stored()['t'], self.original_text)
            self.assertTrue(tool.restore_record(self.db, backup, manifest, self.key, execute=True)['alreadyOriginal'])
            self.assertEqual(self.stored()['updated_at'], 2000)

    def test_apply_refuses_when_the_row_changed_after_the_backup(self):
        with TemporaryDirectory(dir=os.getenv('MIRA_TASK_TMPDIR') or os.getenv('TMPDIR')) as temporary:
            manifest = tool.backup_records(self.db, [self.key], Path(temporary) / 'backup')
            entry = {**tool.manifest_entry(manifest, self.key), 'database': manifest['database']}
            with self.db.transaction() as conn:
                conn.execute('UPDATE learning_textbook_course_builds SET updated_at=updated_at+1 WHERE content_key=?', (self.key,))
            with self.assertRaisesRegex(tool.ToolError, 'changed since the backup'):
                tool.apply_record(self.db, entry, execute=True, now_ms=7)
            self.assertEqual(self.stored()['t'], self.original_text)

    def test_apply_rolls_back_when_validation_fails_and_leaves_the_original(self):
        with TemporaryDirectory(dir=os.getenv('MIRA_TASK_TMPDIR') or os.getenv('TMPDIR')) as temporary:
            manifest = tool.backup_records(self.db, [self.key], Path(temporary) / 'backup')
            entry = {**tool.manifest_entry(manifest, self.key), 'database': manifest['database']}
            with patch.object(tool, '_validate_in', side_effect=tool.ToolError('validation failed')):
                with self.assertRaisesRegex(tool.ToolError, 'validation failed'):
                    tool.apply_record(self.db, entry, execute=True, now_ms=7)
            self.assertEqual(self.stored()['t'], self.original_text)

    def test_apply_rolls_back_when_a_column_other_than_the_review_would_move(self):
        with TemporaryDirectory(dir=os.getenv('MIRA_TASK_TMPDIR') or os.getenv('TMPDIR')) as temporary:
            manifest = tool.backup_records(self.db, [self.key], Path(temporary) / 'backup')
            entry = {**tool.manifest_entry(manifest, self.key), 'database': manifest['database']}
            with self.db.transaction() as conn:
                conn.execute("CREATE FUNCTION touch_updated_at() RETURNS trigger LANGUAGE plpgsql AS "
                             "$$ BEGIN NEW.updated_at := NEW.updated_at + 1; RETURN NEW; END $$")
                conn.execute("CREATE TRIGGER touch_updated_at BEFORE UPDATE OF review_json ON learning_textbook_course_builds "
                             "FOR EACH ROW EXECUTE FUNCTION touch_updated_at()")
            try:
                with self.assertRaisesRegex(tool.ToolError, 'a column other than review_json moved'):
                    tool.apply_record(self.db, entry, execute=True, now_ms=7)
            finally:
                with self.db.transaction() as conn:
                    conn.execute('DROP TRIGGER touch_updated_at ON learning_textbook_course_builds')
                    conn.execute('DROP FUNCTION touch_updated_at()')
            stored = self.stored()
            self.assertEqual((stored['t'], stored['updated_at']), (self.original_text, 2000))

    def test_apply_needs_the_backed_up_original(self):
        with TemporaryDirectory(dir=os.getenv('MIRA_TASK_TMPDIR') or os.getenv('TMPDIR')) as temporary:
            manifest = tool.backup_records(self.db, [self.key], Path(temporary) / 'backup')
            entry = {**tool.manifest_entry(manifest, self.key), 'database': manifest['database'],
                     'originalReviewSha256': '0' * 64}
            with self.assertRaisesRegex(tool.ToolError, 'not the backed-up original'):
                tool.apply_record(self.db, entry, execute=True, now_ms=7)
            self.assertEqual(self.stored()['t'], self.original_text)

    def test_a_missing_evidence_row_makes_the_lesson_unavailable(self):
        with TemporaryDirectory(dir=os.getenv('MIRA_TASK_TMPDIR') or os.getenv('TMPDIR')) as temporary:
            manifest = tool.backup_records(self.db, [self.key], Path(temporary) / 'backup')
            entry = {**tool.manifest_entry(manifest, self.key), 'database': manifest['database']}
            tool.apply_record(self.db, entry, execute=True, now_ms=7)
        with self.db.transaction() as conn:
            conn.execute('DELETE FROM learning_textbook_review_evidence WHERE sha256=('
                         'SELECT min(sha256) FROM learning_textbook_review_evidence)')
        ev.configure(self.db)
        with self.db.transaction() as conn:
            row = conn.execute('SELECT * FROM learning_textbook_course_builds WHERE content_key=?', (self.key,)).fetchone()
        with self.assertRaises(ApiError), self.assertLogs(ev.LOGGER, 'WARNING'):
            validate_release(row, self.manifest, {'id': 'course', 'version': '1', 'status': 'published',
                                                  'quality_status': 'released', 'content_json': canonical({'title': '天地人'})})


if __name__ == '__main__':
    unittest.main()
