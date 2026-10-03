"""Offline subject customization and frozen-config compatibility tests."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from literature_digest.config import DEFAULTS, digest_subject, load_configs, validate_config
from literature_digest.pipeline import config_fingerprint


class SubjectTemplate(unittest.TestCase):
    def test_empty_and_missing_preserve_old_fingerprint(self):
        old = copy.deepcopy(DEFAULTS)
        old.pop('subject_template')
        current = {**old, 'subject_template': ''}
        self.assertEqual(config_fingerprint(old), config_fingerprint(current))
        current['subject_template'] = 'Daily | {date}'
        self.assertNotEqual(config_fingerprint(old), config_fingerprint(current))

    def test_default_subjects_and_literal_custom_date(self):
        self.assertEqual(digest_subject({'language': 'zh-CN'}, '2026-10-03', 2), '科研文献精选 | 2026-10-03 | 2')
        self.assertEqual(digest_subject({'language': 'en'}, '2026-10-03', 2), 'Literature digest | 2026-10-03 | 2')
        self.assertEqual(digest_subject({'subject_template': '【论文日报】研究方向 | {date}'}, '2026-10-03', 2), '【论文日报】研究方向 | 2026-10-03')
        for day in ('20261003', '2026-10-03\r\nBcc: x', '2026-02-30', None):
            with self.subTest(day=day), self.assertRaises(ValueError):
                digest_subject({}, day, 2)

    def test_invalid_templates_rejected(self):
        for template in (None, 42, 'Daily', '{date}{date}', '{date:%Y}', '{date!r}', '{date.__class__}', '{date[0]}', '{{date}}', '{other}', '{date}\r\nBcc: x@example.org', '{date}\x7f', ' {date}', '{date} ', 'x' * 201 + '{date}'):
            config = copy.deepcopy(DEFAULTS)
            config['subject_template'] = template
            with self.subTest(template=template), self.assertRaises(ValueError):
                validate_config(config)

    def test_profiles_can_override_template(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'config.json'
            path.write_text(json.dumps({'subject_template': 'Base | {date}', 'profiles': [
                {'id': 'base'}, {'id': 'custom', 'subject_template': 'Custom | {date}'},
                {'id': 'legacy', 'subject_template': ''}]}), encoding='utf-8')
            configs = load_configs(str(path))
            self.assertEqual([c['subject_template'] for c in configs], ['Base | {date}', 'Custom | {date}', ''])


if __name__ == '__main__':
    unittest.main()
