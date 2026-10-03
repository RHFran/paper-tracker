"""Offline editorial boundaries: grounded conclusions are not proven hypotheses."""
import copy
import unittest

from literature_digest.models import Paper
from literature_digest.outlook import empty_outlook, prepare_outlook, validate_outlook, checked_outlook
from literature_digest.perspective import validate_perspective
from literature_digest.render import render


class ResearchOutlook(unittest.TestCase):
    def setUp(self):
        self.evidence = 'This synthetic study tested a tool-based workflow on held-out climate tasks.'
        self.papers = [Paper(title='Synthetic study ' + str(i), source='crossref',
                             source_id='10.9999/outlook' + str(i), abstract=self.evidence,
                             url='https://doi.org/10.9999/outlook' + str(i)) for i in (1, 2)]
        self.statement = {'text':'The synthetic studies evaluate tool-based workflows.',
                          'citations':[{'ref':i, 'evidence':self.evidence} for i in (1, 2)]}
        self.data = {'synthesis':{'paragraphs':[{'sentences':[copy.deepcopy(self.statement)]}]},
                     'open_questions':[copy.deepcopy(self.statement)],
                     'ideas':[{'status':'proposed','title':'Compare explicit verification',
                               'basis':[copy.deepcopy(self.statement)],
                               'hypothesis':'Verification could improve complete-task success.',
                               'experiment':'Compare matched-budget agents with and without verification.',
                               'validation':'Evaluate held-out tasks; unchanged success would refute the hypothesis.',
                               'expected_value':'The result could clarify whether verification warrants the added cost.'}]}
        self.perspective = {field:[{'text':text,'evidence':self.evidence,'kind':'inferred'}] for field,text in (
            ('design_logic','Separate planning from executable checks to test workflow quality.'),
            ('limitations','The supplied evidence does not establish reliability in untested climates.'),
            ('inspiration','Compare held-out task performance at a fixed compute budget.'))}
        for paper in self.papers:
            paper.analysis = {'mode':'llm_grounded', 'language':'en',
                              'fields':{field:[{'text':'The source tests a tool-based workflow.', 'evidence':self.evidence}]
                                        for field in ('highlights','question','methods','findings')},
                              'perspective':copy.deepcopy(self.perspective)}

    def test_validated_outlook_renders_before_global_references(self):
        result = prepare_outlook(self.data, self.papers, 'en')
        text, html = render(self.papers, {}, {'language':'en'}, outlook=result)
        self.assertLess(text.index('Closing synthesis and research outlook'), text.index('\nReferences\n'))
        self.assertLess(html.index('Closing synthesis and research outlook'), html.index('>References</h2>'))
        self.assertIn('href="#ref-2"', html)
        self.assertIn('Validation and falsification', text)
        self.assertIn('Research ideas to test', text)

    def test_exactly_six_paper_headings_and_merged_results(self):
        text, html = render(self.papers, {}, {'language':'en'})
        headings = ('Problem and design','Scientific question','Method chain','Results and highlights','Limitations','Research implications')
        for heading in headings:
            self.assertEqual(text.count(heading + ':'), 2)
            self.assertEqual(html.count('>' + heading + '</h4>'), 2)
        self.assertNotIn('Core highlights:', text)
        self.assertNotIn('Main results:', text)
        # Equal highlights/findings claims appear once in the merged section.
        for paper_block in text.split('Results and highlights:')[1:]:
            self.assertEqual(paper_block.split('Limitations:')[0].count('The source tests'), 1)

    def test_source_reference_and_status_validation(self):
        for mutation in ('invented_anchor','unknown_ref','duplicate_ref','missing_basis','asserted_result','empty_experiment','extra_field','uncited_synthesis'):
            data = copy.deepcopy(self.data)
            if mutation == 'invented_anchor': data['ideas'][0]['basis'][0]['citations'][0]['evidence'] = 'This fabricated claim is nowhere in the source.'
            if mutation == 'unknown_ref': data['open_questions'][0]['citations'][0]['ref'] = 99
            if mutation == 'duplicate_ref': data['open_questions'][0]['citations'][1]['ref'] = 1
            if mutation == 'missing_basis': data['ideas'][0]['basis'] = []
            if mutation == 'asserted_result': data['ideas'][0]['status'] = 'established'
            if mutation == 'empty_experiment': data['ideas'][0]['experiment'] = ''
            if mutation == 'extra_field': data['ideas'][0]['guaranteed_gain'] = '25%'
            if mutation == 'uncited_synthesis': data['synthesis']['paragraphs'][0]['sentences'][0]['citations'] = []
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_outlook(data, self.papers, 'en')

    def test_multi_paper_synthesis_cannot_ignore_all_but_one_paper(self):
        self.data['synthesis']['paragraphs'][0]['sentences'][0]['citations'] = self.statement['citations'][:1]
        with self.assertRaisesRegex(ValueError, 'at least two'):
            validate_outlook(self.data, self.papers, 'en')

    def test_bounds_duplicate_titles_and_unstructured_citations(self):
        for mutation in ('too_many_ideas','duplicate_title','embedded_citation','too_many_questions'):
            data = copy.deepcopy(self.data)
            if mutation == 'too_many_ideas': data['ideas'] *= 5
            if mutation == 'duplicate_title': data['ideas'] *= 2
            if mutation == 'embedded_citation': data['ideas'][0]['hypothesis'] += ' [1]'
            if mutation == 'too_many_questions': data['open_questions'] *= 5
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_outlook(data, self.papers, 'en')

    def test_empty_issue_has_no_invented_outlook(self):
        self.assertEqual(validate_outlook(empty_outlook(), [], 'en'), empty_outlook())
        with self.assertRaisesRegex(ValueError,'Empty selections'):
            validate_outlook(self.data, [], 'en')
        text, _ = render([], {}, {'language':'en'}, outlook=prepare_outlook(empty_outlook(), [], 'en'))
        self.assertNotIn('Research ideas to test', text)

    def test_render_rejects_stale_tampered_or_wrong_language_outlook(self):
        for mutation in ('stale','anchor','language','policy'):
            data = prepare_outlook(self.data,self.papers,'en')
            if mutation == 'stale': data['references'].reverse()
            if mutation == 'anchor': data['ideas'][0]['basis'][0]['citations'][0]['evidence'] = 'An invented statement without evidence.'
            if mutation == 'language': data['language'] = 'zh-CN'
            if mutation == 'policy': data['policy'] = 'unverified'
            self.assertIsNone(checked_outlook(data,self.papers,'en'))
            text, _ = render(self.papers,{}, {'language':'en'},outlook=data)
            self.assertNotIn('Closing synthesis and research outlook',text)

    def test_html_escapes_proposal_markup(self):
        self.data['ideas'][0]['title'] = '<script>invented()</script> research test'
        _,html=render(self.papers,{}, {'language':'en'},outlook=prepare_outlook(self.data,self.papers,'en'))
        self.assertNotIn('<script>',html)
        self.assertIn('&lt;script&gt;',html)

    def test_perspective_requires_specific_source_anchors_and_origin(self):
        for mutation in ('missing','empty','fabricated','unsupported_kind'):
            data=copy.deepcopy(self.perspective)
            if mutation == 'missing': data.pop('limitations')
            if mutation == 'empty': data['inspiration']=[]
            if mutation == 'fabricated': data['limitations'][0]['evidence']='No original source contains this sentence.'
            if mutation == 'unsupported_kind': data['design_logic'][0]['kind']='proven'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                validate_perspective(data,self.evidence,'en')

    def test_synthetic_perspective_requires_explicit_demo_mode(self):
        for paper in self.papers: paper.analysis['mode']='synthetic_demo'
        text,_=render(self.papers,{}, {'language':'en'})
        self.assertNotIn('Problem and design:',text)
        text,_=render(self.papers,{'demo':True}, {'language':'en'})
        self.assertIn('Problem and design:',text)

    def test_legacy_papers_keep_readable_four_section_rendering(self):
        for paper in self.papers:paper.analysis.pop('perspective')
        text,_=render(self.papers,{}, {'language':'en'})
        self.assertIn('Core highlights:',text)
        self.assertNotIn('Problem and design:',text)

    def test_chinese_headings_and_closing(self):
        def translate(value):
            if isinstance(value,dict):
                return {key: ('中文研究：'+item if key in {'text','title','hypothesis','experiment','validation','expected_value'} else translate(item)) for key,item in value.items()}
            if isinstance(value,list):return [translate(item) for item in value]
            return value
        for paper in self.papers:paper.analysis=translate(paper.analysis)
        data=prepare_outlook(translate(self.data),self.papers,'zh-CN')
        text,_=render(self.papers,{}, {'language':'zh-CN'},outlook=data)
        for heading in ('问题与设计','科学问题','方法链','结果与亮点','局限性','有何启发'):
            self.assertEqual(text.count(heading+':'),2)
        self.assertIn('本期总结与研究启发',text)


if __name__ == '__main__':unittest.main()
