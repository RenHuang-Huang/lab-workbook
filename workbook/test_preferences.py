"""Portable preference checks use temporary synthetic settings only."""
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from workbook import app,core

class PreferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        folder=Path(self.temp.name)
        self.local=folder/'portable/preferences.json';self.legacy=folder/'legacy/preferences.json'
        self.enterContext(patch.object(app,'PREFERENCES',self.local))

    def test_missing_file_creates_defaults_without_reading_other_settings(self):
        core.save_json(self.legacy,{'database_path':'old.mdb','order_mode':'merge'})
        original=self.legacy.read_bytes()
        expected=app.default_preferences()
        with patch.object(app,'load_json',side_effect=AssertionError('Must not read another settings file')):
            self.assertEqual(app.load_preferences(),expected)
        self.assertEqual(core.load_json(self.local),expected)
        self.assertEqual(self.legacy.read_bytes(),original)
        self.assertEqual(expected['database_path'],'')
        self.assertEqual((expected['order_mode'],expected['merge_workno_style']),('merge','first'))

    def test_existing_preferences_survive_restart(self):
        expected=dict(app.default_preferences(),database_path='synthetic.mdb',order_mode='split',merge_workno_style='all')
        core.save_json(self.local,expected)
        self.assertEqual(app.load_preferences(),expected)

    def test_existing_empty_local_file_takes_priority(self):
        core.save_json(self.local,{})
        core.save_json(self.legacy,{'database_path':'old.mdb'})
        self.assertEqual(app.load_preferences(),app.default_preferences())

    def test_invalid_local_file_is_not_replaced_by_old_settings(self):
        self.local.parent.mkdir();self.local.write_text('invalid',encoding='utf-8')
        core.save_json(self.legacy,{'database_path':'old.mdb'})
        with self.assertRaises(ValueError):app.load_preferences()
        self.assertEqual(self.local.read_text(encoding='utf-8'),'invalid')

if __name__=='__main__':unittest.main()
