"""Per-item visibility and deterministic, lossless columns of at most three rows."""
import copy
from .errors import LayoutCapacityError

LETTERS=tuple('ABCDEFGHI')
MODES={'normal':'正常顯示','single_max':'只有一個項目時置中、字體最大'}
PRINT_STATES=('是','否','跨區列印子項')


def print_state(value):
    if not value.get('print_enabled',False):return '否'
    return '跨區列印子項' if value.get('print_mode')=='cross_zone' else '是'

ZONE_KEYS={'生化／糞便':'bio','CBC／尿液':'cbc','外送':'sendout','e411':'e411','其他':'other'}
BIO_GROUPS={
    'A':('@','SMA','LFT','RFT','Alb','TP'), 'B':('AC','PC','Fe'),
    'C':('OT','PT'), 'D':('BUN','cre','uA','Alk','r-GT'),
    'E':('TG','CHO','T.Bili.','D.Bili.'), 'F':('HDL','LDL','Amy','Lipase')}
BIO_ALIASES={'UA':'uA','Alk-P':'Alk','γGT':'r-GT','γ-G.T':'r-GT',
    'T-Bili':'T.Bili.','D-Bil':'D.Bili.','HDL-C':'HDL','LDL-C':'LDL','LDL計':'LDL','GOT':'OT','GPT':'PT'}
BIO_RANK={label.casefold():(letter,index) for letter,labels in BIO_GROUPS.items() for index,label in enumerate(labels)}
BIO_RANK.update({alias.casefold():BIO_RANK[label.casefold()] for alias,label in BIO_ALIASES.items()})
# Positions are automatic within the assigned subgroup: a missing earlier item
# must not send the fourth candidate into the next subgroup prematurely.
BIO={label:(letter,None) for label,(letter,rank) in BIO_RANK.items()}


def apply_bio_groups(layout,records):
    """One-time user-requested regrouping; subsequent saved edits always win."""
    result=copy.deepcopy(layout);result.setdefault('bio_auto_start','A')
    if result.get('bio_groups_version')==1:return result
    for record in records:
        label=record['label'].strip().casefold();zone=record.get('print_zone',record['zone'])
        if label not in BIO or (zone!='生化／糞便' and label!='lipase'):continue
        if record.get('machine_group')=='aux':continue
        if label=='lipase' and zone!='生化／糞便':
            # Exact source codes only; do not rewrite a shared alias rule's other items.
            key=record['key']
            for rule in result['rules']:rule['codes']=[code for code in rule['codes'] if code!=key]
            result['rules'].append(dict(label=record['label'],zone='生化／糞便',codes=[key],aliases=[],enabled=True,source='20261013 生化分區'))
        value=result.setdefault('placements',{}).setdefault(record['key'],default_placement(record))
        value.update(subregion=BIO[label][0],position=None)
    result['bio_groups_version']=1
    validate(result);return result


def default_placement(record):
    kind=record['kind'];zone=record.get('print_zone',record['zone']);label=record['label']
    enabled=record.get('machine_group')!='aux' and (kind!='套組' or bool(label))
    if zone=='生化／糞便':subregion,position=BIO.get(label.strip().casefold(),('',None))
    elif zone=='CBC／尿液':subregion,position='A',2 if label.startswith(('UR','uB','尿液')) else 1
    elif zone=='其他':subregion,position='A',{'hba1c':1,'mab':2}.get(record.get('machine_group'),3)
    else:subregion,position='A',None
    return dict(print_enabled=enabled,subregion=subregion,position=position)


def migrate(layout,records):
    """Seed missing entries only; existing settings and explicit automatic slots survive."""
    result=copy.deepcopy(layout);result['version']=3
    placements=result.setdefault('placements',{})
    # Resolve against the old document once, before marking the migration complete.
    for record in records:
        placements[record['key']]=copy.deepcopy(placement(layout,record['key'],default_placement(record),record.get('print_zone',record['zone'])))
    regions=result.setdefault('subregions',{})
    if not layout.get('bio_adult_slot'):
        regions['生化／糞便']={letter:options(layout,'生化／糞便',letter) for letter in LETTERS}
    result['bio_adult_slot']=True
    for zone in ZONE_KEYS:
        for letter in LETTERS:
            regions.setdefault(zone,{}).setdefault(letter,dict(display='normal',compact_subregions=True,compact_positions=True))
    validate(result);return result


def validate(layout):
    if layout.get('bio_auto_start','A') not in LETTERS[:6]:raise ValueError('生化自動起始區必須為 A～F。')
    if 'bio_groups_version' in layout and (type(layout['bio_groups_version']) is not int or layout['bio_groups_version']!=1):raise ValueError('生化分區版本格式不正確。')
    for key,value in layout.get('placements',{}).items():
        if not isinstance(key,str) or not key or not isinstance(value,dict):raise ValueError('項目位置設定格式不正確。')
        if type(value.get('print_enabled')) is not bool:raise ValueError('是否列印必須為勾選值。')
        if 'print_mode' in value and (not key.startswith('G:') or value['print_mode']!='cross_zone' or not value['print_enabled']):
            raise ValueError('跨區列印子項僅適用於啟用列印的套組。')
        if value.get('subregion') not in ('',*LETTERS):raise ValueError('子區域必須為 A～I 或自動。')
        p=value.get('position')
        mode=value.get('position_mode','slot')
        if mode not in ('slot','order'):raise ValueError('位置模式必須為固定位置或排列順位。')
        maximum=99 if mode=='order' else 5
        if p is not None and (type(p) is not int or not 1<=p<=maximum):raise ValueError('排列順位必須為 1～99 或自動。' if mode=='order' else '位置必須為 1～5 或自動。')
    for zone,regions in layout.get('subregions',{}).items():
        if zone not in ZONE_KEYS or not isinstance(regions,dict):raise ValueError('子區域的列印區域不正確。')
        for letter,value in regions.items():
            if letter not in LETTERS or not isinstance(value,dict):raise ValueError('子區域必須為 A～I。')
            if value.get('display') not in MODES:raise ValueError('子區域顯示模式不正確。')
            if any(type(value.get(k)) is not bool for k in ('compact_subregions','compact_positions')):raise ValueError('遞補設定必須為勾選值。')


def options(layout,zone,letter):
    source=letter
    if zone=='生化／糞便' and not layout.get('bio_adult_slot'):
        source=LETTERS[LETTERS.index(letter)-1] if letter!='A' else ''
    value=dict({'display':'normal','compact_subregions':True,'compact_positions':True},
                **layout.get('subregions',{}).get(zone,{}).get(source,{}))
    if zone=='生化／糞便' and letter=='A' and not layout.get('bio_adult_slot'):value['compact_subregions']=False
    return value


def placement(layout,key,fallback,zone=None):
    value=copy.deepcopy(layout.get('placements',{}).get(key,fallback))
    if zone=='生化／糞便' and key in layout.get('placements',{}) and not layout.get('bio_adult_slot'):
        letter=value.get('subregion')
        if letter:value['subregion']=LETTERS[min(8,LETTERS.index(letter)+1)]
    return value


def arrange(items,zone,layout,*,expand_vertical=False,columns=9):
    """Explicit slots first, collisions shift down, automatic entries fill free slots.

    A full subgroup spills into the next available subgroup, never discards items.
    Its overflow retains provenance. A-I overflow invokes the existing force path.
    expand_vertical/columns remain accepted for older callers but never add rows.
    """
    bio=zone=='生化／糞便';limit=3
    letters=LETTERS[:6] if bio else LETTERS
    slots={letter:[] for letter in LETTERS};automatic=[];overflow=[]
    for order,item in enumerate(items):
        p=item.get('placement',{});letter=p.get('subregion','');position=p.get('position')
        if bio and letter not in letters:letter=''
        if not letter:automatic.append((order,item,position));continue
        slots[letter].append((position,order,item))
    cells={letter:{} for letter in LETTERS}
    for letter in LETTERS:
        ranked=sorted((r for r in slots[letter] if r[2].get('placement',{}).get('position_mode')=='order'),key=lambda r:(r[0] if r[0] is not None else 100,r[1]))
        fixed=sorted((r for r in slots[letter] if r[0] is not None and r[2].get('placement',{}).get('position_mode')!='order'),key=lambda r:(r[0],r[1]))
        floating=[r for r in slots[letter] if r[0] is None and r[2].get('placement',{}).get('position_mode')!='order']
        if bio:floating.sort(key=lambda r:(BIO_RANK.get(r[2]['label'].strip().casefold(),('',999))[1],r[1]))
        # A rank orders only the items actually present; it never reserves a row.
        # Explicit slots keep priority. Ranked items overflow after this subgroup
        # fills, even in adaptive-height mode, without adding a biochemical row.
        for position,order,item in fixed+[(None,order,item) for _,order,item in ranked]+floating:
            target=position or 1
            while target in cells[letter]:target+=1
            if target<=limit:cells[letter][target]=item
            else:overflow.append((LETTERS.index(letter)+1,order,item))
    for start,order,item in overflow:
        candidates=letters[start:]
        target=next(((letter,p) for letter in candidates for p in range(1,limit+1) if p not in cells[letter]),None)
        if target is None:raise LayoutCapacityError('生化 A～F／每區三列仍不足；未省略項目' if bio else '子區域 A～I／每區三列仍不足；未省略項目')
        cells[target[0]][target[1]]=item
    candidates=letters[letters.index(layout.get('bio_auto_start','A')):] if bio else letters
    automatic.sort(key=lambda r:(r[2] if r[1].get('placement',{}).get('position_mode')=='order' and r[2] is not None else 100,r[0]))
    for order,item,position in automatic:
        if item.get('placement',{}).get('position_mode')=='order':position=None
        target=next(((letter,p) for letter in candidates for p in ([position] if position and position<=limit else range(1,limit+1)) if p not in cells[letter]),None)
        if target is None:raise LayoutCapacityError(f"生化 {layout.get('bio_auto_start','A')}～F 自動空位不足（每區最多三列）；未省略項目" if bio else '子區域 A～I／每區三列仍不足；未省略項目')
        cells[target[0]][target[1]]=item
    active=[];column=0
    for index,letter in enumerate(LETTERS):
        opts=options(layout,zone,letter)
        if not cells[letter]:
            # An unchecked empty subgroup reserves its original horizontal width.
            if not opts['compact_subregions']:column+=1
            continue
        entries=sorted(cells[letter].items())
        if opts['compact_positions']:entries=list(enumerate([item for _,item in entries],1))
        active.append(dict(letter=letter,column=column,entries=entries,options=opts));column+=1
    # Trailing empty reservations need not squeeze a row that has no content there.
    return active
