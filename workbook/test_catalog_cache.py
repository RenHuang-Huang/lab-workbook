import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from workbook import core,layout_settings as ls,catalog_cache as cc

def fixture():
    return {'items':[dict(LCI_ID='0921',LCI_NAME='Glucose',LCI_NHICODE='09005C'),dict(LCI_ID='344',LCI_NAME='TIBC',LCI_NHICODE='09045C')],
            'hospitals':[dict(HOS_ID='001',HOS_NAME='測試診所')],
            'sets':[dict(LCS_ID='0001',LCS_NAME='甲組合',LCS_UNIKEY='P1',LCS_HOSPITAL='001'),
                    dict(LCS_ID='0001',LCS_NAME='乙組合',LCS_UNIKEY='P2',LCS_HOSPITAL='9999')],
            'set_members':[dict(LCS_UNIKEY='P1',LCS_ITEM='0921',LCS_SERIAL=1),dict(LCS_UNIKEY='P1',LCS_ITEM='UNKNOWN',LCS_SERIAL=2),
                           dict(LCS_UNIKEY='P2',LCS_ITEM='344',LCS_SERIAL=1)]}

class CatalogCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.folder=Path(self.tmp.name)
        self.cache=self.folder/'catalog.json';self.db=self.folder/'demo.mdb';self.db.write_bytes(b'synthetic')
        self.settings=core.default_settings();self.layout=ls.defaults();self.catalog=fixture()
    def build(self):
        return cc.refresh(self.db,self.settings,self.layout,Mock(return_value=self.catalog),self.cache)
    def test_complete_lists_clinic_variants_members_and_privacy_allowlist(self):
        self.catalog['headers']=[{'LCHK_PATID':'DO-NOT-SAVE'}]
        self.catalog['items'][0]['patient']='DO-NOT-SAVE'
        self.layout['clinic_aliases']={'001':'測試院'}
        doc=self.build();self.assertNotIn('DO-NOT-SAVE',self.cache.read_text(encoding='utf-8'))
        self.assertEqual(doc['lists']['clinics'][0]['label'],'測試院')
        self.assertEqual(len(doc['lists']['sets']),2)
        a,b=doc['lists']['sets'];self.assertEqual(a['definition_id'],'P1');self.assertEqual(b['definition_id'],'P2')
        self.assertEqual(a['members'][0]['code'],'0921');self.assertEqual(a['members'][0]['nhi'],'09005C')
        self.assertEqual(a['missing_member_codes'],['UNKNOWN']);self.assertEqual(b['members'][0]['zone'],'外送')
        self.assertEqual(doc['lists']['items'][1]['rule_source'],'名稱別名')
    def test_cache_works_offline_and_changed_database_does_not_reuse_it(self):
        self.build();self.db.unlink()
        with patch('workbook.catalog_settings.records',side_effect=AssertionError('must not resolve on cache hit')):
            self.assertIsNotNone(cc.load(self.db,self.settings,self.layout,self.cache))
        self.assertIsNone(cc.load(self.folder/'other.mdb',self.settings,self.layout,self.cache))
    def test_setting_and_projection_changes_rebuild_locally(self):
        self.build();self.settings['rules']['0921']['group']='e411'
        doc=cc.load(self.db,self.settings,self.layout,self.cache)
        self.assertEqual(doc['lists']['items'][0]['machine_group'],'e411')
        doc['lists']['items'][0]['label']='STALE';cc.write(doc,self.cache)
        updated=cc.load(self.db,self.settings,self.layout,self.cache)
        self.assertNotEqual(updated['lists']['items'][0]['label'],'STALE')
    def test_failed_refresh_preserves_cache_and_settings(self):
        self.build();before=self.cache.read_bytes();settings=copy.deepcopy(self.settings)
        with self.assertRaises(OSError):cc.refresh(self.db,self.settings,self.layout,Mock(side_effect=OSError()),self.cache)
        self.assertEqual(self.cache.read_bytes(),before);self.assertEqual(self.settings,settings)
    def test_corrupt_cache_does_not_get_silently_accepted(self):
        self.cache.write_text('{bad',encoding='utf-8')
        with self.assertRaises(ValueError):cc.load(self.db,self.settings,self.layout,self.cache)
        self.assertEqual(self.cache.read_text(encoding='utf-8'),'{bad')
    def test_missing_codes_are_kept_for_review_without_invented_mapping(self):
        self.catalog['hospitals'].append({'HOS_ID':None,'HOS_NAME':'無代碼來源'})
        doc=self.build()
        self.assertEqual(doc['counts']['hospitals'],2)
        self.assertEqual(len(doc['lists']['clinics']),1)
        self.assertEqual(doc['lists']['unresolved'][0]['reason'],'缺少代碼')
        self.assertEqual(doc['review']['unresolved_dictionary_rows'],1)
    def test_import_only_overrides_retains_paths_and_does_not_promote_derived_items(self):
        doc=self.build();doc['lists']['items'][0]['label']='NOT-A-RULE'
        current=dict(self.settings,database_path='KEEP',output_directory='KEEP-OUT')
        candidate,layout=cc.import_settings(doc,current)
        self.assertEqual(candidate['database_path'],'KEEP');self.assertEqual(candidate['output_directory'],'KEEP-OUT')
        self.assertFalse(candidate['mapping_confirmed']);self.assertFalse(any('0921' in r['codes'] for r in layout['rules']))
        self.assertNotIn('NOT-A-RULE',json.dumps(candidate))
        doc['settings']['machine_rules']['0921']['group']='INVALID'
        with self.assertRaises(ValueError):cc.import_settings(doc,current)
    def test_batch_import_rolls_back_on_file_replace_failure(self):
        doc=self.build();sp=self.folder/'settings.json';lp=self.folder/'layout.json'
        cc.write(self.settings,sp);cc.write(self.layout,lp)
        before=[p.read_bytes() for p in (sp,lp,self.cache)]
        candidate=copy.deepcopy(self.settings);candidate['rules']['0921']['group']='e411'
        original=cc.os.replace;calls=0
        def replace(source,target):
            nonlocal calls
            calls+=1
            if calls==2:raise OSError('synthetic write error')
            return original(source,target)
        with patch.object(cc.os,'replace',side_effect=replace):
            with self.assertRaises(OSError):cc.apply_settings(doc,candidate,self.layout,sp,lp,self.cache)
        self.assertEqual([p.read_bytes() for p in (sp,lp,self.cache)],before)
        self.assertFalse(list(self.folder.glob('*.tmp')))
        out=cc.apply_settings(doc,candidate,self.layout,sp,lp,self.cache)
        self.assertEqual(out['lists']['items'][0]['machine_group'],'e411')

if __name__=='__main__':unittest.main()
