"""Rolling three-year aggregate usage. No patient values enter this module."""
import csv
import datetime as dt
import tempfile
from collections import defaultdict
from pathlib import Path
from .core import load_json


def period(end):
    try:
        day=dt.date.fromisoformat(str(end));exclusive=day+dt.timedelta(days=1)
        if day.year<1903:raise ValueError
        try:start=exclusive.replace(year=exclusive.year-3)
        except ValueError:start=exclusive.replace(year=exclusive.year-3,day=28)
    except (ValueError,OverflowError):raise ValueError('請選擇有效的統計截至日期。') from None
    return start.isoformat(),day.isoformat()


def read_usage(database,end):
    from .access_runtime import read_bridge
    start,end=period(end);database=Path(database).resolve()
    if not database.is_file():raise ValueError('找不到 Access 檔案，請到系統設定確認資料庫路徑。')
    before=(database.stat().st_size,database.stat().st_mtime_ns)
    with tempfile.TemporaryDirectory(prefix='lab_usage_') as folder:
        out=Path(folder)/'aggregates.json'
        read_bridge(database,'access_bridge.ps1',['-UsageStatistics','-Date',end,'-StartDate',start,'-Output',str(out)],600)
        if not out.is_file():raise ValueError('統計程序未產生資料，請確認資料庫連線。')
        result=load_json(out)
    if before!=(database.stat().st_size,database.stat().st_mtime_ns):
        raise ValueError('統計期間資料庫有變動，請使用穩定備份或稍後重新整理。')
    if result.get('usage_statistics') is not True or result.get('start_date')!=start or result.get('end_date')!=end:
        raise ValueError('統計元件版本不符，請完整更新程式。')
    validate(result)
    return result


def validate(data):
    seen=set()
    for row in data['counts']:
        key=(row['kind'],row['code'])
        if key in seen or key[0] not in ('I','G') or not isinstance(key[1],str) or not key[1]:
            raise ValueError('使用統計的項目代碼格式不正確。')
        seen.add(key)
        for name in ('total_count','direct_count','uncertain_count'):
            if type(row[name]) is not int or row[name]<0:raise ValueError('使用次數格式不正確。')
        if not row['uncertain_count']<=row['direct_count']<=row['total_count']:
            raise ValueError('使用次數不一致，請重新整理。')


def classify(data,settings,layout,exclude_expanded=True):
    from .catalog_settings import records,MEMBER_ZONE
    from .catalog_cache import clean,display_catalog
    from .layout_settings import ZONES
    from .settings_history import display
    validate(data);catalog,_=display_catalog(clean(data['catalog']))
    configured=defaultdict(list)
    for row in records(catalog,settings,layout):configured[row['key']].append(row)
    rows=[]
    for count in data['counts']:
        kind='套組' if count['kind']=='G' else '單項';code=count['code']
        key=('G:' if kind=='套組' else '')+code;options=configured.get(key,[])
        rule=options[0] if options else {}
        direct=kind=='單項' and exclude_expanded
        frequency=count['direct_count'] if direct else count['total_count']
        if not frequency:continue
        rows.append(dict(key=key,kind=kind,code=code,
            name='／'.join(dict.fromkeys(r['name'] for r in options)) or '未在目前字典找到',
            nhi=rule.get('nhi',''),zone=rule.get('zone','待設定'),label=rule.get('label',''),
            print_state=rule.get('print_state','待設定'),count=frequency,total_count=count['total_count'],
            expanded_only=count['total_count']-count['direct_count'],uncertain_count=count['uncertain_count'],
            first_used=count['first_direct'] if direct else count['first_used'],
            last_used=count['last_direct'] if direct else count['last_used'],
            updated_display=display(layout.get('item_updated_at',{}).get(key)) or '尚無紀錄'))
    order={zone:i for i,zone in enumerate((*ZONES,MEMBER_ZONE,'','待設定'))}
    rows.sort(key=lambda r:(r['kind'],order.get(r['zone'],99),-r['count'],r['code']))
    return rows


def report(data,settings,layout,exclude_expanded=True):
    return dict(schema_version=1,generated_at=dt.datetime.now().astimezone().isoformat(timespec='seconds'),
        start_date=data['start_date'],end_date=data['end_date'],exclude_expanded=exclude_expanded,
        count_basis='同一張原始檢驗單內，同代碼最多計一次；不依工作簿併單去重。',
        exclusion_basis='僅排除同單 MKEY 明確對上 G 套組代碼的子項；關聯不明保留計數。',
        settings_updated_at=settings.get('updated_at'),layout_updated_at=layout.get('updated_at'),
        order_count=data['order_count'],unknown_detail_count=data['unknown_detail_count'],
        unresolved_detail_count=data['unresolved_detail_count'],rows=classify(data,settings,layout,exclude_expanded))


def export(path,document):
    """Explicit user export: aggregate rows and metadata only; Excel-safe text cells."""
    from .core import save_json
    path=Path(path)
    if path.suffix.lower()=='.json':save_json(path,document);return
    columns=[('kind','類型'),('code','來源代碼'),('name','項目名稱'),('zone','列印區域'),('label','列印代碼'),
        ('print_state','是否列印'),('count','使用次數'),('total_count','含展開總次數'),('expanded_only','僅套組展開次數'),
        ('uncertain_count','待核對次數'),('first_used','首次使用'),('last_used','最後使用'),('updated_display','設定最後更新')]
    def safe(value):
        if isinstance(value,str) and (value.lstrip().startswith(('=','+','-','@')) or value[:1] in ('\t','\r','\n')):return "'"+value
        return value
    import os
    temporary=None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8-sig',newline='',dir=path.parent,suffix='.tmp',delete=False) as stream:
            temporary=Path(stream.name);writer=csv.writer(stream)
            writer.writerow(['統計起日','統計迄日','排除套組展開',*[title for _,title in columns]])
            for row in document['rows']:
                writer.writerow([document['start_date'],document['end_date'],'是' if document['exclude_expanded'] else '否',*[safe(row[k]) for k,_ in columns]])
        os.replace(temporary,path)
    finally:
        if temporary:temporary.unlink(missing_ok=True)
