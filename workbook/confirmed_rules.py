"""Apply a locally saved, explicitly confirmed dictionary review, never clinical data."""
import copy
from . import catalog_cache as cc, catalog_settings as cs, print_style, layout_settings as ls

RED_ALIASES = ('CBC(7)', 'CBC(8)', 'CBC(8怡)', 'Plt.')
# Decisions made by the user for this review; not general-purpose name inference.
PANEL_ZONES = {'002': '生化／糞便', '000003': '生化／糞便'}
SCHEMAS = {
    '套組表': ('sets', 'LCS_ID', {'項目名稱': 'LCS_NAME', '健保代碼': 'LCS_NHICODE',
        '適用院所代碼': 'LCS_HOSPITAL', '套組定義識別碼': 'LCS_UNIKEY'}),
    '單項表': ('items', 'LCI_ID', {'項目名稱': 'LCI_NAME', '健保代碼': 'LCI_NHICODE'}),
    '診所表': ('hospitals', 'HOS_ID', {'診所名稱': 'HOS_NAME'}),
}


def text(value):
    return str(value or '').strip()


def approved(row):
    return text(row.get('確認狀態')) == '已確認' or row.get('核對') in (True, 'TRUE', '☑')


def plan(snapshot, catalog):
    """Validate every approved row first. Source identity must match exactly."""
    result = []; counts = {}; seen = set()
    for tab, (source, code_field, identity) in SCHEMAS.items():
        values = snapshot['sheets'][tab]['values']
        headers = values[0]
        required = {'確認狀態', *identity, '診所代碼' if source == 'hospitals' else '系統代碼'}
        required |= {'列印簡稱'} if source == 'hospitals' else {'列印區域', '列印代碼', '子區域', '位置',
            '是否依套組名列印' if source == 'sets' else '是否列印'}
        if source == 'items': required.add('流水號分組')
        if len(headers) != len(set(headers)) or not required <= set(headers):
            raise ValueError(tab + ' 欄位不完整或重複。')
        counts[tab] = dict(approved=0, skipped=0)
        for line, cells in enumerate(values[1:], 2):
            row = dict(zip(headers, cells))
            if not any(text(v) for v in cells): continue
            if not approved(row):
                counts[tab]['skipped'] += 1
                continue
            code = text(row.get('診所代碼' if source == 'hospitals' else '系統代碼'))
            key = ('G:' if source == 'sets' else 'H:' if source == 'hospitals' else '') + code
            matches = [v for v in catalog[source] if text(v.get(code_field)) == code]
            if not code or len(matches) != 1 or any(text(row.get(k)) != text(matches[0].get(v)) for k, v in identity.items()):
                raise ValueError(f'{tab} 第 {line} 列：來源代碼／定義不符，未更新任何設定。')
            if key in seen: raise ValueError(f'{tab} 第 {line} 列：重複來源代碼。')
            seen.add(key)
            value = dict(key=key, sheet=tab, row=line, code=code)
            if source == 'hospitals':
                value['label'] = text(row.get('列印簡稱'))
                if not value['label']: raise ValueError(f'{tab} 第 {line} 列：診所簡稱空白。')
            else:
                enabled = row.get('是否依套組名列印' if source == 'sets' else '是否列印')
                if enabled not in ('是', '否'): raise ValueError(f'{tab} 第 {line} 列：是否列印格式不正確。')
                zone = text(row.get('列印區域')); label = text(row.get('列印代碼'))
                if source == 'sets' and enabled == '是' and zone == cs.MEMBER_ZONE and code in PANEL_ZONES:
                    zone = PANEL_ZONES[code]
                if zone not in ls.ZONES and not (source == 'sets' and zone == cs.MEMBER_ZONE and enabled == '否' and not label):
                    raise ValueError(f'{tab} 第 {line} 列：列印區域未確定。')
                if zone != cs.MEMBER_ZONE and not label: raise ValueError(f'{tab} 第 {line} 列：列印代碼空白。')
                region = text(row.get('子區域'))
                if region in ('', '自動'): region = ''
                if region not in ('', *('ABCDEF' if zone == '生化／糞便' else 'ABCDEFGHI')):
                    raise ValueError(f'{tab} 第 {line} 列：子區域不正確。')
                position = text(row.get('位置'))
                if position in ('', '自動'): position = None
                elif position.isascii() and position.isdigit() and 1 <= int(position) <= 99: position = int(position)
                else: raise ValueError(f'{tab} 第 {line} 列：排列順位不正確。')
                group = None
                if source == 'items':
                    group = next((k for k, v in cs.MACHINE_NAMES.items() if v == row.get('流水號分組')), None)
                    if group is None: raise ValueError(f'{tab} 第 {line} 列：流水號分組不正確。')
                value.update(label=label, zone=zone, group=group, print_enabled=enabled == '是',
                    subregion=region, position=position, position_mode='order' if position is not None else 'slot')
            result.append(value); counts[tab]['approved'] += 1
    return result, counts


def apply(snapshot, settings, layout, document):
    """Pure operation: returns a validated bundle and row-level audit, without I/O."""
    raw = document['raw_catalog']; changes, counts = plan(snapshot, raw)
    catalog, _ = cc.display_catalog(raw)
    before = {r['key']: r for r in cs.records(catalog, settings, layout)}
    candidate = copy.deepcopy(settings); updated = copy.deepcopy(layout)
    for value in changes:
        if value['sheet'] == '診所表':
            updated.setdefault('clinic_aliases', {})[value['code']] = value['label']
        else:
            candidate, updated = cs.edit_item(candidate, updated, before[value['key']],
                **{k: value[k] for k in ('label', 'zone', 'group', 'print_enabled', 'subregion', 'position', 'position_mode')})
    rules = print_style.color_rules(candidate)
    matching = next((r for r in rules if r['enabled'] and r['zone'] == 'CBC／尿液' and
        r['color'].upper() == '#B02631' and 'CBC' in r['codes']), None)
    if matching is not None:
        matching['codes'] += [v for v in RED_ALIASES if v not in matching['codes']]
    candidate['print_color_rules'] = rules
    if any(print_style.matching_color(candidate, v, 'CBC／尿液') != '#B02631' for v in RED_ALIASES):
        candidate['print_color_rules'].insert(0, dict(codes=list(RED_ALIASES), zone='CBC／尿液', color='#B02631', enabled=True))
    ls.validate(updated); print_style.validate_settings(candidate)
    rebuilt = cc.build(raw, candidate, updated, document.get('source', {}))
    after = {r['key']: r for r in rebuilt['records']}
    fields = ('label', 'zone', 'machine_group', 'print_enabled', 'subregion', 'position', 'position_mode', 'color_display')
    audit = []
    for value in changes:
        if value['sheet'] == '診所表':
            original = layout.get('clinic_aliases', {}).get(value['code'])
            if original is None:
                h = next(h for h in raw['hospitals'] if text(h['HOS_ID']) == value['code'])
                original = text(h['HOS_NAME']).replace('診所', '').strip()
            diff = {'label': {'before': original, 'after': value['label']}} if original != value['label'] else {}
        else:
            diff = {k: dict(before=before[value['key']].get(k), after=after[value['key']].get(k))
                for k in fields if before[value['key']].get(k) != after[value['key']].get(k)}
        audit.append(dict(sheet=value['sheet'], row=value['row'], key=value['key'], differences=diff))
    return candidate, updated, rebuilt, dict(source_url=snapshot['url'], counts=counts,
        approved_rows=len(changes), changed_rows=sum(bool(r['differences']) for r in audit), rows=audit,
        decisions={'positions': '排列順位；生化三列滿後往後補位', 'panel_zones': PANEL_ZONES,
            'red_aliases': list(RED_ALIASES)}, clinical_data_read=False)
