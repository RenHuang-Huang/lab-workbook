import copy,csv,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from . import usage_stats as stats,core,layout_settings as ls,catalog_settings as cs
from .test_catalog_cache import fixture


def sample():
    def count(kind,code,total,direct,uncertain=0):
        return dict(kind=kind,code=code,total_count=total,direct_count=direct,uncertain_count=uncertain,
            first_used='2024-01-01',last_used='2026-10-14',first_direct='2025-01-01' if direct else '',last_direct='2026-10-01' if direct else '')
    return dict(usage_statistics=True,start_date='2023-10-15',end_date='2026-10-14',order_count=12,
        unknown_detail_count=1,unresolved_detail_count=2,linked_detail_count=20,catalog=fixture(),
        counts=[count('G','0001',10,10),count('I','0921',10,3),count('I','344',5,0),count('I','UNKNOWN',2,2,2)])


class UsageTests(unittest.TestCase):
    def setUp(self):self.settings=core.default_settings();self.layout=ls.defaults();self.data=sample()
    def test_three_year_inclusive_period_and_leap_day(self):
        self.assertEqual(stats.period('2026-10-14'),('2023-10-15','2026-10-14'))
        self.assertEqual(stats.period('2024-02-29'),('2021-03-01','2024-02-29'))
        self.assertEqual(stats.period('2024-02-28'),('2021-02-28','2024-02-28'))
        for value in ('bad','2026-02-30','9999-12-31'):
            with self.assertRaises(ValueError):stats.period(value)
    def test_default_exclusion_and_toggle(self):
        rows={r['key']:r for r in stats.classify(self.data,self.settings,self.layout)}
        self.assertEqual(rows['0921']['count'],3);self.assertNotIn('344',rows)
        self.assertEqual(rows['G:0001']['count'],10);self.assertEqual(rows['UNKNOWN']['uncertain_count'],2)
        included={r['key']:r for r in stats.classify(self.data,self.settings,self.layout,False)}
        self.assertEqual(included['344']['count'],5);self.assertEqual(included['0921']['count'],10)
        self.assertEqual(rows['0921']['first_used'],'2025-01-01');self.assertEqual(included['0921']['first_used'],'2024-01-01')
    def test_current_override_zone_and_label_even_when_not_printed(self):
        self.layout=cs.set_override(self.layout,'0921','CUSTOM','外送')
        row=next(r for r in stats.classify(self.data,self.settings,self.layout) if r['code']=='0921')
        self.assertEqual((row['zone'],row['label']),('外送','CUSTOM'))
        # Missing dictionary code is retained, never silently invented or dropped.
        row=next(r for r in stats.classify(self.data,self.settings,self.layout) if r['code']=='UNKNOWN')
        self.assertEqual(row['zone'],'待設定')
    def test_shared_panel_definitions_aggregate_once_with_all_names(self):
        rows=[r for r in stats.classify(self.data,self.settings,self.layout) if r['kind']=='套組']
        self.assertEqual(len(rows),1);self.assertIn('甲組合',rows[0]['name']);self.assertIn('乙組合',rows[0]['name'])
        self.assertEqual(rows[0]['count'],10)
    def test_invalid_counts_rejected(self):
        for value in (-1,True,'3'):
            self.data['counts'][0]['total_count']=value
            with self.assertRaises(ValueError):stats.validate(self.data)
        self.data=sample();self.data['counts'].append(copy.deepcopy(self.data['counts'][0]))
        with self.assertRaises(ValueError):stats.validate(self.data)
    def test_exports_aggregate_only_and_csv_formula_safe(self):
        document=stats.report(self.data,self.settings,self.layout);document['rows'][0]['name']='=FORMULA'
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'report.json';stats.export(target,document)
            self.assertEqual(json.loads(target.read_text('utf-8')),document)
            target=target.with_suffix('.csv');stats.export(target,document)
            with target.open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.reader(stream))
            self.assertIn("'=FORMULA",rows[1]);self.assertEqual(len(rows),1+len(document['rows']))
        self.assertNotIn('catalog',document);self.assertNotIn('headers',document)
    def test_read_rejects_stale_bridge_and_database_changed(self):
        with tempfile.TemporaryDirectory() as temp:
            db=Path(temp)/'test.mdb';db.write_bytes(b'synthetic')
            def reader(database,script,args,timeout):
                core.save_json(Path(args[args.index('-Output')+1]),self.data)
            with patch('workbook.access_runtime.read_bridge',side_effect=reader):
                self.assertEqual(stats.read_usage(db,'2026-10-14'),self.data)
                self.data['start_date']='2025-01-01'
                with self.assertRaises(ValueError):stats.read_usage(db,'2026-10-14')
            def changed(*args):reader(*args);db.write_bytes(b'changed during reading')
            with patch('workbook.access_runtime.read_bridge',side_effect=changed):
                with self.assertRaisesRegex(ValueError,'有變動'):stats.read_usage(db,'2026-10-14')
    def test_usage_sql_never_selects_identity_or_results(self):
        script=Path(__file__).with_name('access_bridge.ps1').read_text('utf-8-sig')
        branch=script.split('if($UsageStatistics){',2)[-1].split('}elseif($CaseWorkNumber)')[0]
        for name in ('LCHK_PATNAME','LCHK_PATID','LCHK_VALUE','LPATIENT','LCHK_CARD','CHART_NUMBER'):
            self.assertNotIn(name,branch)
        self.assertIn('LCHK_MKEY',branch);self.assertIn('GetRows(2048)',branch)


if __name__=='__main__':unittest.main()
