"""Local-only daily order grouping. Never log patient matching keys."""
import copy
from collections import defaultdict

def merge_rows(data,settings):
    from .core import make_rows,sort_work
    from .merge_settings import exclusions,work_number
    excluded=exclusions(settings)
    split_settings=dict(settings,order_mode='split')
    originals=make_rows(data,split_settings)  # Validate source keys before grouping.
    headers={(h.get('LCHK_DEPT') or '',h['LCHK_WORKNO']):h for h in data['headers']}
    groups={};order=[]
    for row in originals:
        source=(row['department'],row['workno']);h=headers[source]
        clinic=str(h.get('LCHK_SOURCE') or '').strip()
        chart=str(h.get('CHART_NUMBER') or '').strip()
        name=str(h.get('LCHK_PATNAME') or '').strip()
        day=str(h.get('LCHK_INDATE') or data['date'])[:10]
        # Missing identity fields must never group unrelated/insurance patients.
        key=('patient',day,clinic,chart,name) if clinic and chart and name and work_number(row['workno']) not in excluded else ('single',*source)
        if key not in groups:groups[key]=[];order.append(key)
        groups[key].append(row)
    raw_details=defaultdict(list)
    for d in data['details']:raw_details[(d.get('LCHK_DEPT') or '',d['LCHK_WORKNO'])].append(d)
    merged=dict(data,headers=[],details=[],adult_health=[])
    provenance={}
    for group in (groups[key] for key in order):
        group=sorted(group,key=lambda r:(sort_work(r['workno']),r['department']))
        first=group[0];target=(first['department'],first['workno'])
        h=copy.deepcopy(headers[target]);merged['headers'].append(h)
        insurance=list(dict.fromkeys(r['insurance_label'] for r in group if r['insurance_label']))
        h['INSURANCE_LABEL']='／'.join(insurance)
        by_item={};adult_codes=set()
        for row in group:
            if row.get('adult_health_flag'):
                for panel in row.get('verified_panels',[]):
                    if (panel.get('name') or '').strip().startswith(('成健','不報成健')):adult_codes.update(panel['members'])
            source=(row['department'],row['workno'])
            for d in raw_details[source]:
                key=(d['LCHK_ITEMTYPE'],d['LCHK_ITEM'])
                if len(group)==1:
                    merged['details'].append(copy.deepcopy(d));continue
                if key not in by_item:
                    item=copy.deepcopy(d);item.update(LCHK_DEPT=target[0],LCHK_WORKNO=target[1],source_orders=[])
                    by_item[key]=item;merged['details'].append(item)
                by_item[key]['source_orders'].append({'department':source[0],'workno':source[1],'item_serial':d.get('LCHK_ITEMSER')})
        if any(r.get('adult_health_flag') for r in group):merged['adult_health'].append(dict(LCHK_DEPT=target[0],LCHK_WORKNO=target[1]))
        provenance[target]=(group,sorted(adult_codes))
    result=make_rows(merged,split_settings)
    for row in result:
        group,adult_codes=provenance[(row['department'],row['workno'])]
        row['order_mode']='merge';row['merged_count']=len(group)
        row['merge_excluded']=work_number(row['workno']) in excluded
        row['source_orders']=[{'department':r['department'],'workno':r['workno'],
                               'visit_date':r.get('visit_date'),'order_date':r.get('order_date')} for r in group]
        row['visit_dates']=list(dict.fromkeys(day for r in group for day in r.get('visit_dates',[])))
        row['original_source_items']=[{'department':r['department'],'workno':r['workno'],'items':copy.deepcopy(r['source_items'])} for r in group]
        row['adult_source_orders']=[{'department':r['department'],'workno':r['workno']} for r in group if r.get('adult_health_flag')]
        if len(group)>1:row['adult_compact_codes']=adult_codes
        numbers=list(dict.fromkeys(str(int(r['workno'])) if r['workno'].isdigit() else r['workno'] for r in group))
        row['workno_display']='、'.join(numbers) if settings.get('merge_workno_style','all')=='all' else numbers[0]
        if len(numbers)>1 and settings.get('merge_workno_style','all')=='all':row['workno_lines']=numbers
    return result
