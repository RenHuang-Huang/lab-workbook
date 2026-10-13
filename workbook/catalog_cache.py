"""Reusable, allowlisted dictionaries and resolved print mappings. No order data."""
import copy,datetime as dt,hashlib,json,os,tempfile
from collections import defaultdict
from pathlib import Path
from .paths import ROOT
from .version import APP_VERSION

PATH=ROOT/'print_settings/catalog.json'
SCHEMA_VERSION=1
FIELDS={
    'items':('LCI_ID','LCI_NAME','LCI_NAMEC','LCI_NAMES','LCI_NHICODE'),
    'sets':('LCS_ID','LCS_NAME','LCS_NHICODE','LCS_HOSPITAL','LCS_UNIKEY'),
    'set_members':('LCS_UNIKEY','LCS_ITEM','LCS_SERIAL'),
    'hospitals':('HOS_ID','HOS_NAME'),
}

def clean(catalog):
    out={}
    for table,fields in FIELDS.items():
        rows=catalog.get(table,[])
        if not isinstance(rows,list):raise ValueError('JSON 字典格式不正確，請重新更新清單。')
        out[table]=[]
        for row in rows:
            if not isinstance(row,dict):raise ValueError('JSON 字典列格式不正確。')
            values={k:row.get(k) for k in fields}
            if any(v is not None and not isinstance(v,(str,int,float)) for v in values.values()):
                raise ValueError('JSON 字典欄位格式不正確。')
            out[table].append(values)
    return out

def display_catalog(catalog):
    """Keep unusable source rows in the audit, never invent a code for editing."""
    from collections import Counter
    valid=copy.deepcopy(catalog);unresolved=[]
    for table,key in [('items','LCI_ID'),('sets','LCS_ID'),('hospitals','HOS_ID')]:
        counts=Counter(str(row[key]) for row in catalog[table])
        valid[table]=[]
        for index,row in enumerate(catalog[table]):
            reason='缺少代碼' if not str(row[key] or '').strip() else '重複代碼' if table!='sets' and counts[str(row[key])]>1 else ''
            if reason:unresolved.append(dict(table=table,source_row=index+1,reason=reason,record=copy.deepcopy(row)))
            else:valid[table].append(row)
    return valid,unresolved

def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()

def overrides(settings,layout):
    from . import layout_settings as ls
    from .print_style import color_rules
    from .core import GROUP_NAMES
    ls.validate(layout)
    rules={}
    for code,rule in settings.get('rules',{}).items():
        group=rule.get('group','routine')
        if group not in GROUP_NAMES:raise ValueError('JSON 設定含不支援的機器分組。')
        rules[str(code)]={'group':group,'label':str(rule.get('label') or '')}
    return {'machine_rules':rules,'print_layout':copy.deepcopy(layout),'print_color_rules':color_rules(settings),'updated_at':settings.get('updated_at')}

def source_key(database):
    return os.path.normcase(str(Path(database).resolve())) if str(database).strip() else ''

def build(catalog,settings,layout,source=None,resolved_rows=None):
    from .catalog_settings import records
    from .core import GROUP_NAMES
    from .handwritten import clinic_label
    from . import layout_settings as ls
    catalog=clean(catalog);config=overrides(settings,layout)
    usable,unresolved=display_catalog(catalog)
    match_rule=ls.matcher(layout)
    resolved=copy.deepcopy([r for r in resolved_rows if r.get('kind') in ('單項','套組')] if resolved_rows is not None else records(usable,settings,layout))
    singles={};panels=[]
    raw_items={str(x['LCI_ID']):x for x in usable['items']}
    for record in resolved:
        key=record['key'];record['rule_source']='預設列印規則'
        if record['kind']=='單項':
            rule=settings.get('rules',{}).get(key,{'group':'routine'})
            record['machine_group']=rule.get('group','routine')
            record['machine_group_name']=GROUP_NAMES[record['machine_group']]
            item=raw_items[key]
            from .core import display_label
            matched=match_rule(dict(item,LCI_NAMES=display_label(key,raw_items,rule)))
            singles[key]=record
        else:matched=match_rule({'LCI_ID':key})
        if matched:
            record['rule_source']='明確代碼' if key in matched['codes'] else '名稱別名'
            record['matched_rule']=copy.deepcopy(matched)
        if record['kind']=='套組':panels.append(record)
    members=defaultdict(list)
    for row in catalog['set_members']:members[row['LCS_UNIKEY']].append(row)
    clinic_names={str(h['HOS_ID']):h['HOS_NAME'] for h in usable['hospitals']}
    for panel,raw in zip(panels,usable['sets']):
        uid=raw.get('LCS_UNIKEY');panel['definition_id']=uid
        panel['clinic_code']=raw.get('LCS_HOSPITAL') or ''
        panel['clinic_name']=clinic_names.get(str(panel['clinic_code']),'')
        panel['members']=[]
        for member in members[uid] if uid is not None else []:
            code=member['LCS_ITEM'];single=singles.get(str(code))
            panel['members'].append(dict(code=code,order=member.get('LCS_SERIAL'),
                name=single['name'] if single else '',nhi=single['nhi'] if single else '',
                label=single['label'] if single else '',zone=single['zone'] if single else '待核對',
                machine_group=single['machine_group'] if single else None,
                print_enabled=single['print_enabled'] if single else None,found=single is not None))
            panel['members'][-1].update(subregion=single['subregion'] if single else None,position=single['position'] if single else None,position_mode=single.get('position_mode','slot') if single else None)
        panel['machine_groups']=sorted({m['machine_group'] for m in panel['members'] if m['machine_group'] is not None})
        panel['missing_member_codes']=[m['code'] for m in panel['members'] if not m['found']]
        panel['member_count']=len(panel['members'])
        from .panel_children import enabled as child_enabled,key as child_key
        for member in panel['members']:
            member['panel_print_enabled']=child_enabled(layout,panel['key'],dict(member,print_enabled=member.get('print_enabled') is not False))
            member['panel_updated_at']=layout.get('item_updated_at',{}).get(child_key(panel['key'],str(member['code'])))
        if panel['name'].strip().startswith(('成健','不報成健')):
            panel['conditional_compression']='當筆IC旗標＋已驗證成健成員才合併為@'
    clinics=[dict(code=str(h['HOS_ID']),name=h['HOS_NAME'] or '',
        label=clinic_label(layout.get('clinic_aliases',{}).get(str(h['HOS_ID']),h['HOS_NAME'] or str(h['HOS_ID']))),
        rule_source='使用者設定' if str(h['HOS_ID']) in layout.get('clinic_aliases',{}) else '移除診所二字') for h in usable['hospitals']]
    document=dict(schema_version=SCHEMA_VERSION,app_version=APP_VERSION,updated_at=dt.datetime.now().isoformat(timespec='seconds'),
        source=copy.deepcopy(source or {}),settings_fingerprint=fingerprint(config),catalog_fingerprint=fingerprint(catalog),
        usage={'raw_catalog':'白名單資料庫字典，無病患資料','settings':'可重用的分組與列印規則；主要設定仍為 settings.json 與 layout_settings.json',
               'lists':'實際套用規則的校對清單，設定頁修改後自動重建；套組不推定為單一機器分組',
               'freshness':'新增／更名的資料庫字典須按更新；每日資料寫入不自動使字典快取失效'},
        settings=config,raw_catalog=catalog,lists={'clinics':clinics,'items':list(singles.values()),'sets':panels,'unresolved':unresolved},records=resolved,
        counts={k:len(v) for k,v in catalog.items()},
        review={'unresolved_dictionary_rows':len(unresolved),'missing_panel_members':sum(len(p['missing_member_codes']) for p in panels),
                'unconfigured_panel_aliases':sum(not p['label'] for p in panels)})
    document['projection_fingerprint']=fingerprint([document['records'],document['lists']])
    from .settings_history import latest
    document['settings_updated_at']=latest(settings.get('updated_at'),layout.get('updated_at'))
    return document

def write(document,path=None):
    target=Path(path) if path is not None else PATH
    target.parent.mkdir(parents=True,exist_ok=True)
    temp=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=target.parent,suffix='.tmp',delete=False) as f:
            temp=Path(f.name);json.dump(document,f,ensure_ascii=False,indent=2)
        os.replace(temp,target)
    finally:
        if temp is not None and temp.exists():temp.unlink()

def load(database,settings,layout,path=None):
    target=Path(path) if path is not None else PATH
    if not target.is_file():return None
    try:
        document=json.loads(target.read_text(encoding='utf-8-sig'))
        if document=={}:return None
        if document.get('schema_version')!=SCHEMA_VERSION:raise ValueError('清單版本不相容，請重新更新。')
        if source_key(database) and document['source'].get('database_key')!=source_key(database):return None
        catalog=clean(document['raw_catalog'])
        if document.get('catalog_fingerprint')!=fingerprint(catalog):raise ValueError('字典内容已變更，請從資料庫重新更新。')
        if (document.get('settings_fingerprint')!=fingerprint(overrides(settings,layout)) or document.get('app_version')!=APP_VERSION
                or document.get('projection_fingerprint')!=fingerprint([document.get('records'),document.get('lists')])):
            document=build(catalog,settings,layout,document['source']);write(document,target)
        # The dictionaries are the only database content consumed by the UI.
        if not isinstance(document.get('records'),list) or not isinstance(document.get('lists'),dict):raise ValueError('JSON 清單內容不完整。')
        return document
    except (KeyError,TypeError,json.JSONDecodeError):raise ValueError('JSON 清單無法讀取，請按「從資料庫更新清單」。') from None

def refresh(database,settings,layout,reader,path=None):
    catalog=reader(database)
    stat=Path(database).stat()
    source=dict(database_key=source_key(database),database_name=Path(database).name,
                fetched_at=dt.datetime.now().isoformat(timespec='seconds'),size=stat.st_size,mtime_ns=stat.st_mtime_ns,
                tables={'items':'LCHKITEM','sets':'LCHKSET1','set_members':'LCHKSET2','hospitals':'LHOSPITAL'})
    document=build(catalog,settings,layout,source);write(document,path);return document

def reconcile(document,settings,layout,resolved_rows=None,path=None):
    updated=build(document['raw_catalog'],settings,layout,document['source'],resolved_rows)
    write(updated,path);return updated

def import_settings(document,current,catalog=None):
    """Import override sections only. Never import paths, raw rows or projections."""
    try:
        if document['schema_version']!=SCHEMA_VERSION:raise ValueError('JSON 清單版本不相容。')
        config=document['settings'];rules=config['machine_rules'];raw=config['print_layout']
        if not isinstance(rules,dict) or not isinstance(raw,dict):raise ValueError('JSON 設定格式不正確。')
        for key,value in rules.items():
            if not isinstance(key,str) or not key.strip() or not isinstance(value,dict) or not isinstance(value.get('label',''),str):
                raise ValueError('機器分組／簡稱格式不正確。')
        layout={'version':2,'rules':[],'clinic_aliases':{}}
        for rule in raw['rules']:
            if (not isinstance(rule,dict) or not isinstance(rule.get('label'),str)
                    or not isinstance(rule.get('codes'),list) or not isinstance(rule.get('aliases'),list)
                    or not all(isinstance(v,str) for v in rule['codes']+rule['aliases'])):
                raise ValueError('列印規則格式不正確。')
            layout['rules'].append({key:rule[key] for key in ('label','zone','codes','aliases','enabled')})
        for code,label in raw.get('clinic_aliases',{}).items():
            if not isinstance(code,str) or not isinstance(label,str) or not label.strip():raise ValueError('診所簡稱格式不正確。')
            layout['clinic_aliases'][code]=label
        layout['code_colors']=copy.deepcopy(raw.get('code_colors',{}))
        for key in ('updated_at','item_updated_at','panel_children','panel_children_version'):
            if key in raw:layout[key]=copy.deepcopy(raw[key])
        for key in ('bio_auto_start','bio_groups_version'):
            if key in raw:layout[key]=copy.deepcopy(raw[key])
        if 'bio_adult_slot' in raw:
            if type(raw['bio_adult_slot']) is not bool:raise ValueError('生化配置版本格式不正確。')
            layout['bio_adult_slot']=raw['bio_adult_slot']
        if raw.get('version',2)>=3:
            layout['version']=3
            layout['placements']=copy.deepcopy(raw.get('placements',{}))
            layout['subregions']=copy.deepcopy(raw.get('subregions',{}))
        else:
            from . import subregions
            layout=subregions.migrate(layout,[])
        from . import source_panels
        if 'source_panels_migrated' in raw:
            if type(raw['source_panels_migrated']) is not bool:raise ValueError('套組設定版本格式不正確。')
            layout['source_panels_migrated']=raw['source_panels_migrated']
        if catalog is not None:layout,_=source_panels.transfer(layout,clean(catalog))
        else:
            layout=source_panels.strip_generated(layout);layout['source_panels_migrated']=True
        validated=overrides({'rules':rules},layout)
        candidate=copy.deepcopy(current);candidate['rules']=validated['machine_rules'];candidate['mapping_confirmed']=False
        if 'updated_at' in config:candidate['updated_at']=config['updated_at']
        from .settings_history import validate as validate_history
        validate_history(candidate)
        from .print_style import color_rules
        candidate['print_color_rules']=color_rules(config if 'print_color_rules' in config else current)
        if catalog is not None:
            from .panel_children import migrate as migrate_children
            usable,_=display_catalog(clean(catalog));layout=migrate_children(layout,usable,candidate)
        candidate.pop('layout',None)
        return candidate,layout
    except (KeyError,TypeError,AttributeError):raise ValueError('不是本程式可重用的 JSON 設定清單。') from None

def apply_settings(active,candidate,layout,settings_path=None,layout_path=None,cache_path=None,*,preserve_dates=False):
    """Stage all files first and roll back completed replacements on a failed save."""
    from . import core,layout_settings as ls
    from .settings_history import stamp_items
    previous=dict(core.default_settings(),rules=active['settings']['machine_rules'],
        print_color_rules=active['settings'].get('print_color_rules',[]),updated_at=active['settings'].get('updated_at'))
    source_path=Path(settings_path) if settings_path is not None else core.CONFIG
    if source_path.exists():previous.update(core.load_json(source_path))
    usable,_=display_catalog(active['raw_catalog'])
    from .config_store import print_only
    saved_settings,saved_layout=stamp_items(print_only(previous),active['settings']['print_layout'],print_only(candidate),layout,usable,preserve_dates)
    updated=build(active['raw_catalog'],saved_settings,saved_layout,active['source'])
    targets=[(Path(settings_path) if settings_path is not None else core.CONFIG,print_only(saved_settings)),
             (Path(layout_path) if layout_path is not None else ls.PATH,saved_layout),
             (Path(cache_path) if cache_path is not None else PATH,updated)]
    staged=[];committed=[]
    try:
        for target,value in targets:
            target.parent.mkdir(parents=True,exist_ok=True)
            before=target.read_bytes() if target.exists() else None
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=target.parent,suffix='.tmp',delete=False) as f:
                json.dump(value,f,ensure_ascii=False,indent=2);staged.append((target,Path(f.name),before))
        for target,temp,before in staged:
            os.replace(temp,target);committed.append((target,before))
    except OSError:
        for target,before in reversed(committed):
            if before is None:target.unlink(missing_ok=True)
            else:write(json.loads(before.decode('utf-8-sig')),target)
        raise
    finally:
        for _,temp,_ in staged:temp.unlink(missing_ok=True)
    candidate.update(saved_settings);layout.update(saved_layout)
    return updated
