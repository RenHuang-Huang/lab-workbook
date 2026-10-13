"""Synthetic case lookup tests; no real database or clinical records."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from . import case_lookup as cases, core, layout_settings as ls


def fixture():
    settings = core.default_settings();layout = ls.defaults()
    layout['rules'] += [dict(label='LFT',zone='生化／糞便',codes=['G:P'],aliases=[],enabled=True),
                       dict(label='WBC',zone='CBC／尿液',codes=['B02'],aliases=[],enabled=True)]
    data = dict(date='2026-10-01', headers=[], details=[], identity_local_only=True, lookup_only=True,
        hospitals=[dict(HOS_ID='TEST',HOS_NAME='測試診所')],
        items=[dict(LCI_ID=c,LCI_NAME=n,LCI_NAMES=n) for c,n in [('101','G.O.T.'),('102','G.P.T.'),('B02','WBC')]],
        sets=[dict(LCS_ID='P',LCS_NAME='測試套組',LCS_UNIKEY='TEST-P',LCS_HOSPITAL='TEST')],
        set_members=[dict(LCS_UNIKEY='TEST-P',LCS_ITEM=c,LCS_SERIAL=i) for i,c in enumerate(('101','102'))])
    for number in ('00001','00002','00009'):
        data['headers'].append(dict(LCHK_DEPT='D',LCHK_WORKNO=number,LCHK_SOURCE='TEST',LCHK_PATNAME='人工個案',
            CHART_NUMBER='TEST-CHART',LCHK_SEX='女',LCHK_INDATE=data['date'],LCHK_OPDDATE=data['date']))
        for serial,(code,kind,value) in enumerate((('P','G',None),('101','I','11' if number=='00001' else '22'),('B02','I',0))):
            data['details'].append(dict(LCHK_DEPT='D',LCHK_WORKNO=number,LCHK_ITEM=code,LCHK_ITEMTYPE=kind,
                LCHK_ITEMSER=str(serial),LCHK_VALUE=value,LCHK_UNIT='U/L' if code=='101' else ''))
    return data,settings,layout


class LookupTests(unittest.TestCase):
    def setUp(self):
        self.data,self.settings,self.layout=fixture()

    def lookup(self,number='1'):
        return cases.build_result(self.data,number,self.settings,self.layout)

    def test_query_and_merge_keep_original_results(self):
        before=copy.deepcopy(self.data)
        result=self.lookup()
        self.assertEqual((result['matched_count'],result['order_count'],result['item_count']),(1,2,4))
        orders=result['groups'][0]['orders']
        self.assertEqual([r['workno'] for r in orders],['00001','00002'])
        self.assertEqual([r['matched'] for r in orders],[True,False])
        self.assertEqual([r['nodes'][0]['children'][0]['result'] for r in orders],['11','22'])
        self.assertEqual(self.data,before)

    def test_panel_hierarchy_absent_member_zero_and_settings(self):
        nodes=self.lookup()['groups'][0]['orders'][0]['nodes']
        self.assertEqual((nodes[0]['name'],nodes[0]['label'],nodes[0]['zone']),('測試套組','LFT','生化／糞便'))
        self.assertEqual(nodes[0]['status'],'已登錄 1/2 子項')
        self.assertEqual(nodes[0]['children'][1]['status'],'當單未登錄')
        self.assertEqual(nodes[0]['children'][1]['result'],'—')
        self.assertEqual(nodes[1]['result'],'0')
        self.assertEqual(nodes[1]['zone'],'CBC／尿液')

    def test_excluded_work_number_is_separate(self):
        result=self.lookup('009')
        self.assertEqual(result['order_count'],1);self.assertTrue(result['groups'][0]['excluded'])
        self.settings['merge_exclusions_enabled']=False
        self.assertEqual(self.lookup('9')['order_count'],3)

    def test_no_cross_patient_clinic_day_or_blank_chart_merges(self):
        for key,value in [('CHART_NUMBER',''),('LCHK_SOURCE','OTHER'),('LCHK_PATNAME','其他人工個案'),('LCHK_INDATE','2026-10-02')]:
            with self.subTest(key=key):
                data=copy.deepcopy(self.data);data['headers'][1][key]=value
                self.assertEqual(cases.build_result(data,'1',self.settings,self.layout)['order_count'],1)

    def test_leading_zero_and_no_match(self):
        self.assertEqual(self.lookup('000001')['order_count'],2)
        self.assertEqual(self.lookup('999')['groups'],[])

    def test_same_number_in_other_department_kept_separate(self):
        h=copy.deepcopy(self.data['headers'][0]);h.update(LCHK_DEPT='X',CHART_NUMBER='OTHER');self.data['headers'].append(h)
        result=self.lookup()
        self.assertEqual(result['matched_count'],2);self.assertEqual(len(result['groups']),2)

    def test_ambiguous_panel_definition_never_assigns_children(self):
        panel=copy.deepcopy(self.data['sets'][0]);panel['LCS_UNIKEY']='OTHER';self.data['sets'].append(panel)
        nodes=self.lookup()['groups'][0]['orders'][0]['nodes']
        self.assertEqual(nodes[0]['status'],'套組定義待核對');self.assertEqual(nodes[0]['children'],[])
        self.assertEqual([n['code'] for n in nodes[1:]],['101','B02'])

    def test_specific_clinic_definition_beats_generic(self):
        self.data['sets'].append(dict(LCS_ID='P',LCS_NAME='通用套組',LCS_UNIKEY='GENERIC',LCS_HOSPITAL='9999'))
        self.data['set_members'].append(dict(LCS_UNIKEY='GENERIC',LCS_ITEM='B02',LCS_SERIAL=0))
        node=self.lookup()['groups'][0]['orders'][0]['nodes'][0]
        self.assertEqual(node['name'],'測試套組');self.assertEqual(node['children'][0]['code'],'101')

    def test_repeated_results_preserved_and_shared_members_marked(self):
        self.data['sets'].append(dict(LCS_ID='Q',LCS_NAME='另一套組',LCS_UNIKEY='TEST-Q',LCS_HOSPITAL='TEST'))
        self.data['set_members'].append(dict(LCS_UNIKEY='TEST-Q',LCS_ITEM='101',LCS_SERIAL=0))
        row=copy.deepcopy(self.data['details'][0]);row.update(LCHK_ITEM='Q',LCHK_ITEMSER='4');self.data['details'].append(row)
        row=copy.deepcopy(self.data['details'][1]);row.update(LCHK_VALUE='33',LCHK_ITEMSER='5');self.data['details'].append(row)
        result=self.lookup();nodes=result['groups'][0]['orders'][0]['nodes']
        self.assertEqual(result['item_count'],5)
        self.assertEqual([c['result'] for c in nodes[0]['children'][:2]],['11','33'])
        self.assertEqual(nodes[0]['children'][0]['status'],'同單共用子項')

    def test_disabled_unknown_and_empty_type_items_are_kept(self):
        self.settings['rules']['B02']=dict(group='aux',label='WBC')
        self.data['details'][1]['LCHK_ITEMTYPE']=''
        result=self.lookup();nodes=result['groups'][0]['orders'][0]['nodes']
        self.assertEqual(nodes[-1]['print_state'],'否');self.assertEqual(result['item_count'],4)

    def test_all_result_fields_kept_without_interpretation(self):
        value=cases.result_text(dict(LCHK_VALUE=0,LCHK_VALUE2='Negative',LCHK_VALUE3='<1',LCHK_RESULT='+'))
        self.assertEqual(value,'0；值 2：Negative；值 3：<1；結果文字：+')

    def test_invalid_input(self):
        for day,number in [('2026-02-30','1'),('9999-12-31','1'),('2026-10-01',''),('2026-10-01','a\n1')]:
            with self.subTest(day=day,number=number),self.assertRaises(ValueError):cases.validate_query(day,number)

    def test_parameter_boundary_and_temporary_result_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'synthetic.mdb';db.write_bytes(b'artificial');targets=[]
            def bridge(database,script,args,timeout):
                self.assertEqual(script,'access_bridge.ps1');self.assertNotIn('-IncludeIdentity',args)
                self.assertEqual(args[args.index('-CaseWorkNumber')+1],"1' OR 1=1")
                target=Path(args[args.index('-Output')+1]);targets.append(target);core.save_json(target,self.data)
            with patch('workbook.access_runtime.read_bridge',side_effect=bridge):
                cases.read_case(db,'2026-10-01',"1' OR 1=1")
            self.assertFalse(targets[0].exists())

    def test_legacy_bridge_does_not_look_like_empty_results(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'synthetic.mdb';db.write_bytes(b'artificial')
            def bridge(database,script,args,timeout):
                target=Path(args[args.index('-Output')+1]);core.save_json(target,dict(date='2026-10-01'))
            with patch('workbook.access_runtime.read_bridge',side_effect=bridge),self.assertRaisesRegex(ValueError,'版本不符'):
                cases.read_case(db,'2026-10-01','1')

    def test_duplicate_source_headers_rejected(self):
        self.data['headers'].append(copy.deepcopy(self.data['headers'][0]))
        with self.assertRaisesRegex(ValueError,'重複'):self.lookup()

    def test_partial_result_file_removed_on_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'synthetic.mdb';db.write_bytes(b'artificial');targets=[]
            def bridge(database,script,args,timeout):
                target=Path(args[args.index('-Output')+1]);targets.append(target);core.save_json(target,self.data)
                raise ValueError('READ_FAILED')
            with patch('workbook.access_runtime.read_bridge',side_effect=bridge),self.assertRaises(ValueError):
                cases.read_case(db,'2026-10-01','1')
            self.assertFalse(targets[0].exists())


if __name__=='__main__':unittest.main()
