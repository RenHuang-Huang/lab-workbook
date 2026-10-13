"""Panel-specific visibility and provenance tests use artificial orders only."""
import copy,unittest
from workbook import core,handwritten,panel_children as pc,catalog_settings as cs,catalog_batch as cb,catalog_cache as cc,settings_history as sh
from workbook.test_three_rows_panels import fixture

def setup():
    data,s=fixture();s['layout']=pc.migrate(s['layout'],data,s)
    return data,s

def prepared(data,s):return handwritten.prepare(core.make_rows(data,s),s)
def tokens(row):return {t['key']:t for items in row['zones'].values() for t in items}

class PanelChildrenTests(unittest.TestCase):
    def test_same_label_moves_each_number_to_parent_without_child(self):
        for code,label,zone,group in [('EE','sAg','e411','e411'),('HH','HbA1c','其他','hba1c'),('MM','mab','其他','mab')]:
            data,s=fixture();s['layout']=cs.set_override(s['layout'],'G:PACK',label,zone)
            s['layout']=pc.migrate(s['layout'],data,s)
            row=prepared(data,s)[0];items=tokens(row)
            self.assertNotIn(code,items);self.assertIn(group,items['G:PACK']['machines'])
            self.assertTrue(items['G:PACK']['serial_on_label']);self.assertEqual(row[group+'_seq'],1)
            self.assertFalse(s['layout']['panel_children']['G:PACK'][code])

    def test_hidden_numbered_child_with_different_label_has_no_number(self):
        data,s=setup();s['layout']['panel_children']['G:PACK']={c:False for c in ['AA','BB','EE','HH','MM']}
        row=prepared(data,s)[0]
        self.assertEqual(set(tokens(row)),{'G:PACK','CC'})
        self.assertEqual([row[g+'_seq'] for g in pc.NUMBERED],[None]*3)

    def test_transferred_number_stays_on_parent_when_ucr_uses_same_machine(self):
        data,s=fixture();s['layout']=cs.set_override(s['layout'],'G:PACK','mab','其他')
        s['rules']['AA']=dict(label='ucr',group='mab');s['layout']=cs.set_override(s['layout'],'AA','ucr','其他')
        s['layout']=pc.migrate(s['layout'],data,s)
        row=prepared(data,s)[0];items=tokens(row)
        self.assertEqual(items['AA']['machines'],[]);self.assertEqual(items['G:PACK']['machines'],['mab'])
        self.assertNotIn('MM',items);self.assertEqual(row['mab_seq'],1)

    def test_child_choices_override_single_but_do_not_change_it(self):
        data,s=setup();original=copy.deepcopy(s['layout']['placements'])
        s['layout']['panel_children']['G:PACK']['BB']=True
        s['layout']['placements']['BB']['print_enabled']=False
        row=prepared(data,s)[0];self.assertIn('BB',tokens(row))
        self.assertFalse(s['layout']['placements']['BB']['print_enabled'])
        self.assertEqual(original['EE'],s['layout']['placements']['EE'])

    def test_separate_same_code_on_same_order_is_not_hidden(self):
        data,s=setup();s['layout']['panel_children']['G:PACK']['AA']=False
        original=next(d for d in data['details'] if d['LCHK_ITEM']=='AA')
        data['details'].append(dict(original,LCHK_MKEY=''))
        row=prepared(data,s)[0];self.assertIn('AA',tokens(row))
        self.assertEqual(len([t for items in row['zones'].values() for t in items if t['key']=='AA']),1)

    def test_merged_independent_source_keeps_color_and_unlinked_mkey(self):
        data,s=setup();s.update(order_mode='merge',merge_exclusions_enabled=False,merged_color_enabled=True)
        data['headers'][0].update(CHART_NUMBER='ARTIFICIAL',LCHK_PATNAME='人工案例')
        data['headers'].append(dict(data['headers'][0],LCHK_WORKNO='00002'))
        source=next(d for d in data['details'] if d['LCHK_ITEM']=='AA')
        # A nonmatching MKEY on order 2 must not bind to order 1's panel after merging.
        data['details'].append(dict(source,LCHK_WORKNO='00002',LCHK_MKEY='PACK'))
        row=prepared(data,s)[0];item=tokens(row)['AA']
        self.assertEqual(row['merged_count'],2);self.assertEqual(item['color'],s['merged_order_colors'][1])
        origins=[x for x in row['source_items'] if x['code']=='AA']
        self.assertEqual({x['parent_panel'] for x in origins},{'PACK',''})

    def test_same_child_in_two_panels_has_separate_switches(self):
        data,s=setup();data['sets'].append(dict(data['sets'][0],LCS_ID='SECOND'))
        data['details'].append(dict(data['details'][-1],LCHK_ITEM='SECOND'))
        member=next(d for d in data['details'] if d['LCHK_ITEM']=='AA')
        data['details'].append(dict(member,LCHK_MKEY='SECOND'))
        s['layout']=pc.migrate(s['layout'],data,s)
        s['layout']['panel_children']['G:PACK']['AA']=False
        s['layout']['panel_children']['G:SECOND']['AA']=True
        self.assertIn('AA',tokens(prepared(data,s)[0]))
        s['layout']['panel_children']['G:SECOND']['AA']=False
        self.assertNotIn('AA',tokens(prepared(data,s)[0]))

    def test_no_phantom_serial_and_no_fourth_zone_rule(self):
        data,s=setup();s['layout']=cs.set_override(s['layout'],'G:PACK','mab','其他')
        s['layout']['panel_children']['G:PACK']['MM']=False
        data['details']=[d for d in data['details'] if d['LCHK_ITEM']!='MM']
        row=prepared(data,s)[0];self.assertIsNone(row['mab_seq'])
        self.assertEqual(tokens(row)['G:PACK']['machines'],[])

    def test_legacy_cross_zone_migration_preserves_decisions_and_is_idempotent(self):
        data,s=fixture();s['layout']['placements']['G:PACK'].update(print_mode='cross_zone',print_enabled=True)
        layout=pc.migrate(s['layout'],data,s)
        self.assertFalse(layout['panel_children']['G:PACK']['AA'])
        self.assertTrue(layout['panel_children']['G:PACK']['BB'])
        self.assertNotIn('print_mode',layout['placements']['G:PACK'])
        self.assertEqual(layout,pc.migrate(layout,data,s))
        layout['panel_children']['G:PACK']['EE']=False
        document=cc.build(data,s,layout);_,restored=cc.import_settings(document,s,data)
        self.assertEqual(restored['panel_children'],layout['panel_children'])

    def test_old_snapshots_require_refresh_instead_of_guessing(self):
        data,s=setup()
        for d in data['details']:d.pop('LCHK_MKEY',None)
        with self.assertRaisesRegex(ValueError,'重新從資料庫'):prepared(data,s)

    def test_case_lookup_shows_scoped_choice_and_separate_extra_item(self):
        from workbook.case_lookup import build_result
        data,s=fixture();s['layout']=cs.set_override(s['layout'],'G:PACK','mab','其他')
        s['layout']=pc.migrate(s['layout'],data,s)
        source=next(d for d in data['details'] if d['LCHK_ITEM']=='MM')
        data['details'].append(dict(source,LCHK_MKEY='',LCHK_VALUE='EXTRA'))
        result=build_result(data,'1',s,s['layout'])
        nodes=result['groups'][0]['orders'][0]['nodes']
        parent=next(n for n in nodes if n['kind']=='套組')
        child=next(n for n in parent['children'] if n['code']=='MM')
        self.assertEqual(child['print_state'],'否');self.assertIn('流水號印在套組名稱旁',child['status'])
        self.assertEqual(next(n for n in nodes if n['code']=='MM')['result'],'EXTRA')

    def test_child_batch_dates_isolation_and_tree(self):
        data,s=setup();before=copy.deepcopy(s['layout'])
        rows=pc.tree_rows(cs.records(data,s,before),data,s,before)
        child=next(r for r in rows if r['kind']=='套組子項' and r['code']=='AA')
        drafts=cb.Drafts();drafts.put('panel_children',child,dict(print_enabled=False),dict(print_enabled=True))
        candidate,updated=drafts.prepare(s,before)
        self.assertEqual(updated['placements'],before['placements'])
        self.assertEqual(candidate['rules'],s['rules']);self.assertTrue(updated['panel_children']['G:PACK']['AA'])
        _,stamped=sh.stamp_items(s,before,candidate,updated,data)
        self.assertIn(child['key'],stamped['item_updated_at']);self.assertIn('G:PACK',stamped['item_updated_at'])
        self.assertNotIn('AA',stamped['item_updated_at']);self.assertIn('人工套組 → 子項 AA',drafts.details())
        self.assertEqual(rows[child['_parent']]['key'],'G:PACK')

    def test_explicit_urine_children_are_not_folded(self):
        data,s=setup()
        for code,label in [('AA','U-cre'),('BB','U-ACR')]:
            s['rules'][code]=dict(label=label,group='routine');s['layout']=cs.set_override(s['layout'],code,label,'其他')
            s['layout']['panel_children']['G:PACK'][code]=True
        self.assertTrue({'AA','BB','MM'}<=set(tokens(prepared(data,s)[0])))

if __name__=='__main__':unittest.main()
