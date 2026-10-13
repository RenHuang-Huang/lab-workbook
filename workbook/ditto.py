"""Local-only comparison; retain full source rows and emit no identity diagnostics."""
from . import subregions as sr
from .errors import LayoutCapacityError

SYMBOL='〃'


def is_adult(item):
    return str(item.get('label','')).strip()=='@'


def bio_signature(row,layout,keep_adult=True):
    items=[item for item in row['zones']['bio'] if not (keep_adult and is_adult(item))]
    if not items or any(i.get('machines') or i.get('machine') for i in items):return None
    try:groups=sr.arrange(items,'生化／糞便',layout)
    except LayoutCapacityError:return None
    return tuple((g['column'],tuple((position,i.get('key'),i['label'],i.get('color'),tuple(sorted(i.get('codes',[]))),bool(i.get('panel')))
                                  for position,i in g['entries'])) for g in groups)


def patient_key(row):
    # The boolean prevents default placeholder names from identifying a patient.
    if not row.get('patient_identity_present'):return None
    parts=tuple(str(row.get(k) or '').strip() for k in ('clinic_code','chart_number','name'))
    return parts if all(parts) else None


def plan(slots,settings,layout,page_starts=None):
    out=[];previous=None;previous_bio=None
    page_starts=set(range(0,len(slots),20)) if page_starts is None else set(page_starts)
    for index,row in enumerate(slots):
        if index in page_starts:previous=None;previous_bio=None
        flags={'bio':False,'patient':False}
        if row is None:
            previous=None;previous_bio=None;out.append(flags);continue
        signature=bio_signature(row,layout,settings.get('ditto_keep_adult',True)) if settings.get('ditto_bio',True) else None
        if previous is not None:
            flags['bio']=signature is not None and signature==previous_bio
            key=patient_key(row)
            flags['patient']=bool(settings.get('ditto_patient',True) and key is not None and key==patient_key(previous))
            if flags['bio'] or flags['patient']:
                flags['reference_workno']=previous['workno'];flags['reference_department']=previous['department']
        out.append(flags);previous=row;previous_bio=signature
    return out


def patient_display(row,enabled):
    if enabled:return SYMBOL,'',row.get('insurance_label') or ''
    sex={'1':'男','2':'女','M':'男','F':'女'}.get(row['sex'],row['sex'])
    return row['name'],sex,row.get('insurance_label') or row.get('chart_number') or ''
