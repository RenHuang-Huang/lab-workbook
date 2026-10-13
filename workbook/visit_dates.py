"""Calendar-date comparison for the red handwritten visit-date annotation."""
import datetime as dt
import re

def calendar_date(value):
    if value is None or value=='':return None
    if isinstance(value,dt.datetime):return value.date()
    if isinstance(value,dt.date):return value
    text=str(value).strip()
    # Older local progress snapshots may use Windows PowerShell JSON dates.
    match=re.fullmatch(r'/Date\((-?\d+)([+-]\d{4})?\)/',text)
    if match:
        value=dt.datetime.fromtimestamp(int(match[1])/1000,dt.timezone.utc)
        if match[2]:
            offset=match[2];minutes=int(offset[1:3])*60+int(offset[3:])
            value=value.astimezone(dt.timezone(dt.timedelta(minutes=minutes if offset[0]=='+' else -minutes)))
        else:value=value.astimezone()
        return value.date()
    try:return dt.date.fromisoformat(text[:10])
    except ValueError:raise ValueError('就醫／開單日期格式無法辨識，請重新匯入資料') from None

def row_dates(header,work_date):
    visit=calendar_date(header.get('LCHK_OPDDATE'))
    if visit is None:return {'visit_date':None,'order_date':None,'visit_dates':[]}
    order=calendar_date(header.get('LCHK_INDATE') or work_date)
    return {'visit_date':visit.isoformat(),'order_date':order.isoformat() if order else None,
            'visit_dates':[visit.isoformat()] if order and visit!=order else []}
