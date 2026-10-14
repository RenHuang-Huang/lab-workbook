"""Synthetic PDF regressions for slot borrowing and real glyph height fitting."""
import copy
import tempfile
import unittest
from pathlib import Path
import pdfplumber
from workbook import core,handwritten,catalog_settings as cs,print_geometry as pg
from workbook import subregions as sr,layout_settings as ls
from workbook.pdf_fonts import PdfFonts,glyph_metrics
from workbook.test_print_preferences_v45 import data_rows,render,MM


def placed(patterns,zone='e411',size=16):
    data,s=data_rows(patterns)
    key=sr.ZONE_KEYS[zone]
    s.update(show_column_headers=True)
    s['font_sizes'][key]=size
    for code in {c for row in patterns for c in row}:
        s['layout']=cs.set_override(s['layout'],code,code,zone)
        s['layout']['placements'][code].update(subregion='A',position=None)
        if zone=='e411':s['rules'][code]=dict(group='e411',label=code)
    return data,s


def zone_chars(pages,col,top,bottom):
    left=(10+sum(handwritten.WIDTHS[:col]))*MM
    right=left+handwritten.WIDTHS[col]*MM
    return [c for c in pages[0] if left<=c['x0']<right and top*MM<297*MM-c['matrix'][5]<bottom*MM]


class ReadableLayoutTests(unittest.TestCase):
    def test_other_uses_equal_local_columns_even_when_another_row_has_three(self):
        for fixed in (True,False):
            data,s=placed([['HbA1c','mab','uTP','ucr'],[f'X{i}' for i in range(7)]],'其他')
            s['fixed_20_rows']=fixed
            result,pages=render(data,s);entry=result['row_layout'][0]
            chars=zone_chars(pages,10,entry['top_mm'],entry['top_mm']+entry['height_mm'])
            self.assertEqual(result['subregion_columns']['other'],3)
            self.assertAlmostEqual(chars[-3]['x0']-chars[0]['x0'],12.5*MM,places=3)
            self.assertEqual(len({round(c['size'],4) for c in chars}),1)

    def test_other_equal_width_respects_explicitly_reserved_middle_column(self):
        layout=sr.migrate(ls.defaults(),[])
        items=[dict(label='A',placement=dict(subregion='A')),dict(label='C',placement=dict(subregion='C'))]
        layout['subregions']['其他']['B']['compact_subregions']=False
        groups=sr.arrange(items,'其他',layout)
        count,width,spans=pg.region_grid(groups,'other',6,25,layout)
        self.assertEqual(count,3);self.assertAlmostEqual(width,25/3)
        self.assertEqual(spans,{0:1,2:1})

    def test_other_adaptive_force_overflow_keeps_result_lines_for_non_machine_items(self):
        from workbook.adaptive_layout import zone_plan
        from workbook.print_style import Ink
        items=[dict(label=f'X{i}',placement=dict(subregion='A')) for i in range(28)]
        layout=sr.migrate(ls.defaults(),[])
        plan=zone_plan(items,'other',layout,1,25,16,
                       lambda item,seen: ([(item['label'],Ink('#202830'))],[]),
                       lambda text,size: len(text)*size*.15,force=True)
        size,lanes=plan['packed'];pieces=[p for lane in lanes for p in lane]
        self.assertEqual(len(pieces),28)
        self.assertTrue(all(p['result']>0 for p in pieces))
        self.assertEqual(len({p['width'] for p in pieces}),1)

    def test_other_keeps_text_serials_and_positive_result_lines_inside_equal_cells(self):
        for fixed in (True,False):
            data,s=placed([['HbA1c','mab','uTP','ucr']],'其他')
            s['fixed_20_rows']=fixed
            for code,group in [('HbA1c','hba1c'),('mab','mab')]:s['rules'][code]=dict(group=group,label=code)
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'synthetic.pdf'
                result=core.export_pdf(path,core.make_rows(data,s),data['date'],s)
                with pdfplumber.open(path) as pdf:
                    page=pdf.pages[0];entry=result['row_layout'][0]
                    chars=zone_chars([page.chars],10,entry['top_mm'],entry['top_mm']+entry['height_mm'])
                    labels=[c for c in chars if c['text'].isalpha()]
                    self.assertGreater(labels[0]['size'],10)
                    self.assertEqual(len({round(c['size'],4) for c in labels}),1)
                    lines=[l for l in page.lines if l['linewidth']==.25 and l['x0']>=175*MM]
                    self.assertEqual(len(lines),4)
                    for line in lines:
                        right=(187.5 if line['x0']<187.5*MM else 200)*MM
                        self.assertGreaterEqual(line['width']/MM,1.49)
                        self.assertLessEqual(line['x1'],right-.39*MM)
                    for char in chars:
                        right=(187.5 if char['x0']<187.5*MM else 200)*MM
                        self.assertLess(char['x1'],right-1.4*MM)

    def test_other_overflow_columns_share_size_only_within_current_order(self):
        for fixed in (True,False):
            for single_max in (False,True):
                data,s=placed([['HbA1c','mab','uTP','ucr'],['HbA1c','mab','uTP']],'其他')
                s['fixed_20_rows']=fixed
                for code,group in [('HbA1c','hba1c'),('mab','mab')]:s['rules'][code]=dict(group=group,label=code)
                if single_max:s['layout']['subregions']['其他']['B']['display']='single_max'
                source=copy.deepcopy(s);result,pages=render(data,s)
                layouts=result['row_layout']
                first=layouts[0];second=layouts[1]
                a=zone_chars(pages,10,first['top_mm'],first['top_mm']+first['height_mm'])
                b=zone_chars(pages,10,second['top_mm'],second['top_mm']+second['height_mm'])
                labels=[c for c in a if c['text'].isalpha()]
                self.assertEqual(''.join(c['text'] for c in a),'HbA1c1mab1/uTPucr')
                self.assertEqual(len({round(c['size'],4) for c in labels}),1)
                self.assertGreater(min(c['size'] for c in b if c['text'].isalpha()),labels[0]['size'])
                if not single_max:
                    self.assertAlmostEqual(a[-3]['x0']-a[0]['x0'],12.5*MM,places=3)
                    self.assertAlmostEqual(a[-3]['matrix'][5],a[0]['matrix'][5],places=3)
                self.assertEqual(result['sequences']['hba1c'],2);self.assertEqual(result['sequences']['mab'],2)
                self.assertEqual(s,source)

    def test_other_forced_columns_share_size_and_preserve_every_label(self):
        for fixed in (True,False):
            long='LongLabel'*15
            data,s=placed([[long,'mab','uTP','ucr']],'其他')
            s.update(fixed_20_rows=fixed,force_export=True)
            result,pages=render(data,s);entry=result['row_layout'][0]
            chars=zone_chars(pages,10,entry['top_mm'],entry['top_mm']+entry['height_mm'])
            self.assertEqual(''.join(c['text'] for c in chars),long+'mabuTPucr')
            self.assertEqual(len({round(c['size'],4) for c in chars}),1)
            self.assertTrue(result['forced_adjustments'])

    def test_other_uniformity_does_not_reduce_e411_sparse_trailing_column(self):
        data,s=placed([['Ferritin','sAg','T4','AFP']],'e411')
        s['force_export']=True
        result,pages=render(data,s);entry=result['row_layout'][0]
        chars=zone_chars(pages,9,entry['top_mm'],entry['top_mm']+entry['height_mm'])
        self.assertGreater(chars[-1]['size'],next(c['size'] for c in chars if c['text']=='F'))

    def test_sparse_ferritin_uses_empty_right_slots_in_both_height_modes(self):
        for fixed in (True,False):
            data,s=placed([['Ferritin'],[f'X{i}' for i in range(9)]])
            s['fixed_20_rows']=fixed
            source=copy.deepcopy(data);result,pages=render(data,s)
            top=result['body_top_mm'];end=top+handwritten.page_geometry(s)[1]
            chars=zone_chars(pages,9,top,end)
            ferritin=[c for c in chars if c['text'].isalpha()]
            self.assertEqual(''.join(c['text'] for c in ferritin),'Ferritin')
            self.assertTrue(all(abs(c['size']-16)<.01 for c in ferritin))
            self.assertEqual(result['subregion_columns']['e411'],3)
            self.assertFalse(result['forced_adjustments']);self.assertEqual(data,source)
            # The start of each column still uses the shared 9 mm grid.
            xs=[c['x0'] for c in pages[0] if c['text']=='X']
            self.assertAlmostEqual(xs[3]-xs[1],9*MM,places=3)
            self.assertAlmostEqual(xs[6]-xs[3],9*MM,places=3)

    def test_two_lane_bio_keeps_target_font_and_original_anchors(self):
        codes=['AC','OT','PT','cre','uA','CHO','LDL']
        data,s=placed([codes],zone='生化／糞便')
        for label,letter in [('AC','B'),('OT','C'),('PT','C'),('cre','D'),('uA','D'),('CHO','E'),('LDL','F')]:
            s['layout']['placements'][label]['subregion']=letter
        s['layout']['subregions']['生化／糞便']['A']['compact_subregions']=False
        result,pages=render(data,s);top,height=handwritten.page_geometry(s)
        chars=zone_chars(pages,6,top,top+height)
        self.assertTrue(chars);self.assertTrue(all(abs(c['size']-16)<.01 for c in chars))
        self.assertEqual(result['rows_per_page'],20)
        self.assertAlmostEqual(min(c['x0'] for c in chars)/MM,67+8.5+.6,places=3)
        self.assertEqual(''.join(c['text'] for c in chars),'ACOTPTcreuACHOLDL')

    def test_borrowing_stops_at_occupied_or_intentionally_reserved_subregions(self):
        layout=sr.migrate(ls.defaults(),[])
        items=[dict(label='A',placement=dict(subregion='A')),dict(label='C',placement=dict(subregion='C'))]
        layout['subregions']['e411']['B']['compact_subregions']=False
        groups=sr.arrange(items,'e411',layout)
        self.assertEqual(pg.group_spans(groups,4,'e411',layout),{0:1,2:2})
        layout['subregions']['e411']['D']['compact_subregions']=False
        self.assertEqual(pg.group_spans(groups,4,'e411',layout),{0:1,2:1})
        layout['subregions']['e411']['B']['compact_subregions']=True
        groups=sr.arrange(items,'e411',layout)
        self.assertEqual(pg.group_spans(groups,4,'e411',layout),{0:1,1:1})

    def test_group_shares_one_size_target_small_fonts_stay_small(self):
        for target in (6,16):
            data,s=placed([['Ferritin','sAg','T4']],'e411',target)
            s['serial_font_size']=target
            result,pages=render(data,s);top,height=handwritten.page_geometry(s)
            labels=[c for c in zone_chars(pages,9,top,top+height) if c['text'].isalpha()]
            self.assertEqual(len({round(c['size'],4) for c in labels}),1)
            self.assertLessEqual(max(c['size'] for c in labels),target+.01)
            if target==6:self.assertAlmostEqual(labels[0]['size'],6,places=3)

    def test_ink_stays_inside_lanes_with_descenders_cjk_and_raised_serials(self):
        for labels in (['AC','cre','T4'],['gyp','HCV','中文'],['Ferritin','HbA1c']):
            for superscript in (False,True):
                data,s=placed([labels]);s.update(serial_superscript=superscript,serial_font_size=20,force_export=True)
                result,pages=render(data,s);fonts=PdfFonts(s);top,height=handwritten.page_geometry(s)
                chars=zone_chars(pages,9,top,top+height)
                centers=[(top+pg.lane_center(i+1,len(labels),height))*MM for i in range(len(labels))]
                cell=height/(3 if len(labels)==2 else len(labels))*MM
                for c in chars:
                    ascent,descent=fonts.ink_metrics(c['size'],c['text'])
                    baseline=c['y0']-fonts.metrics(c['size'],c['text'])[1]
                    ink_top=297*MM-baseline-ascent;ink_bottom=297*MM-baseline-descent
                    center=min(centers,key=lambda y:abs(y-(ink_top+ink_bottom)/2))
                    self.assertGreaterEqual(ink_top,center-cell/2-.03)
                    self.assertLessEqual(ink_bottom,center+cell/2+.03)

    def test_three_line_and_force_limits_preserve_complete_text(self):
        label='VeryLongName'*20
        data,s=placed([[label,'B','C','D']])
        result,pages=render(data,dict(s,force_export=True))
        self.assertIn(label,''.join(c['text'] for c in pages[0]))
        self.assertEqual(result['rows_per_page'],20);self.assertTrue(result['forced_adjustments'])
        self.assertEqual(result['subregion_columns']['e411'],2)

    def test_font_ink_bounds_are_cached_and_fallback_faces_stay_supported(self):
        fonts=PdfFonts(core.default_settings())
        actual=fonts.ink_metrics(16,'AC');full=fonts.metrics(16,'AC')
        self.assertLess(actual[0]-actual[1],full[0]-full[1])
        previous=glyph_metrics.cache_info().hits
        self.assertEqual(fonts.ink_metrics(16,'AC'),actual)
        self.assertGreater(glyph_metrics.cache_info().hits,previous)
        fonts.mono='Courier'
        self.assertEqual(fonts.ink_metrics(16,'AC'),fonts.metrics(16,'AC'))


if __name__=='__main__':unittest.main()
