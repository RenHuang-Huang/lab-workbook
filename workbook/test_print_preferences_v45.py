"""Synthetic-only acceptance cases for configurable PDF marks and serials."""
import copy
import tempfile
import unittest
from pathlib import Path
import pdfplumber
from workbook import core,handwritten,print_style as ps,glucose_sheet as glucose,config_store
from workbook import layout_settings as ls,catalog_settings as cs,subregions as sr


def data_rows(patterns):
    data=dict(date='2026-10-14',headers=[],details=[],items=[],sets=[],set_members=[],
              hospitals=[dict(HOS_ID='DEMO',HOS_NAME='人工測試診所')],identity_local_only=False)
    settings=core.default_settings();settings.update(ditto_bio=False,ditto_patient=False)
    settings['layout']=sr.migrate(ls.defaults(),[])
    for code in dict.fromkeys(c for codes in patterns for c in codes):
        data['items'].append(dict(LCI_ID=code,LCI_NAME=code,LCI_NAMES=code))
        settings['layout']=cs.set_override(settings['layout'],code,code,'生化／糞便')
        settings['layout']['placements'][code]=dict(print_enabled=True,subregion='B',position=None)
    for index,codes in enumerate(patterns,1):
        workno=f'{index:05}'
        data['headers'].append(dict(LCHK_DEPT='DEMO',LCHK_WORKNO=workno,LCHK_SOURCE='DEMO',
                                   LCHK_PATNAME='人工個案',LCHK_SEX='1',CHART_NUMBER='TEST001'))
        data['details'] += [dict(LCHK_DEPT='DEMO',LCHK_WORKNO=workno,LCHK_ITEM=code,LCHK_ITEMTYPE='I',LCHK_ITEMSER=i)
                           for i,code in enumerate(codes)]
    return data,settings

MM=72/25.4

def render(data,settings,rows=None):
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'synthetic.pdf'
        summary=core.export_pdf(path,rows or core.make_rows(data,settings),data['date'],settings)
        with pdfplumber.open(path) as pdf:
            pages=[copy.deepcopy(page.chars) for page in pdf.pages]
        return summary,pages


class PrintPreferencesTests(unittest.TestCase):
    def test_new_defaults_and_validation(self):
        settings=core.default_settings()
        self.assertEqual((settings['ditto_font_size'],settings['ditto_bold'],settings['ditto_alignment']),(20,True,'center'))
        self.assertTrue(settings['ditto_keep_adult'])
        self.assertEqual((settings['serial_superscript'],settings['serial_font_size']),(False,14))
        self.assertEqual(ps.serial_colors(settings),ps.SERIAL_COLORS)
        for key,value in [('ditto_alignment','invalid'),('serial_font_size',0),('serial_font_size',True),
                          ('serial_font_size','nan'),('serial_superscript','yes'),('ditto_keep_adult',0),
                          ('serial_colors',{'e411':'bad'})]:
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):ps.validate_settings(dict(settings,**{key:value}))

    def test_pc_uses_actual_dictionary_codes_and_deduplicates_each_work_row(self):
        rows=[dict(workno=str(n),source_items=items) for n,items in enumerate([
            [dict(code='0921')],[dict(code='0941')],[dict(code='093')],
            [dict(code='0921'),dict(code='094'),dict(code='0941')],
            [dict(code='new',name='Glucose PC')],[dict(code='U13',name='Glucose',label='PC')],
            [dict(code='0941',type='G')]],1)]
        before=copy.deepcopy(rows);plan=glucose.header_plan(rows,{})
        self.assertEqual(plan['numbers'],[['1'],['2'],['3'],['4'],['5']])
        self.assertEqual(rows,before)
        self.assertEqual(glucose.header_plan(rows,{'export_glucose_ac':False})['records'],0)

    def test_pc_only_and_both_in_merged_row_have_one_header_cell(self):
        data,s=data_rows([['0941'],['0921']]);s.update(order_mode='merge',merge_workno_style='first',merge_exclusions_enabled=False)
        rows=core.make_rows(data,s);self.assertEqual(len(rows),1)
        self.assertEqual(glucose.header_plan(rows,s)['numbers'],[['1']])
        result,pages=render(data,s,rows)
        self.assertEqual(result['glucose_ac']['records'],1)
        self.assertIn('Glucose AC&PC',''.join(c['text'] for c in pages[0] if c['top']<10*MM))

    def test_alignment_coordinates_bold_and_size_in_both_ditto_columns(self):
        positions={}
        for align in ('left','center','right'):
            data,s=data_rows([['AA'],['AA']]);s.update(ditto_bio=True,ditto_patient=True,ditto_alignment=align)
            _,pages=render(data,s);symbols=sorted((c for c in pages[0] if c['text']=='〃'),key=lambda c:c['x0'])
            self.assertEqual(len(symbols),2)
            self.assertTrue(all(abs(c['size']-20)<.01 and 'Bold' in c['fontname'] for c in symbols))
            positions[align]=[c['x0'] for c in symbols]
        for index in (0,1):
            left,center,right=[positions[a][index] for a in ('left','center','right')]
            self.assertLess(left,center);self.assertLess(center,right)
            self.assertAlmostEqual((left+right)/2,center,places=3)

    def test_keep_at_marker_when_other_bio_is_ditto_and_reset_at_page_boundary(self):
        for fixed in (True,False):
            data,s=data_rows([['AA']]*22);s.update(ditto_bio=True,fixed_20_rows=fixed)
            rows=core.make_rows(data,s)
            for row in rows:row['adult_health_flag']=True
            before=copy.deepcopy(rows);result,pages=render(data,s,rows)
            self.assertEqual(sum(c['text']=='@' for page in pages for c in page),22)
            self.assertEqual(sum(c['text']=='〃' for page in pages for c in page),22-result['workbook_pages'])
            for page in pages:
                self.assertTrue(all(c['x1']<=200*MM+.1 and c['top']>=0 for c in page))
            self.assertEqual(rows,before)
            s['ditto_keep_adult']=False;result,pages=render(data,s,rows)
            self.assertEqual(sum(c['text']=='@' for page in pages for c in page),result['workbook_pages'])

    def test_at_alone_does_not_generate_empty_ditto_and_changing_at_does_not_hide_it(self):
        data,s=data_rows([[],[],['AA'],['AA'],['AA']]);s.update(ditto_bio=True)
        rows=core.make_rows(data,s)
        for i in (0,1,3):rows[i]['adult_health_flag']=True
        result,pages=render(data,s,rows)
        self.assertEqual([r['workno'] for r in result['ditto_rows']],['00004','00005'])
        self.assertEqual(sum(c['text']=='@' for c in pages[0]),3)

    def test_serial_baseline_size_custom_colors_and_superscript(self):
        for fixed in (True,False):
            for raised in (False,True):
                data,s=data_rows([['E','H','M']]);s.update(fixed_20_rows=fixed,serial_superscript=raised,
                    serial_colors={'e411':'#123456','hba1c':'#246B45','mab':'#7042A6'})
                for code,group,zone in [('E','e411','e411'),('H','hba1c','其他'),('M','mab','其他')]:
                    s['rules'][code]={'group':group,'label':code};s['layout']=cs.set_override(s['layout'],code,code,zone)
                    s['layout']['placements'][code].update(subregion='B' if code=='M' else 'A',position=None)
                s['font_sizes'].update(e411=12,other=12)
                result,pages=render(data,s)
                body=[c for c in pages[0] if c['x0']>148*MM and c['top']>result['body_top_mm']*MM]
                digits=[c for c in body if c['text']=='1'];letters=[c for c in body if c['text'] in ('E','H','M')]
                self.assertEqual(len(digits),3);self.assertEqual(len(letters),3)
                for digit,letter in zip(digits,letters):
                    self.assertAlmostEqual(digit['size'],14,places=2)
                    # pdfplumber's origin is top plus the font ascent; compare PDF baselines via matrix.
                    if raised:self.assertLess(digit['bottom'],letter['bottom'])
                    else:self.assertAlmostEqual(digit['matrix'][5],letter['matrix'][5],places=3)
                expected={tuple(int(h[i:i+2],16)/255 for i in (1,3,5)) for h in s['serial_colors'].values()}
                self.assertEqual({tuple(round(v,4) for v in c['non_stroking_color']) for c in digits},
                                 {tuple(round(v,4) for v in c) for c in expected})
                self.assertEqual(result['machine_serial_style'],'superscript' if raised else 'baseline')

    def test_saved_custom_settings_survive_normalize_and_backup_roundtrip(self):
        s=core.default_settings();s.update(ditto_alignment='right',ditto_font_size=17,ditto_bold=False,
            ditto_keep_adult=False,serial_superscript=True,serial_font_size=19,
            serial_colors={'e411':'#123456','hba1c':'#246B45','mab':'#7042A6'})
        saved,_,_=config_store.normalize(s,ls.defaults())
        for key in s:self.assertEqual(saved[key],s[key])
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);bundle=dict(settings=s,layout=ls.defaults(),catalog=None,system=None)
            config_store.transaction(config_store.targets(root,bundle))
            loaded=config_store.read_bundle(root)['settings']
            self.assertEqual(loaded,s)

    def test_dense_three_digit_serials_stay_in_row_and_preserve_all_digits(self):
        for fixed in (True,False):
            data,s=data_rows([['E','H','M']]*129);s.update(fixed_20_rows=fixed,force_export=True,serial_font_size=24,export_glucose_ac=False)
            for code,group,zone in [('E','e411','e411'),('H','hba1c','其他'),('M','mab','其他')]:
                s['rules'][code]={'group':group,'label':code};s['layout']=cs.set_override(s['layout'],code,code,zone)
                s['layout']['placements'][code].update(subregion='A',position=None)
            rows=core.make_rows(data,s)
            result,pages=render(data,s,rows);row=result['row_layout'][-1]
            glyphs=[c for c in pages[row['page']-1] if c['x0']>148*MM and c['top']>row['top_mm']*MM]
            self.assertEqual(sum(c['text']=='9' for c in glyphs),3)
            self.assertTrue(all(c['top']>=row['top_mm']*MM-.1 and c['bottom']<=(row['top_mm']+row['height_mm'])*MM+.1 for c in glyphs))

    def test_at_and_ditto_do_not_overlap_for_any_alignment(self):
        for align in ('left','center','right'):
            data,s=data_rows([['AA'],['AA']]);s.update(ditto_bio=True,ditto_alignment=align)
            rows=core.make_rows(data,s)
            for row in rows:row['adult_health_flag']=True
            summary,pages=render(data,s,rows);top=summary['row_layout'][1]['top_mm']*MM
            glyphs=[c for c in pages[0] if c['text'] in ('@','〃') and c['top']>top]
            self.assertEqual(len(glyphs),2);glyphs.sort(key=lambda c:c['x0'])
            self.assertLess(glyphs[0]['x1'],glyphs[1]['x0'])

if __name__=='__main__':unittest.main()
