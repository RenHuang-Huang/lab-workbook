"""Panel-scoped child visibility; never edits independent item settings."""
import copy,json

NUMBERED={'e411','hba1c','mab'}


def key(panel,code):return 'M:'+json.dumps([panel,code],ensure_ascii=False,separators=(',',':'))


def same_label(left,right):return bool(left.strip()) and left.strip().casefold()==right.strip().casefold()


def default_enabled(layout,panel_key,child):
    from . import subregions as sr
    rule=next((r for r in layout['rules'] if r['enabled'] and panel_key in r['codes']),None)
    parent=sr.placement(layout,panel_key,{'print_enabled':bool(rule)})
    if not parent['print_enabled']:return child.get('print_enabled',True)
    if not rule:return False
    if same_label(rule['label'],child['label']):return False
    if child.get('machine_group') in NUMBERED:return True
    return bool(parent.get('print_mode')=='cross_zone' and child.get('print_enabled',True) and child['zone']!=rule['zone'])


def enabled(layout,panel_key,child):
    children=layout.get('panel_children',{}).get(panel_key,{})
    return children[child['code']] if child['code'] in children else default_enabled(layout,panel_key,child)


def validate(layout):
    if 'panel_children_version' in layout and layout['panel_children_version']!=1:raise ValueError('套組子項設定版本不正確。')
    values=layout.get('panel_children',{})
    if not isinstance(values,dict):raise ValueError('套組子項設定格式不正確。')
    for panel,children in values.items():
        if not isinstance(panel,str) or not panel.startswith('G:') or not panel[2:] or not isinstance(children,dict):
            raise ValueError('套組子項必須對應真實套組代碼。')
        if any(not isinstance(code,str) or not code or type(value) is not bool for code,value in children.items()):
            raise ValueError('套組子項是否列印必須為勾選值。')


def migrate(layout,catalog,settings):
    """Seed only missing children, translating old cross-zone decisions once."""
    from .catalog_settings import records
    rows=records(catalog,settings,layout);singles={r['code']:r for r in rows if r['kind']=='單項'}
    result=copy.deepcopy(layout);values=result.setdefault('panel_children',{})
    members={}
    for member in catalog.get('set_members',[]):members.setdefault(str(member.get('LCS_UNIKEY')),set()).add(str(member.get('LCS_ITEM') or ''))
    for panel in catalog.get('sets',[]):
        code=str(panel.get('LCS_ID') or '')
        if not code:continue
        children=values.setdefault('G:'+code,{})
        for child_code in members.get(str(panel.get('LCS_UNIKEY')),set()):
            if not child_code:continue
            child=singles.get(child_code,dict(code=child_code,label=child_code,zone='待設定',print_enabled=True))
            if child_code not in children:children[child_code]=default_enabled(layout,'G:'+code,child)
    # Leave unknown legacy panels for migration when their dictionary becomes available.
    for panel,value in result.get('placements',{}).items():
        if panel in values:value.pop('print_mode',None)
    result['panel_children_version']=1;validate(result);return result


def tree_rows(roots,catalog,settings,layout):
    """Keep ordinary item keys separate from repeated per-panel child keys."""
    from .settings_history import display
    singles={r['code']:r for r in roots if r.get('kind')=='單項'};result=[]
    members={}
    for m in catalog.get('set_members',[]):members.setdefault(str(m.get('LCS_UNIKEY')),[]).append(str(m.get('LCS_ITEM') or ''))
    for parent in roots:
        index=len(result);result.append(copy.deepcopy(parent))
        if parent.get('kind')!='套組':continue
        for code in dict.fromkeys(members.get(str(parent.get('definition_id')),[])):
            if not code:continue
            child=copy.deepcopy(singles.get(code,dict(code=code,name='未在單項字典找到',label=code,zone='待設定',group='待設定',print_enabled=True)))
            child.update(key=key(parent['key'],code),kind='套組子項',panel_key=parent['key'],panel_name=parent['name'],
                _parent=index,definition_id=parent.get('definition_id'),clinic_code=parent.get('clinic_code'))
            child['print_enabled']=enabled(layout,parent['key'],child);child['print_state']='是' if child['print_enabled'] else '否'
            child['updated_at']=layout.get('item_updated_at',{}).get(child['key'])
            child['updated_display']=display(child['updated_at']) or '尚無紀錄'
            child['note']='只調整此套組內是否列印，不影響獨立單項或其他套組。列印代碼、區域、位置與配色沿用單項設定。'
            child['search']=parent['code']+' '+parent['name'];result.append(child)
    return result
