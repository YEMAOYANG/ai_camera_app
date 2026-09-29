"""Atomic parent selection contracts, using an isolated in-memory database."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from flask import Flask
from core.errors import ApiError
from content.textbook_catalog import validate_manifest
from tests import test_textbook_learning as fixtures


class OfficialTextbookCatalogTest(unittest.TestCase):
    def test_catalog_matches_official_snapshot_without_merging_series_or_school_systems(self):
        root = Path(__file__).resolve().parents[1] / 'content' / 'textbooks'
        snapshot = json.loads((root / 'sources' / 'smartedu-math-english-20260928.json').read_text())
        official = {b['resourceId']: b for b in snapshot['books']}
        manifests = [validate_manifest(json.loads(p.read_text()))
                     for directory in ('math-english-v1', 'math-english-v2')
                     for p in (root / directory).glob('*.json')]
        self.assertEqual(len(manifests), len(official))
        self.assertEqual({m['source']['resourceId'] for m in manifests}, set(official))
        for manifest in manifests:
            source = official[manifest['source']['resourceId']]
            for field in ('editionId', 'publisher', 'gradeCode', 'subject', 'volume', 'schoolSystem'):
                self.assertEqual(manifest[field], source[field], (manifest['editionId'], field))
            self.assertEqual(manifest['editionLabel'].split(' · ')[0], source['version'])
            self.assertEqual(manifest['source']['url'], source['detailUrl'])
            self.assertEqual(manifest['coverage']['status'], 'index_only')
            self.assertEqual(manifest['rightsReview']['status'], 'pending')
            self.assertEqual(manifest['units'], [])


class TextbookSelectionBatchTest(unittest.TestCase):
    def setUp(self):
        fixtures.TextbookLearningTest.setUp(self)
        self.books = [self.manifest]
        for subject in ('math', 'english'):
            manifest = deepcopy(self.manifest)
            manifest.update(editionId=f'synthetic-{subject}-g1', revisionId='test-1', subject=subject,
                            title=f'Synthetic {subject} test book', units=[],
                            coverage={'status': 'index_only', 'note': 'Synthetic test fixture'},
                            rightsReview={'status': 'pending', 'basis': 'Synthetic test fixture'})
            self.service.import_manifest(manifest)
            self.books.append(manifest)

    def body(self, books=None, revisions=None):
        books = self.books if books is None else books
        revisions = [0] * len(books) if revisions is None else revisions
        return {'schoolYearStartYear': 2026, 'semester': 'upper', 'selections': [
            {'editionId': book['editionId'], 'alignmentRevisionId': book['revisionId'], 'expectedSelectionRevision': revision}
            for book, revision in zip(books, revisions)]}

    def write(self, body=None, token='parent-a', child='child-a'):
        return self.service.parent_select_many(token, child, self.body() if body is None else body)

    def rows(self):
        return self.repo.selections(self.db, self.child, 2026, 'upper')

    def assert_error(self, code, callback):
        with self.assertRaises(ApiError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code)

    def test_three_subjects_commit_together_and_student_sees_only_confirmed_books(self):
        result = self.write()
        self.assertEqual([row['subject'] for row in result['selections']], ['chinese', 'math', 'english'])
        self.assertEqual([row['selectionRevision'] for row in result['selections']], [1, 1, 1])
        self.assertEqual(len(self.rows()), 3)
        self.assertEqual(len(self.service.student_catalog('student-a', {})['books']), 3)
        self.assertEqual(self.service.student_catalog('student-b', {})['books'], [])

    def test_conflict_on_last_subject_rolls_back_first_subjects_and_audit_events(self):
        self.write(self.body([self.books[-1]]))
        self.assert_error('textbook_selection_changed', self.write)
        self.assertEqual([row['subject'] for row in self.rows()], ['english'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) AS n FROM learning_textbook_selection_events').fetchone()['n'], 1)
        self.write(self.body(revisions=[0, 0, 1]))
        self.assertEqual(len(self.rows()), 3)

    def test_partial_update_does_not_replace_other_subjects(self):
        self.write()
        self.write(self.body([self.books[1]], [1]))
        revisions = {row['subject']: row['selection_revision'] for row in self.rows()}
        self.assertEqual(revisions, {'chinese': 1, 'math': 2, 'english': 1})

    def test_duplicate_subject_is_rejected_without_writes(self):
        self.assert_error('textbook_selection_invalid', lambda: self.write(self.body([self.books[0], self.books[0]])))
        self.assertEqual(self.rows(), [])

    def test_viewer_foreign_child_and_stale_term_cannot_write(self):
        self.assert_error('forbidden', lambda: self.write(token='viewer'))
        self.assert_error('child_not_found', lambda: self.write(child='child-b'))
        body = self.body(); body['semester'] = 'lower'
        self.assert_error('textbook_term_changed', lambda: self.write(body))
        self.assertEqual(self.rows(), [])

    def test_empty_oversized_and_boolean_revision_are_rejected(self):
        for selections in ([], self.body()['selections'] * 2):
            body = self.body(); body['selections'] = selections
            self.assert_error('textbook_selection_invalid', lambda: self.write(body))
        body = self.body(); body['selections'][0]['expectedSelectionRevision'] = True
        self.assert_error('textbook_selection_invalid', lambda: self.write(body))
        self.assertEqual(self.rows(), [])

    def test_http_batch_endpoint_preserves_auth_and_json_contract(self):
        from routes.api.v2.student_textbooks import parent_textbooks_bp
        app = Flask(__name__)
        app.register_blueprint(parent_textbooks_bp, url_prefix='/api/children')
        app.extensions['mira_textbook_learning_service'] = self.service
        client = app.test_client()
        path = '/api/children/child-a/textbooks/selections'
        self.assertEqual(client.put(path, json=self.body()).status_code, 401)
        response = client.put(path, json=self.body(), headers={'Authorization': 'Bearer parent-a'})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(len(response.json['selections']), 3)
        response = client.put(path, json=self.body(), headers={'Authorization': 'Bearer parent-a'})
        self.assertEqual((response.status_code, response.json['error']), (409, 'textbook_selection_changed'))

    def test_math_english_catalog_is_real_index_only_data_with_unique_sources(self):
        root = Path(__file__).parents[1] / 'content/textbooks/math-english-v1'
        manifests = [validate_manifest(json.loads(path.read_text())) for path in root.glob('*.json')]
        self.assertTrue(manifests)
        self.assertEqual({m['subject'] for m in manifests}, {'math', 'english'})
        self.assertEqual(len({m['source']['resourceId'] for m in manifests}), len(manifests))
        for m in manifests:
            self.assertEqual(m['coverage']['status'], 'index_only')
            self.assertEqual(m['rightsReview']['status'], 'pending')
            self.assertEqual(m['units'], [])
        for grade in range(1, 7):
            self.assertTrue(any(m['gradeCode'] == f'primary_{grade}' and m['subject'] == 'math' and m['volume'] == 'upper' for m in manifests))
        for grade in range(3, 7):
            self.assertTrue(any(m['gradeCode'] == f'primary_{grade}' and m['subject'] == 'english' and m['volume'] == 'upper' for m in manifests))
