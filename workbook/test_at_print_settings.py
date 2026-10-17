"""Artificial-only regressions: IC metadata cannot override print choices."""
import copy
import unittest
from workbook import print_items


def fixture():
    layout=dict(version=3,rules=[dict(codes=['G:DEMO'],aliases=[],label='@',
        zone='生化／糞便',enabled=True)],placements={'G:DEMO':dict(print_enabled=False,subregion='A',position=None)},
        panel_children_version=1,panel_children={'G:DEMO':{'CHILD':True}})
    row=dict(clinic='人工診所',workno='00001',adult_health_flag=True,
        adult_compact_codes=['CHILD'],
        ordered_panels=[dict(code='DEMO',name='成健人工套組',present_members=['CHILD'],missing_members=[])],
        verified_panels=[dict(code='DEMO',name='成健人工套組',members=['CHILD'])],
        source_items=[dict(code='CHILD',label='AC',name='Glucose AC',type='I',
                           parent_panel='DEMO',parent_known=True)])
    return row,dict(rules={},compact_adult_health=True),layout


def prepare(row,settings,layout):
    return print_items.prepare([row],settings,layout)[0]


def tokens(row):
    return {item['key']:item for items in row['zones'].values() for item in items}


class AtPrintSettingsTests(unittest.TestCase):
    def test_disabled_parent_never_adds_flag_mark_and_keeps_checked_child(self):
        row,settings,layout=fixture();before=copy.deepcopy((row,settings,layout))
        self.assertEqual(set(tokens(prepare(row,settings,layout))),{'CHILD'})
        self.assertEqual((row,settings,layout),before)
        layout['panel_children']['G:DEMO']['CHILD']=False
        self.assertEqual(tokens(prepare(row,settings,layout)),{})

    def test_enabled_panel_uses_its_actual_label_and_zone_without_ic_requirement(self):
        row,settings,layout=fixture();layout['placements']['G:DEMO']['print_enabled']=True
        layout['panel_children']['G:DEMO']['CHILD']=False
        for flag in (False,True,None):
            for label,zone,key in [('@','生化／糞便','bio'),('@','其他','other'),('Au','生化／糞便','bio')]:
                with self.subTest(flag=flag,label=label,zone=zone):
                    row['adult_health_flag']=flag;layout['rules'][0].update(label=label,zone=zone)
                    printed=tokens(prepare(row,settings,layout))
                    self.assertEqual(set(printed),{'G:DEMO'})
                    self.assertEqual((printed['G:DEMO']['label'],printed['G:DEMO']['zone']),(label,key))

    def test_independently_ordered_member_is_not_folded_by_ic_flag(self):
        row,settings,layout=fixture()
        layout['panel_children']['G:DEMO']['CHILD']=False
        row['source_items'].append(dict(row['source_items'][0],parent_panel=''))
        result=prepare(row,settings,layout)
        self.assertEqual(set(tokens(result)),{'CHILD'})
        self.assertEqual(result['display_accounting'][-1]['display'],'AC')
        self.assertIsNone(result['display_accounting'][-1]['covered_by'])

    def test_single_at_and_panel_child_at_follow_their_own_switches(self):
        row,settings,layout=fixture()
        layout['rules'].append(dict(codes=['CHILD'],aliases=[],label='@',zone='其他',enabled=True))
        layout['placements']['CHILD']=dict(print_enabled=False,subregion='',position=None)
        # A panel child may print even when the independent single is disabled.
        printed=tokens(prepare(row,settings,layout))
        self.assertEqual(set(printed),{'CHILD'});self.assertEqual(printed['CHILD']['label'],'@')
        row['source_items'][0]['parent_panel']=''
        self.assertEqual(tokens(prepare(row,settings,layout)),{})
        layout['placements']['CHILD']['print_enabled']=True
        printed=tokens(prepare(row,settings,layout))
        self.assertEqual(set(printed),{'CHILD'});self.assertEqual(printed['CHILD']['zone'],'other')

    def test_ic_without_registered_at_source_prints_no_mark(self):
        row,settings,layout=fixture()
        row['ordered_panels']=[];row['source_items']=[]
        self.assertEqual(tokens(prepare(row,settings,layout)),{})


if __name__=='__main__':unittest.main()
