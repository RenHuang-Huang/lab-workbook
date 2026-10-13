import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from . import core,layout_settings as ls,catalog_cache as cc,settings_history as history,catalog_settings as cs
from .test_catalog_cache import fixture


class SettingsHistoryTests(unittest.TestCase):
    def setUp(self):
        self.settings=core.default_settings();self.layout=ls.defaults();self.catalog=fixture()

    def test_noop_and_old_settings_do_not_invent_dates(self):
        self.settings.pop('updated_at');self.layout.pop('updated_at');self.layout.pop('item_updated_at')
        settings,layout=history.stamp_items(self.settings,self.layout,self.settings,self.layout,self.catalog)
        self.assertIsNone(settings['updated_at']);self.assertIsNone(layout['updated_at']);self.assertEqual(layout['item_updated_at'],{})
        doc=cc.build(self.catalog,settings,layout)
        self.assertIsNone(doc['settings_updated_at'])
        self.assertTrue(all(r['updated_display']=='尚無紀錄' for r in doc['records']))

    def test_only_changed_item_dated_other_item_retains_date(self):
        self.layout['item_updated_at']={'344':'2025-01-01T10:00:00+08:00'}
        candidate=copy.deepcopy(self.settings);candidate['rules']['0921']['group']='e411'
        with patch.object(history,'now',return_value='2026-10-14T14:00:00+08:00'):
            settings,layout=history.stamp_items(self.settings,self.layout,candidate,self.layout,self.catalog)
        self.assertEqual(layout['item_updated_at'],{'344':'2025-01-01T10:00:00+08:00','0921':'2026-10-14T14:00:00+08:00'})
        self.assertEqual(settings['updated_at'],layout['updated_at'])
        self.assertEqual(history.stamp_items(settings,layout,settings,layout,self.catalog),(settings,layout))

    def test_label_region_position_and_color_changes_are_dated(self):
        for field,value in [('label','Renamed'),('zone','其他'),('position',2),('code_color','#215CAE')]:
            with self.subTest(field=field):
                row=cs.records(self.catalog,self.settings,self.layout)[0]
                args=dict(label=row['label'],zone=row['zone'],group=row['machine_group'],print_enabled=True)
                args[field]=value
                candidate,layout=cs.edit_item(self.settings,self.layout,row,**args)
                _,saved=history.stamp_items(self.settings,self.layout,candidate,layout,self.catalog)
                self.assertTrue(history.display(saved['item_updated_at']['0921']))

    def test_json_import_preserves_item_origin_dates(self):
        candidate=copy.deepcopy(self.settings);candidate['rules']['0921']['group']='e411'
        layout=copy.deepcopy(self.layout);layout['item_updated_at']={'0921':'2025-03-02T10:00:00+08:00'}
        settings,saved=history.stamp_items(self.settings,self.layout,candidate,layout,self.catalog,preserve_dates=True)
        doc=cc.build(self.catalog,settings,saved)
        _,imported=cc.import_settings(doc,self.settings,self.catalog)
        self.assertEqual(imported['item_updated_at']['0921'],layout['item_updated_at']['0921'])
        self.assertEqual(doc['records'][0]['updated_at'],layout['item_updated_at']['0921'])

    def test_failed_transaction_does_not_mutate_dates_or_files(self):
        with tempfile.TemporaryDirectory() as temp:
            paths=[Path(temp)/name for name in ('settings.json','layout.json','catalog.json')]
            active=cc.build(self.catalog,self.settings,self.layout)
            for path,value in zip(paths,(self.settings,self.layout,active)):cc.write(value,path)
            candidate=copy.deepcopy(self.settings);candidate['rules']['0921']['group']='e411';layout=copy.deepcopy(self.layout)
            before=copy.deepcopy((candidate,layout));blobs=[p.read_bytes() for p in paths];calls=0;replace=cc.os.replace
            def fail(source,target):
                nonlocal calls
                calls+=1
                if calls==2:raise OSError('synthetic')
                return replace(source,target)
            with patch.object(cc.os,'replace',side_effect=fail):
                with self.assertRaises(OSError):cc.apply_settings(active,candidate,layout,*paths)
            self.assertEqual((candidate,layout),before);self.assertEqual([p.read_bytes() for p in paths],blobs)

    def test_system_changes_and_cache_rebuild_do_not_change_print_dates(self):
        with tempfile.TemporaryDirectory() as temp:
            paths=[Path(temp)/name for name in ('settings.json','layout.json','catalog.json')]
            active=cc.build(self.catalog,self.settings,self.layout)
            for path,value in zip(paths,(self.settings,self.layout,active)):cc.write(value,path)
            candidate=dict(self.settings,database_path='elsewhere',output_directory='destination')
            doc=cc.apply_settings(active,candidate,copy.deepcopy(self.layout),*paths)
            self.assertIsNone(doc['settings_updated_at']);self.assertEqual(doc['settings']['print_layout']['item_updated_at'],{})
            self.assertEqual(candidate['database_path'],'elsewhere')

    def test_general_print_save_records_only_real_change(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'settings.json';candidate=copy.deepcopy(self.settings)
            core.save_print_settings(candidate,path);self.assertIsNone(candidate['updated_at'])
            candidate['fixed_20_rows']=False
            core.save_print_settings(candidate,path);stamp=candidate['updated_at'];self.assertTrue(history.display(stamp))
            with patch.object(history,'now',return_value='2099-01-01T00:00:00+08:00'):
                core.save_print_settings(candidate,path)
            self.assertEqual(candidate['updated_at'],stamp)

    def test_malformed_dates_rejected_and_latest_compares_timezones(self):
        for value in ({'updated_at':'not a date'},{'item_updated_at':[]},{'item_updated_at':{'101':4}}):
            with self.assertRaises(ValueError):history.validate(value)
        self.assertEqual(history.latest('2026-10-14T12:00:00+08:00','2026-10-14T08:00:00+00:00'),'2026-10-14T08:00:00+00:00')


if __name__=='__main__':unittest.main()
