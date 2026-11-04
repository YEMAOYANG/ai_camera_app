import unittest

from courseware.tools.check import check_classroom


class FactCheckEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.notes = {'resources': {
            name: {'findings': ['reviewed'], 'pageRefs': [1, 2]}
            for name in ('teachingDesign', 'courseware', 'learningTaskSheet', 'afterClassExercise')},
            'factChecks': [{'claims': ['可的笔顺是横、竖、横折、横、竖钩。'], 'sources': [
                {'resource': 'teachingDesign', 'pageRefs': [1], 'finding': '教师示范规范书写。'},
                {'resource': 'courseware', 'pageRefs': [26, 27], 'finding': '分步画面显示完整笔顺。'}]}]}

    def issues(self):
        return [issue for issue in check_classroom({'scenes': []}, notes=self.notes)
                if issue['code'] == 'fact_check_incomplete']

    def test_two_cited_official_resources_are_accepted(self):
        self.assertEqual(self.issues(), [])

    def test_a_fact_needs_two_existing_cited_resources(self):
        self.notes['factChecks'][0]['sources'].pop()
        self.assertEqual([(issue['gate'], issue['severity']) for issue in self.issues()], [('G0', 'error')])
        self.notes['factChecks'][0]['sources'].append(
            {'resource': 'memory', 'pageRefs': [1], 'finding': 'not an official resource'})
        self.assertEqual([(issue['gate'], issue['severity']) for issue in self.issues()], [('G0', 'error')])


if __name__ == '__main__':
    unittest.main()
