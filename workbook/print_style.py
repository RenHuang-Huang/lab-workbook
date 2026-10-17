"""Explicit PDF ink styles; a red label is not a superscript serial."""
from dataclasses import dataclass
import re

BLACK='#202830'
RED='#B02631'
MERGED='#7042A6'
BLUE='#215CAE'
PALETTE={'自動':'','黑色':BLACK,'紅色':RED,'藍色':'#215CAE','紫色':MERGED,'深綠色':'#246B45'}
ALL_ZONES='全部區域'
DITTO_ALIGN={'left':'置左','center':'置中','right':'置右'}
SERIAL_COLORS={'e411':RED,'hba1c':BLUE,'mab':RED}


def default_color_rules():
    return [dict(codes=['CBC','Plt','WBC','Hb'],zone='CBC／尿液',color=RED,enabled=True)]


def color_rules(settings):
    from .layout_settings import ZONES
    values=settings.get('print_color_rules',default_color_rules())
    if not isinstance(values,list):raise ValueError('列印代碼配色規則必須是清單。')
    result=[]
    for index,value in enumerate(values,1):
        if (not isinstance(value,dict) or type(value.get('enabled')) is not bool
                or value.get('zone') not in (ALL_ZONES,*ZONES)
                or not isinstance(value.get('codes'),list) or not value['codes']
                or any(not isinstance(code,str) or not code.strip() for code in value['codes'])):
            raise ValueError(f'配色規則第 {index} 列格式不正確，請填入列印代碼、區域及啟用狀態。')
        codes=[];seen=set()
        for code in value['codes']:
            code=code.strip()
            if code.casefold() not in seen:codes.append(code);seen.add(code.casefold())
        result.append(dict(codes=codes,zone=value['zone'],color=color(value.get('color')),enabled=value['enabled']))
    return result


def matching_color(settings,label,zone):
    for rule in color_rules(settings):
        if rule['enabled'] and rule['zone'] in (ALL_ZONES,zone) and label.strip().casefold() in {v.casefold() for v in rule['codes']}:
            return rule['color']
    return ''

@dataclass(frozen=True)
class Ink:
    color: str
    serial: bool=False
    font_size: float=14
    reference_size: float=14
    superscript: bool=False
    bold: bool=False


def serial_ink(group,settings,reference_size):
    return Ink(serial_colors(settings)[group],True,float(settings.get('serial_font_size',14)),
               reference_size,bool(settings.get('serial_superscript',False)))


def serial_colors(settings):
    values=settings.get('serial_colors',{})
    if not isinstance(values,dict):raise ValueError('流水號顏色設定格式不正確。')
    return {key:color(values.get(key,default)) for key,default in SERIAL_COLORS.items()}


def run_size(size,ink):
    return ink.font_size*min(1,size/max(.01,ink.reference_size)) if isinstance(ink,Ink) and ink.serial else size


def run_rise(size,ink):
    return run_size(size,ink)*.28 if isinstance(ink,Ink) and ink.serial and ink.superscript else 0


def measure_run(measure,value,size,ink):
    if isinstance(ink,Ink) and ink.bold:
        return measure(value,run_size(size,ink),bold=True)
    return measure(value,run_size(size,ink))


def run_height(runs,size):
    # Conservatively reserve taller serials and raised glyphs in every renderer.
    return max([size]+[run_size(size,ink)+2*run_rise(size,ink) for _,ink in runs])

def color(value):
    if not isinstance(value,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',value):
        raise ValueError('顏色請選擇色票或輸入 #RRGGBB（例如 #B02631）。')
    return value.upper()

def choice(value):
    return PALETTE.get(value,value)

def title(value):
    return next((k for k,v in PALETTE.items() if v==value),value)

def code_color(layout,key,label,settings=None,zone=None):
    matched=matching_color(settings or {},label,zone)
    explicit=layout.get('code_colors',{}).get(key)
    return matched or (color(explicit) if explicit else '')

def order_colors(settings):
    values=settings.get('merged_order_colors',[BLACK,BLUE,BLUE,BLUE])
    if not isinstance(values,list) or len(values)!=4:raise ValueError('併單配色需要第一、第二、第三及第四張起，共四個顏色。')
    return [color(value) for value in values]


def source_order_index(row,key,codes=()):
    """Use the earliest actual registration, never panel membership to guess origin."""
    from .core import sort_work
    def identity(source):return str(source.get('department') or ''),str(source.get('workno') or '')
    orders=sorted(row.get('source_orders',[]),key=lambda s:(sort_work(str(s['workno'])),str(s.get('department') or '')))
    ranks={identity(source):i for i,source in enumerate(orders)}
    origins=[]
    if key=='@':origins=row.get('adult_source_orders',[])
    elif key.startswith('G:'):
        origins=[o for p in row.get('ordered_panels',[]) if str(p['code'])==key[2:] for o in p.get('source_orders',[])]
    else:
        wanted=set(codes) or {key}
        origins=[o for item in row.get('source_items',[]) if item['code'] in wanted for o in item.get('source_orders',[])]
        # Saved progress from older versions may retain per-order items only.
        if not origins:
            origins=[o for o in row.get('original_source_items',[]) if any(item['code'] in wanted for item in o['items'])]
    return min((ranks[identity(source)] for source in origins if identity(source) in ranks),default=None)


def item_color(layout,key,label,row,settings,zone=None,codes=()):
    explicit=code_color(layout,key,label,settings,zone)
    if explicit:return explicit
    if settings.get('merged_color_enabled',True) and row.get('merged_count',1)>1:
        index=source_order_index(row,key,codes)
        if index is not None:return order_colors(settings)[min(index,3)]
    return BLACK

def validate_settings(settings):
    from .merge_settings import exclusions
    exclusions(settings)
    order_colors(settings)
    color_rules(settings)
    color(settings.get('merged_color',MERGED))
    try:
        size=float(settings.get('ditto_font_size',20))
        if isinstance(settings.get('ditto_font_size'),bool) or not 6<=size<=24:raise ValueError
    except (ValueError,TypeError):raise ValueError('同上符號字級請輸入 6～24 pt。') from None
    if settings.get('ditto_alignment','center') not in DITTO_ALIGN:raise ValueError('同上符號位置請選擇置左、置中或置右。')
    try:
        serial=float(settings.get('serial_font_size',14))
        if isinstance(settings.get('serial_font_size'),bool) or not 6<=serial<=24:raise ValueError
    except (ValueError,TypeError):raise ValueError('流水號字級請輸入 6～24 pt。') from None
    serial_colors(settings)
    for key in ('ditto_bold','merged_color_enabled','ditto_keep_adult','serial_superscript','show_order_notes','apply_order_note_rules'):
        if key in settings and type(settings[key]) is not bool:raise ValueError('顏色及粗體開關必須為勾選值。')
    return size
