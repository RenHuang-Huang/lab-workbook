"""Modification dates reflect user saves, never cache loads or upgrades."""
import copy
import datetime as dt

META = {'updated_at', 'item_updated_at'}


def now():
    return dt.datetime.now().astimezone().isoformat(timespec='seconds')


def content(value):
    return {k:v for k,v in value.items() if k not in META}


def stamp_file(before, after, stamp=None):
    result = copy.deepcopy(after)
    result['updated_at'] = (stamp or now()) if content(before) != content(after) else before.get('updated_at')
    return result


def display(value):
    if not value:return ''
    try:return dt.datetime.fromisoformat(value).astimezone().strftime('%Y-%m-%d %H:%M:%S')
    except (TypeError,ValueError):return ''


def latest(*values):
    return max((v for v in values if display(v)),key=lambda v:dt.datetime.fromisoformat(v).astimezone(),default=None)


def validate(value):
    stamp=value.get('updated_at');dates=value.get('item_updated_at',{})
    if not isinstance(dates,dict):raise ValueError('項目最後更新日期格式不正確。')
    for key,date in [('updated_at',stamp),*dates.items()]:
        if not isinstance(key,str) or date is not None and (not isinstance(date,str) or not display(date)):
            raise ValueError('設定最後更新日期格式不正確。')


def stamp_items(old_settings, old_layout, settings, layout, catalog, preserve_dates=False):
    from .catalog_settings import records
    fields=('label','zone','print_zone','machine_group','print_state','print_mode','subregion','position','position_mode','code_color','color_display')
    def states(s,l):
        result={}
        for row in records(catalog,s,l):
            result.setdefault(row['key'],set()).add(tuple(str(row.get(k,'')) for k in fields))
        for key in set(s.get('rules',{}))|set(l.get('placements',{}))|set(l.get('code_colors',{})):
            if key not in result:
                result[key]=(s.get('rules',{}).get(key),l.get('placements',{}).get(key),l.get('code_colors',{}).get(key),
                    [r for r in l.get('rules',[]) if key in r.get('codes',[])])
        from .panel_children import key as child_key
        for panel,children in l.get('panel_children',{}).items():
            result[panel]=[result.get(panel),children]
            for code,enabled in children.items():result[child_key(panel,code)]=enabled
        return result
    before=states(old_settings,old_layout);after=states(settings,layout);stamp=now()
    result=stamp_file(old_layout,layout,stamp);dates=copy.deepcopy(old_layout.get('item_updated_at',{}))
    changed={key for key in before.keys()|after.keys() if before.get(key)!=after.get(key)}
    imported=layout.get('item_updated_at',{}) if preserve_dates else {}
    for key in changed:dates[key]=imported.get(key) or stamp
    if preserve_dates:
        dates.update({key:value for key,value in imported.items() if value and key in after})
    result['item_updated_at']=dates
    if changed:result['updated_at']=stamp
    return stamp_file(old_settings,settings,stamp),result
