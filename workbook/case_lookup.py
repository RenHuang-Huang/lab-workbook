"""Read-only local case lookup. Results stay separate for every original order."""
import copy
import datetime as dt
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from .core import load_json, make_rows, sort_work
from .merge_settings import work_number

RESULT_FIELDS = (('LCHK_VALUE', '檢驗值'), ('LCHK_VALUE2', '值 2'),
                 ('LCHK_VALUE3', '值 3'), ('LCHK_RESULT', '結果文字'))


def validate_query(day, number):
    try:
        day = dt.date.fromisoformat(str(day)).isoformat()
        if day == '9999-12-31':
            raise ValueError
    except ValueError:
        raise ValueError('請選擇有效的工作日期。') from None
    number = str(number).strip()
    if not number or len(number) > 40 or any(ord(c) < 32 for c in number):
        raise ValueError('請輸入工作號，最多 40 個字元。')
    return day, number


def read_case(database, day, number):
    """Use the existing ACE/bitness fallback; never write clinical data to logs."""
    from .access_runtime import read_bridge
    day, number = validate_query(day, number)
    database = Path(database).resolve()
    if not database.is_file():
        raise ValueError('找不到 Access 檔案，請到系統設定確認資料庫路徑。')
    before = (database.stat().st_size, database.stat().st_mtime_ns)
    with tempfile.TemporaryDirectory(prefix='lab_case_') as folder:
        target = Path(folder)/'local.json'
        read_bridge(database, 'access_bridge.ps1',
                    ['-Date', day, '-CaseWorkNumber', number, '-Output', str(target)], 180)
        if not target.exists():
            raise ValueError('病例查詢未取得資料，請重新測試資料庫連線。')
        data = load_json(target)
    if before != (database.stat().st_size, database.stat().st_mtime_ns):
        raise ValueError('查詢期間資料庫有變動，請稍後重查，以免顯示不同時間的資料。')
    if data.get('lookup_only') is not True or data.get('date') != day:
        raise ValueError('病例查詢元件版本不符，請完整更新程式後重試。')
    return data


def text(value):
    return '' if value is None else str(value).strip()


def source_key(value):
    return (value.get('LCHK_DEPT') or '', value['LCHK_WORKNO'])


def result_text(detail):
    values = []
    for key, label in RESULT_FIELDS:
        value = text(detail.get(key))
        if value:
            values.append(value if key == 'LCHK_VALUE' else f'{label}：{value}')
    return '；'.join(values) or '未填值'


def build_result(data, number, settings, layout):
    """Hierarchy uses dictionary membership, never assumes historical parent keys.

    A shared member can appear under several panels, labelled as shared; counts
    are of original detail records. Missing dictionary members have no result.
    Exact clinic definitions take precedence, then 9999, as in make_rows().
    """
    from .catalog_settings import records
    _, number = validate_query(data['date'], number)
    headers = {source_key(h): h for h in data['headers']}
    hits = {key for key in headers if work_number(key[1]) == work_number(number)}
    if not hits:
        return dict(groups=[], order_count=0, matched_count=0, item_count=0, panel_count=0)
    effective = dict(copy.deepcopy(settings), layout=layout, order_mode='merge')
    # Reuse actual export grouping, including blank identity and work exclusions.
    grouped = make_rows(data, effective)
    selected = [row for row in grouped if hits & {
        (s['department'], s['workno']) for s in row['source_orders']}]
    definitions = records(data, settings, layout)
    single_rules = {r['code']: r for r in definitions if r['kind'] == '單項'}
    panel_rules = defaultdict(list)
    for rule in definitions:
        if rule['kind'] == '套組':
            panel_rules[rule['code']].append(rule)
    members = defaultdict(list)
    for member in data.get('set_members', []):
        uid = member.get('LCS_UNIKEY')
        if uid is not None and text(uid):
            members[str(uid)].append(member)
    for entries in members.values():
        entries.sort(key=lambda m: sort_work(text(m.get('LCS_SERIAL'))))
    details = defaultdict(list)
    for detail in data['details']:
        details[source_key(detail)].append(detail)
    hospitals = {h['HOS_ID']: h.get('HOS_NAME') or h['HOS_ID'] for h in data['hospitals']}

    def item_node(detail, rule, kind='單項', status='已登錄'):
        code = text(detail.get('LCHK_ITEM'))
        values = [(label, text(detail.get(key))) for key, label in RESULT_FIELDS]
        return dict(kind=kind, code=code, name=rule.get('name') or code,
                    zone=rule.get('zone', '待設定'), label=rule.get('label', ''),
                    print_state=rule.get('print_state', '待設定'),
                    subregion=rule.get('subregion_display', ''),
                    result=result_text(detail), unit=text(detail.get('LCHK_UNIT')),
                    status=status, values=values, children=[],
                    item_serial=text(detail.get('LCHK_ITEMSER')))

    output = dict(groups=[], order_count=0, matched_count=len(hits), item_count=0, panel_count=0)
    for group in selected:
        orders = []
        for source in group['source_orders']:
            key = (source['department'], source['workno'])
            header = headers[key]; local = details[key]
            singles = [d for d in local if d.get('LCHK_ITEMTYPE') != 'G']
            by_code = defaultdict(list)
            for single in singles:
                by_code[text(single['LCHK_ITEM'])].append(single)
            panels = []
            for d in local:
                if d.get('LCHK_ITEMTYPE') != 'G':
                    continue
                candidates = panel_rules[text(d['LCHK_ITEM'])]
                exact = [r for r in candidates if r.get('clinic_code') == header.get('LCHK_SOURCE')]
                common = [r for r in candidates if r.get('clinic_code') == '9999']
                options = exact or common or candidates
                rule = options[0] if len(options) == 1 else {}
                uid = rule.get('definition_id')
                known = uid is not None and bool(text(uid))
                panel_members = members[str(uid)] if known else []
                panels.append((d, rule, known, panel_members))
            shared = Counter(code for _, _, _, entries in panels
                             for code in {text(m['LCS_ITEM']) for m in entries})
            nodes = []; assigned = set()
            for d, rule, known, entries in panels:
                node = item_node(d, rule, '套組')
                present = 0
                for member in entries:
                    code = text(member['LCS_ITEM']); member_rule = single_rules.get(code, {})
                    actual = by_code.get(code, [])
                    for detail in actual:
                        status = '同單共用子項' if shared[code] > 1 else '已登錄'
                        if detail.get('LCHK_ITEMTYPE') != 'I':
                            status += '；來源類型待核對'
                        child = item_node(detail, member_rule,
                            status=status)
                        node['children'].append(child); assigned.add(id(detail))
                    if actual:
                        present += 1
                    else:
                        child = item_node({'LCHK_ITEM': code}, member_rule, status='當單未登錄')
                        child['result'] = '—';node['children'].append(child)
                node['status'] = f'已登錄 {present}/{len(entries)} 子項' if known else '套組定義待核對'
                nodes.append(node)
            for detail in singles:
                if id(detail) not in assigned:
                    kind = text(detail.get('LCHK_ITEMTYPE'))
                    nodes.append(item_node(detail, single_rules.get(text(detail['LCHK_ITEM']), {}),
                        status='已登錄' if kind == 'I' else '來源類型待核對'))
            orders.append(dict(department=key[0], workno=key[1], matched=key in hits,
                clinic=hospitals.get(header.get('LCHK_SOURCE'), header.get('LCHK_SOURCE') or '未指定'),
                name=text(header.get('LCHK_PATNAME')), chart=text(header.get('CHART_NUMBER')),
                order_date=text(header.get('LCHK_INDATE'))[:10] or data['date'],
                visit_date=text(header.get('LCHK_OPDDATE'))[:10], nodes=nodes,
                item_count=len(singles), panel_count=len(panels)))
            output['item_count'] += len(singles);output['panel_count'] += len(panels)
        output['groups'].append(dict(orders=orders, merged=len(orders) > 1,
            excluded=bool(group.get('merge_excluded'))))
        output['order_count'] += len(orders)
    return output
