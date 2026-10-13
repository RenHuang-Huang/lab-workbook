"""Artificial-only acceptance for three-row grids and panel visibility modes."""
import copy
import tempfile
import unittest
from pathlib import Path
import pdfplumber
from workbook import core,handwritten,catalog_settings as cs,catalog_cache as cc
from workbook import catalog_batch,layout_settings as ls,subregions as sr,print_geometry,config_store
from workbook.errors import LayoutCapacityError
from workbook.test_print_preferences_v45 import data_rows,render,MM


def fixture():
    data,s=data_rows([['AA','BB','CC','EE','HH','MM']])
    data['sets']=[dict(LCS_ID='PACK',LCS_NAME='人工套組',LCS_UNIKEY='P',LCS_HOSPITAL='DEMO')]
    data['set_members']=[dict(LCS_UNIKEY='P',LCS_ITEM=c,LCS_SERIAL=i) for i,c in enumerate(['AA','BB','EE','HH','MM','MISSING'])]
    data['details'].append(dict(LCHK_DEPT='DEMO',LCHK_WORKNO='00001',LCHK_ITEM='PACK',LCHK_ITEMTYPE='G'))
    layout=cs.set_override(s['layout'],'G:PACK','PACK','生化／糞便')
    for code,label,zone,group in [('BB','BB','外送','routine'),('EE','sAg','e411','e411'),('HH','HbA1c','其他','hba1c'),('MM','mab','其他','mab')]:
        layout=cs.set_override(layout,code,label,zone);s['rules'][code]=dict(label=label,group=group)
        layout['placements'][code].update(subregion='A',position=None)
    for detail in data['details']:
        detail['LCHK_MKEY']='PACK' if detail['LCHK_ITEM'] in {'AA','BB','EE','HH','MM'} else ''
    s['layout']=sr.migrate(layout,cs.records(data,s,layout))
    return data,s


def mode(data,s,value):
    record=next(r for r in cs.records(data,s,s['layout']) if r['key']=='G:PACK')
    candidate,layout=cs.edit_item(s,s['layout'],record,record['label'],record['zone'],print_enabled=value)
    return dict(candidate,layout=layout)


class ThreeRowTests(unittest.TestCase):
    def test_fourth_and_seventh_move_right_in_every_zone_and_height_mode(self):
        for zone,key in sr.ZONE_KEYS.items():
            for adaptive in (False,True):
                with self.subTest(zone=zone,adaptive=adaptive):
                    items=[dict(label=f'X{i}',placement=dict(subregion='A',position=None)) for i in range(7)]
                    layout=sr.migrate(ls.defaults(),[])
                    groups=sr.arrange(items,zone,layout,expand_vertical=adaptive,columns=1)
                    self.assertEqual([[p for p,_ in g['entries']] for g in groups],[[1,2,3],[1,2,3],[1]])
                    self.assertEqual([i['label'] for g in groups for _,i in g['entries']],[f'X{i}' for i in range(7)])

    def test_saved_fourth_fifth_position_spills_and_empty_columns_keep_alignment(self):
        layout=sr.migrate(ls.defaults(),[]);layout['subregions']['e411']['B']['compact_subregions']=False
        items=[dict(label='A',placement=dict(subregion='A',position=4)),dict(label='B',placement=dict(subregion='A',position=5)),dict(label='C',placement=dict(subregion='C',position=3))]
        groups=sr.arrange(items,'e411',layout,expand_vertical=True)
        self.assertTrue(all(p<=3 for g in groups for p,_ in g['entries']))
        self.assertEqual([i['label'] for _,i in groups[0]['entries']],['A','B'])
        self.assertEqual([g['column'] for g in groups],[0,1])
        layout['subregions']['e411']['A']['compact_subregions']=False
        self.assertEqual([g['column'] for g in sr.arrange(items,'e411',layout)],[1,2])

    def test_pdf_four_items_have_three_y_positions_and_fourth_to_right(self):
        for zone,key in sr.ZONE_KEYS.items():
            for fixed in (True,False):
                with self.subTest(zone=zone,fixed=fixed):
                    data,s=data_rows([['A','B','C','D']])
                    s.update(fixed_20_rows=fixed);s['font_sizes'][key]=8
                    for c in ('A','B','C','D'):
                        s['layout']=cs.set_override(s['layout'],c,c,zone)
                        s['layout']['placements'][c].update(subregion='A',position=None)
                    summary,pages=render(data,s)
                    left=10+sum(handwritten.WIDTHS[:{'bio':6,'cbc':7,'sendout':8,'e411':9,'other':10}[key]])
                    chars={c['text']:c for c in pages[0] if c['text'] in 'ABCD' and c['top']>summary['body_top_mm']*MM and left*MM<=c['x0']<(left+handwritten.WIDTHS[{'bio':6,'cbc':7,'sendout':8,'e411':9,'other':10}[key]])*MM}
                    self.assertEqual(set(chars),set('ABCD'))
                    self.assertAlmostEqual(chars['A']['x0'],chars['C']['x0'],places=3)
                    self.assertGreater(chars['D']['x0'],chars['A']['x0'])
                    self.assertAlmostEqual(chars['A']['top'],chars['D']['top'],places=3)
                    self.assertEqual(len({round(c['top'],2) for c in chars.values()}),3)

    def test_forced_overflow_retains_all_items_with_at_most_three_rows(self):
        codes=[f'X{i:02}' for i in range(35)]
        for zone,key in sr.ZONE_KEYS.items():
            for fixed in (True,False):
                with self.subTest(zone=zone,fixed=fixed):
                    data,s=data_rows([codes]);s.update(fixed_20_rows=fixed)
                    for c in codes:
                        s['layout']=cs.set_override(s['layout'],c,c,zone)
                        s['layout']['placements'][c].update(subregion='A',position=None)
                    with self.assertRaises(LayoutCapacityError):render(data,s)
                    summary,pages=render(data,dict(s,force_export=True))
                    text=''.join(c['text'] for c in pages[0]);self.assertTrue(all(code in text for code in codes))
                    chars=[c for c in pages[0] if c['text']=='X' and c['top']>summary['body_top_mm']*MM]
                    self.assertEqual(len(chars),len(codes));self.assertLessEqual(len({round(c['top'],2) for c in chars}),3)
                    self.assertTrue(summary['forced_adjustments'])

    def test_serial_runs_touch_labels_without_space_in_all_render_modes(self):
        for fixed,force in ((True,False),(False,False),(True,True),(False,True)):
            data,s=fixture();s.update(fixed_20_rows=fixed,force_export=force)
            if force:
                s['layout']=cs.set_override(s['layout'],'CC','VeryLongName'*10,'外送')
            summary,pages=render(data,s)
            chars=pages[0]
            for group,label in [('e411','sAg'),('hba1c','HbA1c'),('mab','mab')]:
                rgb=tuple(int(s['serial_colors'][group][i:i+2],16)/255 for i in (1,3,5))
                col=9 if group=='e411' else 10;left=(10+sum(handwritten.WIDTHS[:col]))*MM;right=left+handwritten.WIDTHS[col]*MM
                serial=next(c for c in chars if c['text']=='1' and left<=c['x0']<right and all(abs(a-b)<.001 for a,b in zip(c['non_stroking_color'],rgb)))
                same_line=[c for c in chars if abs(c['y0']-serial['y0'])<5 and abs(c['x0']-serial['x0'])<50 and c['text']!=' ']
                if group=='e411':
                    letter=min((c for c in same_line if c['text']==label[0] and c['x0']>=serial['x0']),key=lambda c:c['x0'])
                    self.assertLess(abs(letter['x0']-serial['x1']),.3)
                else:
                    letter=max((c for c in same_line if c['text']==label[-1] and c['x0']<serial['x0']),key=lambda c:c['x0'])
                    self.assertLess(abs(serial['x0']-letter['x1']),.3)


if __name__=='__main__':unittest.main()
