"""Upgrade continuity tests: artificial settings/dictionaries only, no Access."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from workbook import core, config_store as cs, catalog_cache as cc, layout_settings as ls
from scripts.build_desktop import synthetic_demo


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.old=self.root/'old';self.new=self.root/'new'
        self.settings=core.default_settings()
        self.settings.update(fixed_20_rows=False,ditto_bio=False,ditto_patient=False,
                             show_column_headers=True,merged_color='#246B45',ditto_bold=True,
                             ditto_font_size=19,export_glucose_ac=False,mapping_confirmed=True)
        self.settings['font_sizes']['name']=21
        self.settings.update(merged_order_colors=['#202830','#246B45','#123456','#654321'],
                             merge_exclusions_enabled=False,merge_excluded_worknos=['9','10','66'])
        self.settings['rules']['0921']={'group':'e411','label':'自訂AC'}
        self.layout=ls.defaults()
        self.layout.update(bio_adult_slot=True,source_panels_migrated=True,version=3,
            clinic_aliases={'DEMO':'保留簡稱'},code_colors={'0921':'#ABCDEF'},
            placements={'0921':dict(print_enabled=False,subregion='',position=None)})
        self.system=cs.system_defaults(self.old)
        self.system.update(database_path='synthetic.mdb',output_directory='synthetic-output',order_mode='split',merge_workno_style='all')
        self.catalog=cc.build(synthetic_demo(),self.settings,self.layout)
        self.write_old()

    def write_old(self):
        for name,value in [('settings.json',dict(self.settings,**self.system)),('layout_settings.json',self.layout),('catalog.json',self.catalog)]:
            core.save_json(self.old/'workbook'/name,value)
        core.save_json(self.old/'preferences.json',self.system)

    def seed(self,root=None):
        root=root or self.new
        for name,value in [('settings.json',self.settings),('layout_settings.json',self.layout),('catalog.json',self.catalog)]:
            core.save_json(root/'defaults/print_settings'/name,value)
        core.save_json(root/'defaults/system_seed.json',self.system)

    def snapshot(self,root):
        return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*.json') if 'config_backups' not in p.parts}

    def test_legacy_same_folder_migrates_all_and_keeps_original_bytes(self):
        before=self.snapshot(self.old);cs.ensure_configuration(self.old)
        for path,data in before.items():self.assertEqual((self.old/path).read_bytes(),data)
        current=cs.read_bundle(self.old)
        self.assertEqual(current['settings'],self.settings)
        self.assertEqual(current['system'],self.system)
        for key in ('clinic_aliases','code_colors','placements'):
            for code,value in self.layout[key].items():self.assertEqual(current['layout'][key][code],value)
        self.assertEqual(current['catalog']['raw_catalog'],self.catalog['raw_catalog'])
        self.assertTrue(list((self.old/'config_backups').rglob('settings.json')))

    def test_fresh_folder_initializes_carried_system_and_print_seed(self):
        self.seed();cs.ensure_configuration(self.new)
        value=cs.read_bundle(self.new)
        self.assertEqual(value['settings'],self.settings);self.assertEqual(value['system'],self.system)

    def test_update_seed_cannot_overwrite_modified_user_values(self):
        self.seed();cs.ensure_configuration(self.new)
        altered=cs.read(self.new/'print_settings/settings.json')
        altered.update(ditto_bold=False,ditto_font_size=23)
        altered['rules']['0921']['label']='現場新值'
        core.save_json(self.new/'print_settings/settings.json',altered)
        system=dict(self.system,database_path='onsite.mdb',order_mode='merge')
        core.save_json(self.new/'preferences.json',system)
        before=self.snapshot(self.new)
        self.seed();cs.ensure_configuration(self.new)
        for path,data in before.items():
            if path != 'print_settings\\catalog.json' and path != 'print_settings/catalog.json':
                self.assertEqual((self.new/path).read_bytes(),data)
        refreshed=cs.read(self.new/'print_settings/catalog.json')
        self.assertEqual(refreshed['settings']['machine_rules']['0921']['label'],'現場新值')

    def test_missing_new_option_gets_default_but_saved_false_survives(self):
        del self.settings['ditto_bold'];self.write_old();cs.ensure_configuration(self.old)
        actual=cs.read_bundle(self.old)['settings']
        self.assertTrue(actual['ditto_bold']);self.assertFalse(actual['fixed_20_rows'])

    def test_repeated_upgrade_does_not_shift_bio_or_rewrite_user_files(self):
        from workbook.catalog_settings import set_override
        self.layout=set_override(self.layout,'0921','AC','生化／糞便')
        self.layout.pop('bio_adult_slot');self.layout['placements']['0921']['subregion']='A'
        self.write_old();cs.ensure_configuration(self.old);before=self.snapshot(self.old)
        cs.ensure_configuration(self.old)
        self.assertEqual(before,self.snapshot(self.old))
        self.assertEqual(cs.read_bundle(self.old)['layout']['placements']['0921']['subregion'],'B')

    def test_current_startup_reuses_verified_catalog_without_rebuilding_or_writing(self):
        self.seed();first=cs.ensure_configuration(self.new);before=self.snapshot(self.new)
        from workbook import catalog_settings
        with patch.object(cc,'build',side_effect=AssertionError('unnecessary rebuild')), \
                patch.object(catalog_settings,'records',side_effect=AssertionError('unnecessary projection')), \
                patch.object(cs,'transaction',side_effect=AssertionError('unnecessary write')):
            second=cs.ensure_configuration(self.new)
        self.assertEqual(first,second);self.assertEqual(before,self.snapshot(self.new))

    def test_cache_invalidations_rebuild_once_and_preserve_settings(self):
        self.seed();baseline=cs.ensure_configuration(self.new)
        cache_path=self.new/'print_settings/catalog.json'
        for mutation in ('version','projection','settings_projection','normalization','dictionary'):
            with self.subTest(mutation=mutation):
                document=copy.deepcopy(baseline['catalog'])
                if mutation=='version':document['app_version']='previous-version'
                elif mutation=='projection':document['records'][0]['label']='stale'
                elif mutation=='settings_projection':document['settings']['machine_rules']['0921']['label']='stale'
                elif mutation=='normalization':document.pop('normalization_version')
                else:document['raw_catalog']['items'][0]['LCI_NAME']='updated dictionary name'
                core.save_json(cache_path,document)
                with patch.object(cc,'build',wraps=cc.build) as rebuild:
                    result=cs.ensure_configuration(self.new)
                    self.assertEqual(rebuild.call_count,1)
                    self.assertEqual(cs.ensure_configuration(self.new),result)
                    self.assertEqual(rebuild.call_count,1)
                self.assertEqual(result['settings'],baseline['settings'])
                self.assertEqual(result['layout'],baseline['layout'])
                if mutation=='dictionary':
                    self.assertEqual(result['catalog']['raw_catalog']['items'][0]['LCI_NAME'],'updated dictionary name')

    def test_invalid_layout_is_rejected_even_with_current_cache(self):
        self.seed();cs.ensure_configuration(self.new)
        path=self.new/'print_settings/layout_settings.json';layout=cs.read(path)
        layout['placements']['0921']['position']=999;core.save_json(path,layout)
        before=self.snapshot(self.new)
        with self.assertRaises(ValueError):cs.ensure_configuration(self.new)
        self.assertEqual(before,self.snapshot(self.new))

    def test_import_new_folder_preserves_every_setting_and_old_source(self):
        self.seed();cs.ensure_configuration(self.new);before=self.snapshot(self.old)
        result=cs.import_previous(self.old,self.new)
        self.assertTrue(result['system_imported']);self.assertTrue(result['backup'].exists())
        self.assertEqual(cs.read_bundle(self.new)['settings'],self.settings)
        self.assertEqual(before,self.snapshot(self.old))

    def test_print_only_import_never_changes_system(self):
        self.seed();cs.ensure_configuration(self.new)
        current=dict(self.system,database_path='current.mdb')
        core.save_json(self.new/'preferences.json',current)
        result=cs.import_previous(self.old,self.new,False)
        self.assertFalse(result['system_imported']);self.assertEqual(cs.read(self.new/'preferences.json'),current)

    def test_missing_source_preferences_does_not_read_legacy_path_keys(self):
        (self.old/'preferences.json').unlink()
        self.seed();cs.ensure_configuration(self.new)
        before=(self.new/'preferences.json').read_bytes()
        result=cs.import_previous(self.old,self.new)
        self.assertFalse(result['system_imported']);self.assertEqual((self.new/'preferences.json').read_bytes(),before)
        cs.ensure_configuration(self.old)
        self.assertEqual(cs.read(self.old/'preferences.json'),cs.system_defaults(self.old))

    def test_empty_existing_preferences_beats_package_seed(self):
        self.seed();core.save_json(self.new/'preferences.json',{})
        cs.ensure_configuration(self.new)
        self.assertEqual(cs.read(self.new/'preferences.json'),{})

    def test_bad_json_blocks_upgrade_and_preserves_all_original_files(self):
        self.seed();cs.ensure_configuration(self.new)
        (self.old/'workbook/layout_settings.json').write_text('bad',encoding='utf-8')
        before=self.snapshot(self.new)
        with self.assertRaises(ValueError):cs.import_previous(self.old,self.new)
        self.assertEqual(self.snapshot(self.new),before)

    def test_bad_preferences_not_silently_replaced(self):
        self.seed();core.save_json(self.new/'preferences.json',{'order_mode':'invalid'})
        before=self.snapshot(self.new)
        with self.assertRaises(ValueError):cs.ensure_configuration(self.new)
        self.assertEqual(self.snapshot(self.new),before)

    def test_missing_required_layout_no_partial_import(self):
        (self.old/'workbook/layout_settings.json').unlink()
        with self.assertRaises(ValueError):cs.import_previous(self.old,self.new)
        self.assertFalse(self.new.exists())

    def test_write_failure_rolls_back_all_targets_byte_for_byte(self):
        self.seed();cs.ensure_configuration(self.new);before=self.snapshot(self.new)
        replace=cs.os.replace;calls=0
        def fail_second(source,target):
            nonlocal calls
            calls+=1
            if calls==2:raise OSError('Synthetic disk failure')
            return replace(source,target)
        with patch.object(cs.os,'replace',side_effect=fail_second):
            with self.assertRaises(OSError):cs.import_previous(self.old,self.new)
        self.assertEqual(self.snapshot(self.new),before)
        self.assertFalse(list(self.new.rglob('*.tmp')))

    def test_backup_can_be_used_as_import_source(self):
        folder=self.root/'backup';cs.export_backup(self.old,folder)
        cs.import_previous(folder,self.new)
        self.assertEqual(cs.read_bundle(self.new)['settings'],self.settings)
        self.assertEqual(cs.read_bundle(self.new)['system'],self.system)

    def test_old_and_new_source_formats_both_supported(self):
        cs.ensure_configuration(self.old);cs.import_previous(self.old,self.new)
        self.assertEqual(cs.read_bundle(self.old)['settings'],cs.read_bundle(self.new)['settings'])

    def test_source_without_catalog_does_not_reuse_unrelated_destination_catalog(self):
        (self.old/'workbook/catalog.json').unlink();self.seed();cs.ensure_configuration(self.new)
        cs.import_previous(self.old,self.new)
        self.assertIsNone(cs.read_bundle(self.new)['catalog'])
        self.assertIsNone(cc.load('',self.settings,self.layout,path=self.new/'print_settings/catalog.json'))

    def test_print_persistence_has_no_system_keys_or_transient_layout(self):
        path=self.root/'print.json'
        core.save_print_settings(dict(self.settings,**self.system,layout=self.layout),path)
        from .settings_history import content,display
        saved=cs.read(path)
        self.assertEqual(content(saved),content(self.settings))
        self.assertTrue(display(saved['updated_at']))

    def test_same_folder_import_refused(self):
        with self.assertRaises(ValueError):cs.import_previous(self.old,self.old)


if __name__=='__main__':unittest.main()
