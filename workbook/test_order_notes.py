"""Artificial orders only: memo import, panel/merge rules and rendered PDF checks."""
import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import pdfplumber
from workbook import core,handwritten,order_note_rules as notes,catalog_settings as cs
from workbook import config_store,print_style,ditto
from workbook.errors import LayoutCapacityError
from workbook.test_print_preferences_v45 import data_rows,MM
from workbook.test_three_rows_panels import fixture as panel_fixture
from workbook import panel_children


def fixture(memos):
    data,s=data_rows([['AC','H','M','T','C','E'] for _ in memos])
    s.update(show_order_notes=True,apply_order_note_rules=True,export_glucose_ac=False)
    for header,memo in zip(data['headers'],memos):header['ORDER_NOTE']=memo
    for code,label,zone,group in [('H','HbA1c','其他','hba1c'),('M','mab','其他','mab'),
            ('T','uTP','其他','mab'),('C','ucr','其他','mab'),('E','sAg','e411','e411')]:
        s['rules'][code]=dict(label=label,group=group)
        s['layout']=cs.set_override(s['layout'],code,label,zone)
        s['layout']['placements'][code].update(subregion='A',position=None)
    return data,s


def prepared(data,s):return handwritten.prepare(core.make_rows(data,s),s)
def flattened(row):return [item for items in row['zones'].values() for item in items]


class OrderNotesTests(unittest.TestCase):
    def test_split_preserves_order_duplicates_and_empty_vs_not_fetched(self):
        self.assertEqual(core.split_order_notes(' + ; 補；安信\r\n缺尿;;+ '),['+','補','安信','缺尿','+'])
        data,s=fixture([None]);self.assertEqual(core.make_rows(data,s)[0]['order_notes'],[])
        del data['headers'][0]['ORDER_NOTE']
        self.assertIsNone(core.make_rows(data,s)[0]['order_notes'])

    def test_exact_plus_substrings_and_unique_marks(self):
        self.assertEqual(notes.flags(['++','+AC','AC+','A+B'])['visit_marks'],[])
        value=notes.flags([' + ','補單','補','安信轉送','缺尿待補'])
        self.assertEqual(value,dict(visit_marks=['+','補'],urine_marks=['安信','no UR'],suppress_mab=True))
        for invalid in (None,'+', [1]):
            with self.assertRaises(ValueError):notes.flags(invalid)

    def test_whole_mab_group_suppressed_and_next_sequence_continues(self):
        data,s=fixture(['','缺尿','']);rows=core.make_rows(data,s);before=copy.deepcopy((rows,s))
        result=handwritten.prepare(rows,s)
        self.assertEqual([r['mab_seq'] for r in result],[1,None,2])
        for group in ('e411','hba1c'):self.assertEqual([r[group+'_seq'] for r in result],[1,2,3])
        self.assertTrue({'mab','uTP','ucr'}<={i['label'] for i in flattened(result[1])})
        self.assertFalse(any('mab' in i['machines'] for i in flattened(result[1])))
        self.assertEqual((rows,s),before)

    def test_disabled_rules_restore_serials_while_memo_column_can_stay_enabled(self):
        data,s=fixture(['+;補;安信;缺尿']);s['apply_order_note_rules']=False
        row=prepared(data,s)[0];self.assertEqual(row['mab_seq'],1)
        self.assertNotIn('note_adjustments',row)
        self.assertFalse(any(i.get('note_annotation') for i in flattened(row)))
        self.assertEqual(row['order_notes'],['+','補','安信','缺尿'])

    def test_hidden_same_label_panel_serial_is_suppressed_without_hiding_panel(self):
        data,s=panel_fixture();s['layout']=cs.set_override(s['layout'],'G:PACK','mab','其他')
        s['layout']=panel_children.migrate(s['layout'],data,s)
        data['headers'][0]['ORDER_NOTE']='缺尿'
        row=prepared(data,s)[0];parent=next(i for i in flattened(row) if i['key']=='G:PACK')
        self.assertEqual(parent['label'],'mab');self.assertEqual(parent['machines'],[])
        self.assertIsNone(row['mab_seq'])
        self.assertEqual(row['panel_display'][0]['transferred_serial_groups'],[])

    def test_merge_preserves_every_note_visit_date_and_insurance(self):
        data,s=fixture(['+;安信','缺尿;補;+']);s.update(order_mode='merge',merge_exclusions_enabled=False)
        for header in data['headers']:header['LCHK_INDATE']=data['date']
        data['headers'][0].update(LCHK_OPDDATE='2026-10-12',INSURANCE_LABEL='人工保險')
        row=prepared(data,s)[0]
        self.assertEqual(row['merged_count'],2);self.assertEqual(row['order_notes'],['+','安信','缺尿','補','+'])
        self.assertEqual(row['visit_dates'],['2026-10-12']);self.assertEqual(row['insurance_label'],'人工保險')
        self.assertEqual(row['note_adjustments']['visit_marks'],['+','補']);self.assertIsNone(row['mab_seq'])
        self.assertEqual(len(row['order_notes_sources']),2)

    def test_memo_differences_do_not_hide_visit_or_urine_marks_under_ditto(self):
        data,s=fixture(['','補;安信']);s.update(ditto_patient=True,ditto_bio=True)
        rows=prepared(data,s);plan=ditto.plan(rows,s,s['layout'])
        self.assertTrue(plan[1]['bio']);self.assertTrue(plan[1]['patient'])
        self.assertEqual(rows[1]['note_adjustments']['visit_marks'],['補'])
        self.assertIn('安信',[i['label'] for i in rows[1]['zones']['cbc']])

    def test_app_reads_memos_when_either_option_requires_them(self):
        from workbook.app import App
        data,s=fixture([''])
        for show,adjust in [(False,False),(False,True),(True,False),(True,True)]:
            opts=dict(s,show_order_notes=show,apply_order_note_rules=adjust)
            app=SimpleNamespace(write_output=Mock(return_value='done'))
            with patch('workbook.app.read_access',return_value=data) as read:
                self.assertEqual(App.generate(app,'synthetic.mdb',data['date'],Path('.'),opts),'done')
            self.assertEqual(read.call_args.kwargs,dict(include_identity=True,include_order_notes=show or adjust))

    def test_new_defaults_and_saved_false_values_survive_normalization(self):
        s=core.default_settings();self.assertTrue(s['show_order_notes']);self.assertTrue(s['apply_order_note_rules'])
        _,s=fixture(['']);s.update(show_order_notes=False,apply_order_note_rules=False)
        normalized,_,_=config_store.normalize(s,s['layout'])
        self.assertFalse(normalized['show_order_notes']);self.assertFalse(normalized['apply_order_note_rules'])
        for key in ('show_order_notes','apply_order_note_rules'):
            with self.assertRaises(ValueError):print_style.validate_settings(dict(s,**{key:'yes'}))

    def test_unknown_memos_require_refresh_only_when_needed(self):
        data,s=fixture(['']);del data['headers'][0]['ORDER_NOTE'];rows=core.make_rows(data,s)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'out.pdf'
            for show,adjust in [(True,False),(False,True),(True,True)]:
                with self.assertRaisesRegex(ValueError,'重新匯入'):
                    core.export_pdf(path,rows,data['date'],dict(s,show_order_notes=show,apply_order_note_rules=adjust))
                self.assertFalse(path.exists())
            core.export_pdf(path,rows,data['date'],dict(s,show_order_notes=False,apply_order_note_rules=False))
            self.assertTrue(path.exists())

    def test_pdf_marks_are_red_bold_dates_preserved_and_memos_have_separate_rows(self):
        data,s=fixture(['+;補;安信','缺尿','']);data['headers'][0].update(LCHK_INDATE=data['date'],LCHK_OPDDATE='2026-10-12')
        with tempfile.TemporaryDirectory() as folder:
            for fixed in (True,False):
                path=Path(folder)/f'{fixed}.pdf';summary=core.export_pdf(path,core.make_rows(data,s),data['date'],dict(s,fixed_20_rows=fixed))
                self.assertEqual((summary['table_left_mm'],summary['table_right_mm']),(5,205))
                self.assertEqual(summary['order_notes']['entries'],4)
                self.assertEqual(summary['sequences'],dict(e411=3,hba1c=3,mab=2))
                with pdfplumber.open(path) as pdf:
                    chars=pdf.pages[0].chars
                    annotations=[c for c in chars if c['text'] in ('+','補','安','信','n','o','U','R') and c['x0']<195*MM]
                    self.assertTrue(annotations)
                    for c in annotations:
                        self.assertIn('Bold',c['fontname'])
                        self.assertEqual(tuple(round(v*255) for v in c['non_stroking_color']),(176,38,49))
                    memo=[c for c in chars if c['x0']>=195*MM and c['top']>summary['body_top_mm']*MM]
                    self.assertEqual(''.join(c['text'] for c in memo),'+補安信缺尿')
                    tops=sorted({round(c['top'],1) for c in memo if c['text'] in ('+','補','安')})
                    self.assertEqual(len(tops),3)
                    self.assertTrue(all(c['x1']<=205*MM for c in chars))
                    visit=[c for c in chars if 22*MM<=c['x0']<27*MM]
                    self.assertTrue({'1','2','0','+','補'}<={c['text'] for c in visit})

    def test_overflow_is_atomic_and_force_preserves_all_memo_characters(self):
        memo='人工長備註'*18;data,s=fixture([memo]);rows=core.make_rows(data,s)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'out.pdf';path.write_bytes(b'previous-output')
            with self.assertRaises(LayoutCapacityError):core.export_pdf(path,rows,data['date'],s)
            self.assertEqual(path.read_bytes(),b'previous-output');self.assertFalse(path.with_suffix('.partial.pdf').exists())
            summary=core.export_pdf(path,rows,data['date'],dict(s,force_export=True))
            self.assertTrue(summary['forced_adjustments'])
            with pdfplumber.open(path) as pdf:
                chars=[c for c in pdf.pages[0].chars if c['x0']>=195*MM and c['top']>summary['body_top_mm']*MM]
                self.assertEqual(''.join(c['text'] for c in chars),memo)

    def test_adaptive_many_note_rows_grow_and_paginate_without_omitting_entries(self):
        data,s=fixture([';'.join(['人工備註']*12)]*4);s['fixed_20_rows']=False
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'out.pdf';summary=core.export_pdf(path,core.make_rows(data,s),data['date'],s)
            self.assertEqual(summary['order_notes']['entries'],48)
            self.assertGreater(summary['row_layout'][0]['height_mm'],12)
            with pdfplumber.open(path) as pdf:
                chars=[c for page in pdf.pages for c in page.chars if c['x0']>=195*MM and c['top']>summary['body_top_mm']*MM]
                self.assertEqual(''.join(c['text'] for c in chars),'人工備註'*48)


if __name__=='__main__':unittest.main()
