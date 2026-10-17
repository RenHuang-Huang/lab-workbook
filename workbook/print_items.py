"""Build visible tokens independently from the immutable source order details."""
import copy,re
from . import layout_settings as ls,subregions as sr
from .print_style import item_color
from . import panel_children as pc


def prepare(rows,settings,layout):
    from .handwritten import SHORT,clinic_label
    output=copy.deepcopy(rows);counts={g:0 for g in ('e411','hba1c','mab')}
    match_rule=ls.matcher(layout)
    reverse={v:k for k,v in sr.ZONE_KEYS.items()}
    for row in output:
        tokens=[];accounting=[];row['panel_display']=[];printed_panels=[];seen_panels=set();seen_items=set()
        def token(key,label,zone,codes,machines=(),original=None,configured=False):
            fallback=sr.default_placement(dict(kind='單項',label=label,zone=reverse[zone],machine_group=next(iter(machines),None)))
            return dict(key=key,label=label,original_label=original or label,codes=list(codes),zone=zone,
                        machine=next(iter(machines),None),machines=list(machines),configured=configured,
                        color=item_color(layout,key,label,row,settings,reverse[zone],codes),
                        placement=copy.deepcopy(sr.placement(layout,key,fallback,reverse[zone])))
        # Ordered group codes are authoritative. Never infer a panel from matching singles.
        for code in row.get('unresolved_panels',[]):
            key='G:'+code;rule=match_rule({'LCI_ID':key})
            if sr.placement(layout,key,{'print_enabled':bool(rule)})['print_enabled']:
                raise ValueError('套組 '+code+' 的成員定義不明確，無法安全取代子項；請核對套組字典。')
        for panel in row.get('ordered_panels',[]):
            key='G:'+panel['code'];rule=match_rule({'LCI_ID':key})
            enabled=sr.placement(layout,key,{'print_enabled':bool(rule)})['print_enabled']
            if not enabled:continue
            if key in seen_panels:continue
            seen_panels.add(key)
            if not rule:raise ValueError('套組 '+panel['code']+' 已勾選列印，但尚未設定列印簡稱及區域。')
            printed_panels.append((panel,rule))
        parents={p['code']:p for p in row.get('ordered_panels',[])}
        printed={p['code']:rule for p,rule in printed_panels}
        transferred={};hidden={};shown_members={};visible_sources={}
        for source in row.get('source_items',[]):
            code=source['code'];group=settings.get('rules',{}).get(code,{}).get('group','routine')
            label=source['label'];rule=match_rule({'LCI_ID':code,'LCI_NAME':source.get('name',''),
                'LCI_NAMEC':source.get('namec',''),'LCI_NAMES':label})
            if rule:shown=rule['label'];zone=sr.ZONE_KEYS[rule['zone']]
            else:
                shown=SHORT.get(label,label)
                zone='e411' if group=='e411' else 'other' if group in ('hba1c','mab') or label in ('U-cre','U-ACR','UTP','U-PCR','HBeAg') else 'cbc' if code.startswith('B') or re.fullmatch(r'U\d{2}',code) else 'bio'
            item=token(code,shown,zone,[code],[group] if group in counts else [],label,bool(rule))
            enabled=sr.placement(layout,code,{'print_enabled':group!='aux'})['print_enabled']
            entry=dict(code=code,original=label,zone=zone,display=shown,covered_by=None)
            accounting.append(entry)
            parent=source.get('parent_panel','')
            if not source.get('parent_known'):
                if parents and layout.get('panel_children_version'):
                    raise ValueError('舊工作進度未包含套組來源，請重新從資料庫匯入當日資料後輸出。')
                # Compatibility for legacy snapshots before the panel settings migration.
                candidates=[p for p in parents.values() if code in p['present_members']]
                if len(candidates)==1:parent=candidates[0]['code']
            entry['parent_panel']=parent
            if parent in parents:
                enabled=pc.enabled(layout,'G:'+parent,dict(code=code,label=shown,zone=reverse[zone],machine_group=group,print_enabled=enabled))
                item['panel_member']=True
                if not enabled:
                    hidden.setdefault(parent,set()).add(code)
                    rule=printed.get(parent)
                    if rule and group in counts and pc.same_label(rule['label'],shown):
                        transferred.setdefault(parent,set()).add(group)
                        entry.update(display=rule['label'],zone=sr.ZONE_KEYS[rule['zone']],covered_by='流水號移至同代碼套組')
                    else:entry.update(display='',covered_by='本套組子項設定不列印')
                    continue
                shown_members.setdefault(parent,set()).add(code)
                entry['print_reason']='本套組子項設定列印'
            if not enabled:
                entry.update(display='',covered_by='使用者設定不列印');continue
            # A malformed source item type is still visible, just as in previous releases.
            if source.get('type','I')!='I':item['label']=f"[{source.get('type')}:{code}] "+shown
            source_key=(code,source.get('type','I'))
            visible_sources.setdefault(source_key,[]).append(source)
            if source_key not in seen_items:tokens.append(item);seen_items.add(source_key)
            elif item.get('panel_member'):
                next(t for t in tokens if t['key']==code)['panel_member']=True
        for item in tokens:
            sources=[s for (code,_),items in visible_sources.items() if code==item['key'] for s in items]
            item['color']=item_color(layout,item['key'],item['label'],dict(row,source_items=sources,original_source_items=[]),settings,reverse[item['zone']],item['codes'])
        for panel,rule in printed_panels:
            code=panel['code'];codes=hidden.get(code,set())
            machines=[g for g in counts if g in transferred.get(code,set())]
            item=token('G:'+code,rule['label'],sr.ZONE_KEYS[rule['zone']],sorted(codes),machines,panel['name'],True)
            item.update(panel=True,serial_on_label=True);tokens.append(item)
            row['panel_display'].append(dict(code=panel['code'],label=rule['label'],zone=item['zone'],
                covered_codes=sorted(codes),visible_member_codes=sorted(shown_members.get(code,set())),
                transferred_serial_groups=machines,missing_members=panel['missing_members']))
        # A transferred sequence belongs to the matching panel label even when
        # another visible member shares that machine group and is drawn first.
        serial_targets={}
        for item in tokens:
            if item.get('serial_on_label'):
                for group in item['machines']:serial_targets.setdefault(group,item['key'])
        for item in tokens:
            item['machines']=[g for g in item['machines'] if g not in serial_targets or serial_targets[g]==item['key']]
            item['machine']=next(iter(item['machines']),None)
        # IC metadata must not add @ or hide otherwise printable items. An @
        # label follows the same registered-panel/item visibility rules above.
        # The established urine-result grouping remains unchanged.
        labels={t['original_label'] for t in tokens if t['zone']=='other'};fold_labels=set()
        if {'mab','U-cre','U-ACR'}<=labels:fold_labels|={'U-cre','U-ACR'}
        if {'UTP','U-cre','U-PCR'}<=labels:fold_labels|={'U-cre','U-PCR'}
        for t in list(tokens):
            if t['zone']=='other' and t['original_label'] in fold_labels and not t.get('panel') and not t['machines'] and not t.get('panel_member'):
                tokens.remove(t)
                for a in accounting:
                    if a['code'] in t['codes']:a['covered_by']='mab／UTP完整尿液組合'
        # Unresolved group-only orders must not disappear when no dictionary match exists.
        for label in row.get('routine','').split(' / '):
            if label.startswith('套組待核:') and not any(label=='套組待核:'+p['code'] for p,_ in printed_panels):
                tokens.append(token(label,label,'bio',[]))
        zones={key:[] for key in reverse}
        for item in tokens:zones[item['zone']].append(item)
        for group in counts:
            if any(group in t['machines'] for t in tokens):counts[group]+=1;row[group+'_seq']=counts[group]
            else:row[group+'_seq']=None
        row.update(zones=zones,display_accounting=accounting,clinic_print=clinic_label(row['clinic']))
    return output
