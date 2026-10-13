"""Retire synthetic PRINT keys; transfer settings only to proven database panels."""
import copy,re
from collections import defaultdict
from . import layout_settings as ls,subregions as sr
from .core import CBC_DETAIL_CODES,STOOL_DETAIL_CODES


def strip_generated(layout):
    result=copy.deepcopy(layout);result['version']=3;rules=[]
    for rule in result['rules']:
        prior=list(rule['codes']);rule['codes']=[c for c in prior if not str(c).startswith('PRINT:')]
        if prior and not rule['codes'] and all(str(c).startswith('PRINT:') for c in prior):continue
        rules.append(rule)
    result['rules']=rules
    result['placements']={k:v for k,v in result.get('placements',{}).items() if not k.startswith('PRINT:')}
    return result


def transfer(layout,catalog):
    """Exact member-set families and established LFT/SMA IDs, not fuzzy names.

    A user-authored G rule or non-default G placement wins over a legacy alias.
    All clinic variants of a code must agree. No order is inferred or added.
    """
    result=strip_generated(layout);audit=[]
    if layout.get('source_panels_migrated'):return result,audit
    result['source_panels_migrated']=True
    members=defaultdict(set);variants=defaultdict(list)
    known={str(i['LCI_ID']) for i in catalog.get('items',[]) if i.get('LCI_ID')}
    for m in catalog.get('set_members',[]):members[m.get('LCS_UNIKEY')].add(m.get('LCS_ITEM'))
    standard={'B02','B04','B10','B24','B38','B39','B40','B43'}
    for p in catalog.get('sets',[]):
        code=str(p.get('LCS_ID') or '');codes=members[p.get('LCS_UNIKEY')];original=None
        if not code:continue
        if codes and all(c in known for c in codes):
            if codes==standard:original='CBC'
            elif len(codes)>=4 and codes<=CBC_DETAIL_CODES:original=f'CBC({len(codes)})'
            elif len(codes)>=5 and all(re.fullmatch(r'U\d{2}',c) for c in codes):original=f'UR{len(codes)}'
            elif codes==STOOL_DETAIL_CODES:original='Stool'
            elif code in ('0080','00052'):original={'0080':'LFT','00052':'SMA'}[code]
        variants[code].append(original)
    definitions=ls.generated_definitions(catalog);match_rule=ls.matcher(layout)
    for code,originals in variants.items():
        if None in originals or len(set(originals))!=1:continue
        original=originals[0];key='G:'+code;old_key='PRINT:'+original
        if original not in definitions:continue
        if any(key in r['codes'] for r in result['rules']):
            audit.append(dict(code=code,original=old_key,status='保留既有套組規則'));continue
        current=result['placements'].get(key)
        if current is not None and current!=dict(print_enabled=False,subregion='A',position=None):
            audit.append(dict(code=code,original=old_key,status='保留既有套組位置／開關'));continue
        old=match_rule({'LCI_ID':old_key});label,zone,_=definitions[original]
        if old:label,zone=old['label'],old['zone']
        fallback=sr.default_placement(dict(kind='套組',label=label,zone=zone,machine_group=None))
        placement=copy.deepcopy(sr.placement(layout,old_key,fallback))
        result['rules'].append(dict(label=label,zone=zone,codes=[key],aliases=[],enabled=True,source='由既有列印簡稱移至資料庫套組；'+old_key))
        result['placements'][key]=placement
        audit.append(dict(code=code,original=old_key,label=label,zone=zone,status='已移至資料庫套組'))
    ls.validate(result);return result,audit
