"""Build visible tokens independently from the immutable source order details."""
import copy,re
from . import layout_settings as ls,subregions as sr
from .print_style import item_color


def prepare(rows,settings,layout):
    from .handwritten import SHORT,clinic_label
    from .font_settings import sizes
    fonts=sizes(settings)
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
        covered={code for panel,_ in printed_panels for code in panel['present_members']}
        cross_panels=[(panel,sr.ZONE_KEYS[rule['zone']]) for panel,rule in printed_panels
            if sr.placement(layout,'G:'+panel['code'],{}).get('print_mode')=='cross_zone']
        cross_codes=set()
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
            numbered_member=code in covered and group in counts
            cross_member=any(code in panel['present_members'] and zone!=destination for panel,destination in cross_panels)
            if cross_member:cross_codes.add(code)
            if code in covered and not numbered_member and not cross_member:
                entry.update(display='',covered_by='登錄套組取代子項');continue
            if not enabled and not numbered_member:
                entry.update(display='',covered_by='使用者設定不列印');continue
            if numbered_member:entry['print_reason']='已列印套組的流水號子項，獨立列印'
            if cross_member:
                item['cross_zone_member']=True
                entry['print_reason']='套組設定跨區列印子項，保留子項原區域'
            # A malformed source item type is still visible, just as in previous releases.
            if source.get('type','I')!='I':item['label']=f"[{source.get('type')}:{code}] "+shown
            source_key=(code,source.get('type','I'))
            if source_key not in seen_items:tokens.append(item);seen_items.add(source_key)
        for panel,rule in printed_panels:
            members=set(panel['present_members'])
            numbered={code for code in members if settings.get('rules',{}).get(code,{}).get('group','routine') in counts}
            codes=members-numbered-cross_codes
            item=token('G:'+panel['code'],rule['label'],sr.ZONE_KEYS[rule['zone']],sorted(codes),[],panel['name'],True)
            item['panel']=True;tokens.append(item)
            row['panel_display'].append(dict(code=panel['code'],label=rule['label'],zone=item['zone'],
                covered_codes=sorted(codes),numbered_member_codes=sorted(numbered),
                cross_zone_member_codes=sorted(members & cross_codes),missing_members=panel['missing_members']))
            for entry in accounting:
                if entry['code'] in codes:entry.update(display=rule['label'],zone=item['zone'],covered_by='登錄套組 '+panel['code']+' 取代子項；不增補缺項')
        adult=set(row.get('adult_compact_codes',[]))
        if 'adult_compact_codes' not in row:
            adult={c for p in row.get('verified_panels',[]) if (p.get('name') or '').strip().startswith(('成健','不報成健')) for c in p['members']}
        if row.get('adult_health_flag') and settings.get('compact_adult_health',True):
            fold=[t for t in tokens if not t['configured'] and not t['machines'] and not t.get('cross_zone_member') and set(t['codes'])<=adult]
            for t in fold:
                tokens.remove(t)
                for a in accounting:
                    if a['code'] in t['codes']:a.update(display='@',covered_by='當筆IC旗標＋已驗證成健套組成員')
        # The established urine-result grouping remains unchanged.
        labels={t['original_label'] for t in tokens if t['zone']=='other'};fold_labels=set()
        if {'mab','U-cre','U-ACR'}<=labels:fold_labels|={'U-cre','U-ACR'}
        if {'UTP','U-cre','U-PCR'}<=labels:fold_labels|={'U-cre','U-PCR'}
        for t in list(tokens):
            if t['zone']=='other' and t['original_label'] in fold_labels and not t.get('panel') and not t['machines'] and not t.get('cross_zone_member'):
                tokens.remove(t)
                for a in accounting:
                    if a['code'] in t['codes']:a['covered_by']='mab／UTP完整尿液組合'
        # Unresolved group-only orders must not disappear when no dictionary match exists.
        for label in row.get('routine','').split(' / '):
            if label.startswith('套組待核:') and not any(label=='套組待核:'+p['code'] for p,_ in printed_panels):
                tokens.append(token(label,label,'bio',[]))
        # A registered panel explicitly printed as @ already supplies this mark.
        # Keep its panel/member provenance; do not add a second flag-only glyph.
        if row.get('adult_health_flag') and not any(t.get('panel') and t['zone']=='bio' and t['label']=='@' for t in tokens):
            adult_token=token('@','@','bio',[])
            adult_token['font_size']=fonts['adult_health']
            adult_token['placement']=dict(print_enabled=True,subregion='A',position=1)
            tokens.insert(0,adult_token)
        zones={key:[] for key in reverse}
        for item in tokens:zones[item['zone']].append(item)
        for group in counts:
            if any(group in t['machines'] for t in tokens):counts[group]+=1;row[group+'_seq']=counts[group]
            else:row[group+'_seq']=None
        row.update(zones=zones,display_accounting=accounting,clinic_print=clinic_label(row['clinic']))
    return output
