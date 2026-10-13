"""A4 renderer: independent zones with at most three rows per column."""
from __future__ import annotations
import copy,math,re,os
from pathlib import Path
from . import layout_settings as ls
from .core import CBC_DETAIL_CODES,STOOL_DETAIL_CODES
from .errors import LayoutCapacityError

WIDTHS=[10,7,19,5,16,0,51,13,17,27,25]
VISIT_DATE_WIDTH=5  # Reserve inside the name area; test columns keep their fixed x positions.
HEADERS=['診所','工作號','姓名','性別','病歷號／保險','@','生化／糞便','CBC／尿液','外送','e411','其他']
ZONE_KEYS={'生化／糞便':'bio','CBC／尿液':'cbc','外送':'sendout','e411':'e411','其他':'other'}
SHORT={'UTP':'uTP','LDL(calc)':'LDL計','HDL-C':'HDL-C','γ-G.T':'GGT','(舊)eGFR(MDRD method)':'eGFR',
       'LDL-C/HDL-C R.':'LDL/HDL','CA-19-9':'CA19-9'}
# Fixed biochemical x positions in mm relative to the zone. Empty groups keep their space.
BIO_GROUPS=[(['AC','TP','Alb'],0,8.5),(['OT','PT'],8.5,8.5),(['BUN','cre','UA'],17,8.5),
            (['TG','CHO'],25.5,8.5),(['HDL','HDL-C','LDL','LDL計'],34,11)]

def page_geometry(settings):
    body=(49 if settings.get('export_glucose_ac',True) else 20) if settings.get('show_column_headers',False) else (43 if settings.get('export_glucose_ac',True) else 14)
    return body,(291-body)/20

def biochemistry_columns(items,available_width,measure):
    columns=[];used=set();free=[]
    for labels,x,w in BIO_GROUPS:
        found=[item for label in labels for item in items if item['label']==label]
        if found:
            columns.append((found,x,w));used.update(id(i) for i in found)
        else:free.append([x,x+w])
    if available_width>45:free.append([45,available_width])
    merged=[]
    for lo,hi in free:
        if merged and abs(merged[-1][1]-lo)<.01:merged[-1][1]=hi
        else:merged.append([lo,hi])
    extra=[i for i in items if id(i) not in used]
    # Extra tests may use truly vacant columns, but never move the standard groups.
    while extra:
        placed=False
        for region in merged:
            room=region[1]-region[0]
            fit=[i for i in extra if measure(i['label'])+1.4<=room][:3]
            if not fit:continue
            w=max(measure(i['label']) for i in fit)+1.4
            columns.append((fit,region[0],w));region[0]+=w+.8
            for item in fit:extra.remove(item)
            placed=True;break
        if not placed:
            # Dense rows may share a spare sub-row; standard columns still never shift.
            for existing,x,w in columns:
                fit=next((i for i in extra if measure(i['label'])+1.4<=w),None)
                if fit is not None and len(existing)<3:
                    existing.append(fit);extra.remove(fit);placed=True;break
        if not placed:raise LayoutCapacityError('固定生化欄位不足以容納額外項目，請設定簡稱或調整區域')
    if any(len(items)>3 for items,x,w in columns):raise LayoutCapacityError('生化串列超過三層')
    return sorted(columns,key=lambda c:c[1])

def clinic_label(value):return str(value or '').replace('診所','').strip()

def expanded_biochemistry(items,available_width,measure,lanes):
    """Keep standard x positions; pack extra labels into vacant sub-row intervals."""
    free=[[[0,available_width]] for _ in range(lanes)]
    placed=[];used=set()
    def occupy(lane,x,w):
        remaining=[]
        for lo,hi in free[lane]:
            if hi<=x or lo>=x+w:remaining.append([lo,hi]);continue
            if lo<x:remaining.append([lo,x])
            if hi>x+w:remaining.append([x+w,hi])
        free[lane]=remaining
    for labels,x,w in BIO_GROUPS:
        found=[i for label in labels for i in items if i['label']==label]
        if len(found)>lanes:raise LayoutCapacityError('同一生化固定欄超過五小列')
        for lane,item in enumerate(found):
            if measure(item['label'])+1.2>w:raise LayoutCapacityError('生化固定項目超出欄寬')
            placed.append((item,x,w,lane));used.add(id(item));occupy(lane,x,measure(item['label'])+1.4)
    extra=[i for i in items if id(i) not in used]
    # Long labels first avoid fragmenting space needed by a wider item.
    for item in sorted(extra,key=lambda i:measure(i['label']),reverse=True):
        need=measure(item['label'])+1.4
        choices=[(hi-lo,lane,lo) for lane,gaps in enumerate(free) for lo,hi in gaps if hi-lo>=need]
        if not choices:raise LayoutCapacityError('生化區五小列仍不足，請為較長項目設定簡稱；未省略任何項目')
        _,lane,x=min(choices)
        placed.append((item,x,need,lane));occupy(lane,x,need)
    return placed

def page_slots(rows,date):
    """User-confirmed reserved row; never create an order or infer other gaps."""
    out=list(rows)
    if date=='2026-08-29':
        numbers=[int(r['workno']) if str(r['workno']).isdigit() else None for r in rows]
        if 44 in numbers:
            raise ValueError('8/29 第44列已核定留空，但資料含44號，請先核對。')
        if any(n is not None and n>44 for n in numbers):
            index=next(i for i,n in enumerate(numbers) if n is not None and n>44)
            out.insert(index,None)
    return out

def prepare(rows,settings):
    """Keep raw items unchanged; re-route visible items with saved layout rules."""
    config=settings.get('layout') or ls.load();ls.validate(config)
    if config.get('version',2)>=3:
        from .print_items import prepare as prepare_items
        return prepare_items(rows,settings,config)
    out=copy.deepcopy(rows)
    seq={'e411':0,'hba1c':0,'mab':0}
    for row in out:
        zones={k:[] for k in ZONE_KEYS.values()};groups={'e411':[],'hba1c':[],'mab':[]}
        row['display_accounting']=[]
        adult_codes=set()
        if row.get('adult_health_flag') and settings.get('compact_adult_health',True):
            for p in row.get('verified_panels',[]):
                if (p['name'] or '').strip().startswith(('成健','不報成健')):adult_codes.update(p['members'])
            if 'adult_compact_codes' in row:adult_codes=set(row['adult_compact_codes'])
        for group in ('routine','e411','hba1c','mab'):
            tokens=[]
            for label in filter(None,(x.strip() for x in row.get(group,'').split(' / '))):
                source=[s for s in row['source_items'] if s['label']==label]
                compressed=label=='CBC' or label.startswith(('CBC(','尿液(','糞便('))
                if label=='CBC' or label.startswith('CBC('):source=[s for s in row['source_items'] if s['code'] in CBC_DETAIL_CODES]
                elif label.startswith('尿液('):source=[s for s in row['source_items'] if re.fullmatch(r'U\d{2}',s['code'])]
                elif label=='糞便(13項)':source=[s for s in row['source_items'] if s['code'] in STOOL_DETAIL_CODES]
                overridden=(compressed or len(source)>1) and any(ls.match({'LCI_ID':s['code'],'LCI_NAME':s.get('name',s['label']),'LCI_NAMES':s['label'],'LCI_NAMEC':s.get('namec','')},config) for s in source)
                if overridden:tokens.extend((s['label'],[s]) for s in source)
                else:tokens.append((label,source))
            for label,source in tokens:
                rules=[]
                for s in source or [{'label':label}]:
                    item={'LCI_ID':s.get('code',''),'LCI_NAME':s.get('name',label),'LCI_NAMEC':s.get('namec',''),'LCI_NAMES':label}
                    rule=ls.match(item,config)
                    if rule and rule not in rules:rules.append(rule)
                if len(rules)>1:raise ValueError(f"工作號 {row['workno']} 的顯示項目有多個版面規則，請以代碼核對。")
                override=rules[0] if rules else None
                shown=override['label'] if override else SHORT.get(label,label)
                if override:zone=ZONE_KEYS[override['zone']]
                elif group=='e411':zone='e411'
                elif group in ('hba1c','mab'):zone='other'
                elif label=='CBC' or label.startswith(('CBC(','尿液(')) or any(s.get('code','').startswith('B') for s in source):zone='cbc'
                elif label in ('U-cre','U-ACR','UTP','U-PCR','HBeAg'):zone='other'
                else:zone='bio'
                if label.startswith('尿液(') and not override:
                    shown='UR'+re.search(r'\d+',label).group()
                if label=='糞便(13項)' and not override:shown='Stool'
                if (label=='CBC' or label.startswith(('CBC(','尿液(','糞便('))) and not override:
                    generated=ls.match({'LCI_ID':'PRINT:'+shown},config)
                    if generated:
                        shown,zone=generated['label'],ZONE_KEYS[generated['zone']];override=generated
                    elif shown in ls.GENERATED:
                        shown,destination,_=ls.GENERATED[shown];zone=ZONE_KEYS[destination]
                # Presentation destination and sequence membership are independent.
                sequence_group=group if group in groups else None
                item={'label':shown,'original_label':label,'machine':sequence_group,'configured':bool(override),'codes':[s.get('code') for s in source if s.get('code')]}
                if not override and group=='routine' and item['codes'] and set(item['codes'])<=adult_codes:
                    row['display_accounting'].append({'original':label,'zone':zone,'display':'@','covered_by':'當筆IC旗標＋已驗證成健套組成員'})
                    continue
                zones[zone].append(item)
                if sequence_group:groups[sequence_group].append(item)
                row['display_accounting'].append({'original':label,'zone':zone,'display':shown,'covered_by':None})
        # Explicit G: codes abbreviate an ordered panel, never infer one from its members.
        row['panel_display']=[]
        for panel in row.get('ordered_panels',[]):
            panel_rule=next((r for r in config['rules'] if r['enabled'] and
                'G:'+panel['code'] in r['codes']),None)
            if not panel_rule:continue
            members=set(panel['present_members']);fold=[]
            placeholder='套組待核:'+panel['code']
            for zone in zones:
                for item in zones[zone]:
                    if item['original_label']==placeholder or (item['codes'] and
                        set(item['codes'])<=members and not item.get('machine') and not item.get('configured')):
                        fold.append(item)
                zones[zone]=[i for i in zones[zone] if i not in fold]
            if not fold:continue
            destination=ZONE_KEYS[panel_rule['zone']];label=panel_rule['label']
            covered_codes=sorted({c for i in fold for c in i['codes']})
            zones[destination].append({'label':label,'original_label':panel['name'],
                'machine':None,'configured':True,'codes':covered_codes})
            for a in row['display_accounting']:
                if any(i['original_label']==a['original'] for i in fold):
                    a.update(zone=destination,display=label,covered_by='登錄套組 '+panel['code']+' 簡稱；不增補缺項')
            row['panel_display'].append({'code':panel['code'],'label':label,'zone':destination,
                'covered_codes':covered_codes,'missing_members':panel['missing_members']})
        # Compact only full, present urine combinations. Every covered item remains in accounting.
        other=zones['other'];labels={x['original_label'] for x in other}
        covered=set()
        if {'mab','U-cre','U-ACR'}<=labels:covered |= {'U-cre','U-ACR'}
        if {'UTP','U-cre','U-PCR'}<=labels:covered |= {'U-cre','U-PCR'}
        zones['other']=[x for x in other if x['original_label'] not in covered]
        for a in row['display_accounting']:
            if a['original'] in covered:a['covered_by']='mab／UTP完整尿液組合'
        for code,short in [('0080','LFT'),('00052','SMA')]:
            panel=next((p for p in row.get('verified_panels',[]) if p['code']==code),None)
            if not panel:continue
            pcs=set(panel['members'])
            fold=[x for x in zones['bio'] if not x.get('configured') and x['codes'] and set(x['codes'])<=pcs]
            if len(fold)<2:continue
            zones['bio']=[x for x in zones['bio'] if x not in fold]
            rule=ls.match({'LCI_ID':'PRINT:'+short},config)
            destination=ZONE_KEYS[rule['zone']] if rule else 'bio';shown=rule['label'] if rule else short
            zones[destination].insert(0,{'label':shown,'original_label':short,'machine':None,'codes':sorted(pcs)})
            for a in row['display_accounting']:
                if a['zone']=='bio' and any(x['original_label']==a['original'] for x in fold):
                    a.update(covered_by=short+'已驗證套組',zone=destination,display=shown)
        for g in seq:
            if groups[g]:seq[g]+=1;row[g+'_seq']=seq[g]
            else:row[g+'_seq']=None
        zones['other'].sort(key=lambda x:0 if x['machine']=='hba1c' else 1 if x['machine']=='mab' else 2 if x['original_label']=='UTP' else 3)
        row['zones']=zones
        row['clinic_print']=clinic_label(row['clinic'])
    return out

def display_work_numbers(row):
    """The workbook and AC sheet use exactly the same visible work numbers."""
    return [str(n) for n in (row.get('workno_lines') or [row.get('workno_display') or
        (str(int(row['workno'])) if str(row['workno']).isdigit() else str(row['workno']))])]


def export(path,rows,date,settings,draft=False):
    from .font_settings import sizes as font_sizes
    fonts=font_sizes(settings)
    from .print_style import Ink,validate_settings,serial_ink,serial_colors,run_size,run_rise,run_height,measure_run
    ditto_size=validate_settings(settings)
    from . import glucose_sheet
    ac_plan=glucose_sheet.header_plan(rows,settings)
    config=copy.deepcopy(settings.get('layout') or ls.load())
    legacy=config.get('version',2)<3
    legacy_prepared=prepare(rows,dict(settings,layout=config)) if legacy else None
    config['version']=max(3,config.get('version',2))
    settings=dict(settings,layout=config)
    subregions_enabled=True
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from .pdf_fonts import PdfFonts
    if not rows:raise ValueError('當日沒有資料。')
    prepared=prepare(rows,settings) if legacy_prepared is None else legacy_prepared
    if legacy:
        # Older saved progress may contain explicit display fields without source
        # tokens. Keep those labels, but use the new three-line region renderer.
        from . import subregions as sr
        from .print_style import item_color
        for row in prepared:
            for zone,key in sr.ZONE_KEYS.items():
                for item in row['zones'][key]:
                    item['key']=next(iter(item.get('codes',[])),item['label'])
                    item['machines']=[item['machine']] if item.get('machine') else []
                    item['color']=item_color(config,item['key'],item['label'],row,settings,zone,item.get('codes',[]))
                    item['placement']=sr.default_placement(dict(kind='單項',label=item['label'],zone=zone,machine_group=item.get('machine')))
            if row.get('adult_health_flag'):
                row['zones']['bio'].insert(0,dict(key='@',label='@',codes=[],machines=[],font_size=fonts['adult_health'],color=item_color(config,'@','@',row,settings,'生化／糞便'),placement=dict(print_enabled=True,subregion='A',position=1)))
    for prepared_row in prepared:
        for key,items in prepared_row['zones'].items():
            for item in items:item['_serial_base_size']=fonts[key]
    slots=page_slots(prepared,date)
    from . import print_geometry,ditto,adaptive_layout as adaptive
    fixed_20=bool(settings.get('fixed_20_rows',True))
    fixed_columns=print_geometry.column_counts(slots,config) if subregions_enabled or not fixed_20 else {}
    typefaces=PdfFonts(settings)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.partial.pdf')
    c=canvas.Canvas(str(tmp),pagesize=A4);c.setTitle(f'檢驗工作簿 {date}');c.setAuthor('工作簿輸出（本機）')
    H=A4[1];xs=[10]
    for w in WIDTHS:xs.append(xs[-1]+w)
    body,rowh=page_geometry(settings);base_rowh=rowh
    headers=bool(settings.get('show_column_headers',False));red='#B02631';blue='#215CAE';black='#202830'
    force=bool(settings.get('force_export',False));adjustments=[];commands=None
    def width(s,size):return typefaces.width(s,size)/mm
    def item_width(s,size):
        # Preserve taller glyphs in fixed columns, using moderate horizontal compression.
        return max(0,(typefaces.width(s,size)-min(.08,size/75)*max(0,len(str(s))-1))*.78/mm)
    def item_text(s,x,center,w,size=11,color=black):
        if measure_run(item_width,s,size,color)>w+.001:raise LayoutCapacityError('項目文字超出欄寬')
        if commands is not None:commands.append(('item',(s,x,center,w,size,color)));return
        c.saveState()
        ink=color if isinstance(color,Ink) else Ink(color)
        c.setFillColor(ink.color)
        t=c.beginText(x*mm,H-(center+size/mm*.32)*mm)
        # Explicit serial metadata keeps colored labels at the ordinary baseline.
        actual_size=run_size(size,ink)
        t.setRise(run_rise(size,ink))
        typefaces.write(t,s,actual_size,horizontal_scale=78,char_space=-min(.08,actual_size/75));c.drawText(t)
        c.restoreState()
    def text(s,x,center,w,size=8.5,color=black):
        if width(s,size)>w:raise LayoutCapacityError('文字超出欄寬')
        if commands is not None:commands.append(('text',(s,x,center,w,size,color)));return
        c.saveState();c.setFillColor(color)
        t=c.beginText(x*mm,H-(center+size/mm*.32)*mm)
        typefaces.write(t,s,size);c.drawText(t);c.restoreState()
    def fitted_text(s,x,center,w,size,color=black,bold=False):
        # Increase glyph height independently of column width. State never leaks to tests.
        if commands is not None:commands.append(('fit',(s,x,center,w,size,color,bold)));return
        scale=min(1,w/max(typefaces.width(s,size,bold)/mm,.001))
        ascent,descent=typefaces.metrics(size,s,bold)
        c.saveState();c.setFillColor(color)
        t=c.beginText(x*mm,H-center*mm-(ascent+descent)/2)
        if bold and typefaces.cjk_bold==typefaces.cjk:c.setStrokeColor(color);c.setLineWidth(.18);t.setTextRenderMode(2)
        typefaces.write(t,s,size,bold,horizontal_scale=scale*100);c.drawText(t)
        c.restoreState()
    def height_fit(size,height):
        ascent,descent=typefaces.metrics(1)
        return min(size,max(.1,height-.6)*mm/max(1,ascent-descent))
    def line(x,y,x2,y2,color='#B2B9C1',lw=.3):
        if commands is not None:commands.append(('line',(x,y,x2,y2,color,lw)));return
        c.setStrokeColor(color);c.setLineWidth(lw);c.line(x*mm,H-y*mm,x2*mm,H-y2*mm)
    def wrapped(value,w,size=8.5,limit=3,compact=False):
        lines=['']
        for char in str(value):
            if (item_width if compact else width)(lines[-1]+char,size)>w:
                lines.append(char)
            else:lines[-1]+=char
        if len(lines)>limit:raise LayoutCapacityError(f'內容超過{limit}小列')
        return lines
    def identity(value,col,y,size=None,inset=0,color=black,allow_tiny=False):
        key={0:'clinic',1:'workno',2:'name',3:'sex',4:'chart_number',5:'adult_health',8:'sendout'}[col]
        size=fonts[key] if size is None else size
        available=WIDTHS[col]-1.4-inset
        # Prefer one tall line down to 60% width, then wrap up to three lines.
        for _ in range(180):
            if size<6 and not allow_tiny:raise LayoutCapacityError('欄位文字超出可容納範圍，請調整字級或使用強制輸出')
            try:lines=wrapped(value,available/.6,size,limit=3 if fixed_20 else 2000)
            except LayoutCapacityError:size*=.9;continue
            fitted=height_fit(size,rowh/len(lines))
            if fitted>=size-.001:break
            size=fitted
        else:raise LayoutCapacityError('欄位文字無法排入主列')
        for j,s in enumerate(lines):fitted_text(s,xs[col]+.7+inset,y+(j+.5)*rowh/len(lines),available,size,color)
    def work_numbers(row,y,color=black,force=False):
        numbers=display_work_numbers(row)
        if len(numbers)>5 and not force and fixed_20:raise LayoutCapacityError('併單工作號超過五行，請改用拆單或只顯示第一工作號')
        size=height_fit(fonts['workno'],rowh/len(numbers));available=WIDTHS[1]-1.4
        # Do not turn a long custom work number into an unreadably narrow stroke.
        size=min(size,*(available*size/(max(width(n,size),.001)*.6) for n in numbers))
        for j,n in enumerate(numbers):fitted_text(n,xs[1]+.7,y+(j+.5)*rowh/len(numbers),available,size,color)
    def visit_dates(values,y,force=False):
        from .visit_dates import calendar_date
        if not values:return
        if len(values)>3 and not force and fixed_20:raise LayoutCapacityError('併單有超過三個不同就醫日期，請改用拆單以完整顯示日期')
        size=min(fonts['visit_date'],max(.1,rowh/len(values)-.7)*mm/2)
        ascent,descent=typefaces.metrics(size,'0123456789')
        offset=((ascent-descent)/mm+.3)/2
        for j,value in enumerate(values):
            day=calendar_date(value);center=y+(j+.5)*rowh/len(values)
            x=xs[2];w=VISIT_DATE_WIDTH
            for label,cy in ((str(day.day),center-offset),(str(day.month),center+offset)):
                label_width=min(w-1,width(label,size))
                fitted_text(label,x+(w-label_width)/2,cy,label_width,size,red)
            line(x+.5,center,x+w-.5,center,red,.45)
    def zone_size(key,lanes=3,dense=False):
        target=fonts[key]
        if lanes==4:target*=9.5/(10.5 if key in ('e411','other') else 11)
        elif lanes==5:target*=8/(10.5 if key in ('e411','other') else 11)
        elif dense and key not in ('e411','other'):target*=10.5/11
        # Dense 4/5-line zones retain their established 9.5/8 pt defaults.
        # Both the label and its raised number must stay inside the row. The
        # superscript's top bearing is slightly taller than the label's.
        ascent,_=typefaces.metrics(1)
        top_bearing=max(ascent-.32,ascent*.72+.28-.32)
        edge=rowh/(3 if lanes==2 else 2*lanes)
        return min(target,max(.05,(edge*mm-.1)/top_bearing))
    def stack(items,x,w,y,results=False,suffix_groups=(),font_key='bio'):
        base=zone_size(font_key,3 if font_key=='bio' else max(1,min(3,len(items))))
        if not results and items and all(not i.get('machine') for i in items) and any(item_width(i['label'],base)>w-1.2 for i in items):
            for limit in (3,4,5):
                size=zone_size(font_key,limit)
                try:expanded=[part for item in items for part in wrapped(item['label'],w-1.2,size,limit,compact=True)]
                except ValueError:continue
                if len(expanded)<=limit:break
            else:raise LayoutCapacityError('完整項目名稱換行後五小列仍不足，請調整簡稱')
            for j,part in enumerate(expanded):item_text(part,x+.5,y+(j+.5)*rowh/len(expanded),w-1.2,size)
            return
        if len(items)>3:
            # Preserve legible type while increasing the number of sub-rows.
            for limit in (3,4,5):
                size=zone_size(font_key,limit,dense=True)
                lanes=[[]];used_width=0;seen=set(printed);too_wide=False
                for item in items:
                    machine=item.get('machine');seqtext=''
                    if machine and machine not in seen:
                        seqtext=str(current[machine+'_seq'])+('/' if machine=='mab' else '')
                        seen.add(machine)
                    reserve=max(3.6,item_width(seqtext,size)+.5) if seqtext else 0
                    need=item_width(item['label'],size)+reserve+1.8+(5 if results else 0)
                    if need>w:too_wide=True;break
                    if used_width+need>w:
                        lanes.append([]);used_width=0
                    lanes[-1].append((item,seqtext,reserve,need));used_width+=need
                if not too_wide and len(lanes)<=limit:break
            else:raise LayoutCapacityError('並排後五小列仍不足，請調整項目簡稱或區域；未省略任何項目')
            for j,lane in enumerate(lanes):
                center=y+(j+.5)*rowh/len(lanes);cursor=x
                for item,seqtext,reserve,need in lane:
                    machine=item.get('machine')
                    suffix=machine in suffix_groups
                    if seqtext and not suffix:
                        item_text(seqtext,cursor+.5,center,reserve,size,serial_ink(machine,settings,fonts[font_key]))
                    if seqtext:printed.add(machine)
                    start=cursor+.5+(0 if suffix else reserve);label_width=item_width(item['label'],size)
                    item_text(item['label'],start,center,label_width+.1,size)
                    end=start+label_width
                    if seqtext and suffix:
                        item_text(seqtext,end+.7,center,reserve,size,serial_ink(machine,settings,fonts[font_key]))
                        end+=.7+item_width(seqtext,size)
                    if results:line(end+.6,center+1.2,cursor+need-.6,center+1.2,'#C1C8CD',.25)
                    cursor+=need
            return
        for j,item in enumerate(items):
            center=y+(j+.5)*rowh/len(items)
            label=item['label'];machine=item.get('machine');size=base
            seqtext=''
            if machine and machine not in printed:
                seqtext=str(current[machine+'_seq'])+('/' if machine=='mab' else '')
                printed.add(machine)
            reserve=max(3.6,item_width(seqtext,size)+.5) if machine else 0
            color=serial_ink(machine,settings,fonts[font_key]) if machine else Ink(black)
            suffix=machine in suffix_groups
            if suffix:reserve=(item_width(seqtext,size)+.7) if seqtext else 0
            start=x+.5+(0 if suffix else reserve)
            available=w-reserve-1.2-(8.7 if results else 0)
            # Enlarged defaults still fit ordinary legacy names when a small
            # reduction suffices; genuinely dense content keeps the force gate.
            size=min(size,size*available/max(.001,item_width(label,size)))
            if size<min(7.5,fonts[font_key])-.001:raise LayoutCapacityError('項目簡稱過長或結果書寫空間不足')
            if seqtext and not suffix:item_text(seqtext,x+.5,center,reserve,size,color)
            if item_width(label,size)>available:raise LayoutCapacityError('項目簡稱過長或結果書寫空間不足')
            item_text(label,start,center,available,size)
            end=start+item_width(label,size)
            if seqtext and suffix:
                item_text(seqtext,end+.7,center,reserve,size,color);end+=reserve
            if results:
                line(end+.7,center+1.2,x+w-.7,center+1.2,'#C1C8CD',.25)
    def biochemistry(items,x,w,y):
        try:
            columns=biochemistry_columns(items,w,lambda s:item_width(s,zone_size('bio')))
        except ValueError:
            # A main row keeps its height; only this zone gains sub-rows.
            if any(i.get('machine') for i in items):
                raise LayoutCapacityError('生化區含機器項目且空間不足，請將機器項目設定回結果區') from None
            for count in (4,5):
                size=zone_size('bio',count)
                try:layout=expanded_biochemistry(items,w,lambda s:item_width(s,size),count)
                except ValueError:
                    if count==5:raise
                    continue
                for item,offset,cw,lane in layout:
                    item_text(item['label'],x+offset+.5,y+(lane+.5)*rowh/count,cw-1,size)
                expanded_counts[count]+=1
                return
        else:
            for col,offset,cw in columns:stack(col,x+offset,cw,y)
    def item_segments(item,seen=None):
        seen=printed if seen is None else seen
        machines=[g for g in item.get('machines',([item['machine']] if item.get('machine') else [])) if g not in seen]
        runs=[(item['label'],Ink(item.get('color',black)))]
        for group in machines:
            number=str(current[group+'_seq'])+('/' if group=='mab' else '')
            color=serial_ink(group,settings,item.get('_serial_base_size',fonts['e411' if group=='e411' else 'other']))
            if item.get('panel'):
                runs.append(({'e411':'e411','hba1c':'HbA1c','mab':'mab'}[group]+number,color))
            elif group=='e411':runs.insert(0,(number,color))
            else:runs.append((number,color))
        return runs,machines
    def draw_subregions(items,key,x,w,y,tiny=False,only_adult=False):
        from . import subregions as sr
        if not items:return
        zone=next(name for name,k in ZONE_KEYS.items() if k==key)
        groups=sr.arrange(items,zone,config)
        columns=max(g['column'] for g in groups)+1
        # Missing groups leave trailing space; they never stretch the remaining slots.
        normal_columns=fixed_columns[key]
        if columns>normal_columns and not tiny:raise LayoutCapacityError('子區域數超過固定欄位，請調整區域或使用強制輸出')
        count=max(normal_columns,columns);cw=w/count;scale=normal_columns/count
        readable_min=min(7.5,fonts[key])
        peak=max(max(p for p,_ in g['entries']) for g in groups)
        if peak>3:raise LayoutCapacityError('檢驗區每欄最多三小列')
        for group in groups:
            if only_adult and not any(ditto.is_adult(item) for _,item in group['entries']):continue
            gx=x+cw*group['column']
            entries=group['entries'];opts=group['options'];single=len(entries)==1 and opts['display']=='single_max'
            lanes=peak
            cellh=rowh if single else rowh/(3 if lanes==2 else lanes)
            size=height_fit(max(24,fonts[key]),cellh) if single else zone_size(key,lanes)
            if key=='bio' and all(item.get('key')=='@' for _,item in entries):size=height_fit(fonts['adult_health'],cellh)
            padding=1.2*scale
            planned=[];seen=set(printed)
            for position,item in entries:
                runs,machines=item_segments(item,seen);seen.update(machines)
                has_result=bool(item.get('machines')) or key in ('e411','other')
                reserve=min(3*scale,cw*.28) if has_result else 0
                room=cw-padding-reserve
                measured=sum(measure_run(item_width,text,size,ink) for text,ink in runs)
                size=min(size,size*room/max(.001,measured))
                planned.append((position,runs,machines,has_result,reserve,item))
            # Measure the actual faces rather than reserve the full CJK box for
            # ASCII serials. Keep adjacent lines and row boundaries separate.
            extent=0
            for _,runs,_,_,_,_ in planned:
                for value,ink in runs:
                    ascent,descent=typefaces.metrics(run_size(size,ink),value)
                    rise=run_rise(size,ink)
                    extent=max(extent,2*(ascent+rise-size*.32),2*(size*.32-descent-rise))
            size*=min(1,max(.1,cellh-.2)*mm/max(.001,extent))
            if not tiny and size<readable_min-.001:raise LayoutCapacityError('子區域 '+group['letter']+' 空間不足，請調整簡稱、子區域或使用強制輸出')
            size=max(.05,size)
            for position,runs,machines,has_result,reserve,item in planned:
                if only_adult and not ditto.is_adult(item):continue
                center=y+rowh/2 if single else y+print_geometry.lane_center(position,lanes,rowh)
                measured=sum(measure_run(item_width,text,size,ink) for text,ink in runs)
                cursor=gx+(padding/2 if not single else (cw-measured-reserve)/2)
                for value,color in runs:
                    length=measure_run(item_width,value,size,color);item_text(value,cursor,center,length+.001,size,color);cursor+=length
                if has_result:line(cursor+padding*.4,center+min(1.2,cellh*.2),gx+cw-padding/2,center+min(1.2,cellh*.2),'#C1C8CD',.25)
                printed.update(machines)
    def draw_patient(row,y,tiny=False):
        name,sex,chart=ditto.patient_display(row,current_ditto['patient'])
        if current_ditto['patient']:draw_ditto(xs[2]+.7+VISIT_DATE_WIDTH,y,WIDTHS[2]-1.4-VISIT_DATE_WIDTH)
        else:identity(name,2,y,inset=VISIT_DATE_WIDTH,allow_tiny=tiny)
        identity(sex,3,y,allow_tiny=tiny)
        identity(chart,4,y,allow_tiny=tiny)
    def adaptive_row(row):
        seen=set();zones={};needed=base_rowh
        for key,col in [('bio',6),('cbc',7),('sendout',8),('e411',9),('other',10)]:
            items=list(row['zones'][key])
            if key=='sendout' and row.get('notes'):items.append({'label':'備註：'+row['notes']})
            zone=adaptive.zone_plan(items,key,config,fixed_columns[key],WIDTHS[col],fonts[key],item_segments,item_width,seen,force)
            zones[key]=zone
            if zone:needed=max(needed,zone['height'])
        for value,col,key,inset in [(row['clinic_print'],0,'clinic',0),(row['name'],2,'name',VISIT_DATE_WIDTH),
                (ditto.patient_display(row,False)[1],3,'sex',0),(row.get('insurance_label') or row.get('chart_number') or '',4,'chart_number',0)]:
            lines=wrapped(value,(WIDTHS[col]-1.4-inset)/.6,fonts[key],limit=2000)
            needed=max(needed,len(lines)*(fonts[key]/mm*1.15+.6))
        numbers=row.get('workno_lines') or [row.get('workno_display') or row['workno']]
        needed=max(needed,len(numbers)*(fonts['workno']/mm*1.15+.6),len(row.get('visit_dates',[]))*(2*fonts['visit_date']/mm+.7))
        return dict(zones=zones,height=needed)
    def draw_adaptive_zone(plan,key,col,y,scale=1):
        if not plan:return
        if plan.get('packed'):
            draw_packed(plan['packed'],xs[col]+plan['offset'],plan['width'],y)
            if plan.get('adult'):
                item=plan['adult'];item_text('@',xs[col]+.6,y+rowh/2,7,fonts['adult_health'],item.get('color',black))
            return
        cw=plan['cell_width'];padding=plan['padding']
        # A tall CBC region must not pull two wrapped words in another region apart.
        block_height=min(rowh,max(base_rowh,plan['height']*scale))
        block_top=y+(rowh-block_height)/2
        for group in plan['groups']:
            size=group['size']*scale;gx=xs[col]+group['column']*cw
            for piece in group['pieces']:
                lines=piece['lines']
                for offset,runs in enumerate(lines):
                    lanes=len(lines) if group['single'] else plan['lanes']
                    position=offset+1 if group['single'] else plan['starts'][piece['position']]+offset+1
                    center=block_top+print_geometry.lane_center(position,lanes,block_height)
                    measured=sum(measure_run(item_width,value,size,ink) for value,ink in runs)
                    reserve=piece['reserve'] if offset==len(lines)-1 else 0
                    cursor=gx+((cw-measured-reserve)/2 if group['single'] else padding/2)
                    for value,color in runs:
                        length=measure_run(item_width,value,size,color);item_text(value,cursor,center,length+.001,size,color);cursor+=length
                    if reserve:line(cursor+padding*.4,center+min(1.2,block_height/max(1,lanes)*.2),gx+cw-padding/2,center+min(1.2,block_height/max(1,lanes)*.2),'#C1C8CD',.25)
                printed.update(piece['machines'])
    def draw_ditto(x,y,w,color=black):
        size=height_fit(ditto_size,rowh);bold=bool(settings.get('ditto_bold',True))
        actual=min(w,typefaces.width(ditto.SYMBOL,size,bold)/mm)
        align=settings.get('ditto_alignment','center')
        offset={'left':0,'center':(w-actual)/2,'right':w-actual}[align]
        fitted_text(ditto.SYMBOL,x+offset,y+rowh/2,actual,size,color,bold=bold)
    def draw_bio_ditto(y):
        from .print_style import item_color
        kept=[i for i in current['zones']['bio'] if settings.get('ditto_keep_adult',True) and ditto.is_adult(i)]
        x=xs[6]+.6;w=WIDTHS[6]-1.2
        if kept:
            # Preserve the marker's normal position, face and size, then align
            # the ditto in free horizontal space without covering the marker.
            checkpoint=len(commands)
            draw_subregions(current['zones']['bio'],'bio',xs[6],WIDTHS[6],y,only_adult=True)
            occupied=[]
            for kind,args in commands[checkpoint:]:
                if kind=='item' and args[0]=='@':occupied.append((args[1],args[1]+args[3]+.8))
            intervals=[];cursor=x
            for left,right in sorted(occupied):
                if left>cursor:intervals.append((cursor,left-cursor))
                cursor=max(cursor,right)
            if cursor<x+w:intervals.append((cursor,x+w-cursor))
            if not intervals:raise LayoutCapacityError('@ 與同上符號沒有足夠空間')
            x,w=max(intervals,key=lambda interval:interval[1])
        draw_ditto(x,y,w,item_color(config,'DITTO','〃',current,settings,'生化／糞便'))
    def draw_packed(packed,x,w,y):
        size,lanes=packed
        for j,lane in enumerate(lanes):
            center=y+print_geometry.lane_center(j+1,len(lanes),rowh);cursor=x
            for piece in lane:
                position=cursor+piece['padding']/3
                for value,color in piece['runs']:
                    measured=measure_run(item_width,value,size,color);item_text(value,position,center,measured+.01,size,color);position+=measured
                if piece['result']:line(position+min(.3,piece['result']*.2),center+.7,position+piece['result'],center+.7,'#C1C8CD',.25)
                cursor+=piece['width']
    def compact_row(row,y,previous):
        from .compact_layout import pack_segments
        if row['clinic_print']!=previous:
            line(10,y,20,y);identity(row['clinic_print'],0,y,allow_tiny=True)
        work_numbers(row,y,red,force=True)
        visit_dates(row.get('visit_dates',[]),y,force=True)
        draw_patient(row,y,tiny=True)
        # Adult-health @ is a token in biochemical subregion A.
        zones=row['zones']
        for key,col,results in [('bio',6,False),('cbc',7,False),('sendout',8,False),('e411',9,True),('other',10,True)]:
            if key=='bio' and current_ditto['bio']:draw_bio_ditto(y);continue
            items=list(zones[key])
            if key=='sendout' and row.get('notes'):items.append({'label':'備註：'+row['notes']})
            if not items:continue
            w=WIDTHS[col]
            if key=='bio' and not subregions_enabled and not zones['cbc']:
                w+=WIDTHS[7]
                if not zones['sendout'] and not row.get('notes'):w+=WIDTHS[8]
            # Keep normal fixed columns and font sizes wherever that zone fits.
            checkpoint=len(commands);prior_printed=set(printed)
            try:
                if subregions_enabled:draw_subregions(items,key,xs[col],w,y,tiny=True)
                elif key=='bio':biochemistry(items,xs[col],w,y)
                else:stack(items,xs[col],w,y,results,suffix_groups=('hba1c','mab') if key=='other' else (),font_key=key)
            except LayoutCapacityError:
                del commands[checkpoint:];printed.clear();printed.update(prior_printed)
            else:continue
            tokens=[]
            packed_x=xs[col]
            for item in items:
                if subregions_enabled:
                    segments,machines=item_segments(item);printed.update(machines)
                    tokens.append((segments,results or bool(item.get('machines'))));continue
                machine=item.get('machine');segments=[(item['label'],black)]
                if machine and machine not in printed:
                    serial=str(row[machine+'_seq'])+('/' if machine=='mab' else '')
                    serial_color=serial_ink(machine,settings,fonts[key])
                    if machine in ('hba1c','mab'):segments.append((serial,serial_color))
                    else:segments.insert(0,(serial,serial_color))
                    printed.add(machine)
                tokens.append((segments,results))
            packed=pack_segments(tokens,w,rowh,item_width,max_lanes=3,start_size=fonts[key])
            draw_packed(packed,packed_x,w,y)
        line(20,y+rowh,200,y+rowh,red,.6)
        return minimum_font(commands)
    def minimum_font(pending):
        return min(run_size(args[4],args[5]) if kind=='item' else args[4]
                   for kind,args in pending if kind in ('item','text','fit'))
    expanded_counts={4:0,5:0}
    try:
        plans={}
        if fixed_20:
            page_plan=[[dict(index=index,top=body+i*base_rowh,height=base_rowh,needed=base_rowh,oversized=False)
                        for i,index in enumerate(range(start,min(start+20,len(slots))))] for start in range(0,len(slots),20)]
        else:
            for index,current in enumerate(slots):
                if current is not None:
                    try:plans[index]=adaptive_row(current)
                    except LayoutCapacityError as e:raise LayoutCapacityError(f"工作號 {current['workno']}：{e}") from None
            page_plan=adaptive.paginate(slots,[plans[i]['height'] if i in plans else base_rowh for i in range(len(slots))],body,bottom=291,force=force)
        workbook_pages=len(page_plan)
        pages=max(workbook_pages,ac_plan['pages'])
        ditto_flags=ditto.plan(slots,settings,config,[p[0]['index'] for p in page_plan])
        page_plan.extend([[] for _ in range(pages-workbook_pages)])
        for page,entries in enumerate(page_plan):
            chunk=[slots[e['index']] for e in entries]
            glucose_sheet.draw_header(ac_plan,page,fitted_text,line,width)
            text(date,145 if ac_plan['enabled'] else 10,8,32,8)
            if force:text('強制輸出：紅字工作號請核對',10 if ac_plan['enabled'] else 86,8,58,7,red)
            elif draft:text('分組待核對',115,8,28,7,red)
            text(f'{page+1} / {pages}',180,8,20,7)
            if headers:
                for i,h in enumerate(HEADERS):
                    if i==5:continue
                    parts={1:['工作','號'],3:['性','別'],4:['病歷號','保險'],7:['CBC','尿液']}.get(i,[h])
                    inset=VISIT_DATE_WIDTH if i==2 else 0
                    for j,s in enumerate(parts):text(s,xs[i]+.4+inset,body-7+j*3 if len(parts)>1 else body-5.5,WIDTHS[i]-.8-inset,6.8)
                for j,s in enumerate(('就','醫')):text(s,xs[2]+1.2,body-7+j*3,VISIT_DATE_WIDTH-1.2,6.8)
            end=291 if fixed_20 else entries[-1]['top']+entries[-1]['height'] if entries else body
            line(10,body,200,body,lw=.45);line(20,body,20,end,lw=.45)
            if settings.get('show_region_lines',False):
                for boundary in xs[6:11]:line(boundary,body,boundary,end,'#E3E6E9',.3)
            if fixed_20:
                for blank in range(len(entries),20):line(20,body+(blank+1)*base_rowh,200,body+(blank+1)*base_rowh)
            previous=None
            for entry in entries:
                index=entry['index'];y=entry['top'];rowh=entry['height'];line(20,y+rowh,200,y+rowh)
                if slots[index] is None:
                    previous=None
                    continue
                current=slots[index];printed=set();z=current['zones']
                current_ditto=ditto_flags[index]
                adaptive_scale=min(1,rowh/entry['needed'])
                adaptive_reduced=not fixed_20 and any(zplan.get('forced') or g['size']*adaptive_scale<min(7.5,fonts[key])-.001
                    for key,zplan in plans[index]['zones'].items() if zplan for g in zplan['groups'])
                commands=[];previous_before=previous;counts_before=dict(expanded_counts)
                try:
                    if current['clinic_print']!=previous:
                        line(10,y,20,y);identity(current['clinic_print'],0,y);previous=current['clinic_print']
                    work_numbers(current,y,red if entry['oversized'] or adaptive_reduced else black)
                    visit_dates(current.get('visit_dates',[]),y)
                    draw_patient(current,y)
                    # Adult-health @ is rendered with the biochemical tokens.
                    # Borrow contiguous unoccupied areas only. Never borrow result slots.
                    bw=WIDTHS[6]
                    if not z['cbc']:
                        bw+=WIDTHS[7]
                        if not z['sendout'] and not current.get('notes'):bw+=WIDTHS[8]
                    if not fixed_20:
                        for key,col in [('bio',6),('cbc',7),('sendout',8),('e411',9),('other',10)]:
                            if key=='bio' and current_ditto['bio']:draw_bio_ditto(y)
                            else:draw_adaptive_zone(plans[index]['zones'][key],key,col,y,adaptive_scale)
                        if entry['oversized'] or adaptive_reduced:
                            minimum=minimum_font(commands)
                            adjustments.append({'workno':current['workno'],'department':current['department'],
                                'reason':'單筆超過一頁高度或子區域單字寬度不足，已強制縮字','min_font_size':round(minimum,2)})
                            line(20,y+rowh,200,y+rowh,red,.6)
                    elif subregions_enabled:
                        for key,col in [('bio',6),('cbc',7),('sendout',8),('e411',9),('other',10)]:
                            if key=='bio' and current_ditto['bio']:draw_bio_ditto(y)
                            else:draw_subregions(z[key],key,xs[col],WIDTHS[col],y)
                    else:
                        if current_ditto['bio']:draw_bio_ditto(y)
                        else:biochemistry(z['bio'],xs[6],bw,y)
                        stack(z['cbc'],xs[7],WIDTHS[7],y,font_key='cbc')
                        stack(z['sendout'],xs[8],WIDTHS[8],y,font_key='sendout')
                        stack(z['e411'],xs[9],WIDTHS[9],y,True,font_key='e411')
                        stack(z['other'],xs[10],WIDTHS[10],y,True,suffix_groups=('hba1c','mab'),font_key='other')
                    if fixed_20 and current.get('notes'):
                        # Explicit note band is unavailable in fully occupied 3-lane rows.
                        if z['sendout']:raise LayoutCapacityError('備註與外送區相衝，請調整')
                        identity(current['notes'],8,y)
                except LayoutCapacityError as e:
                    if not force:raise LayoutCapacityError(f"工作號 {current['workno']}：{e}") from None
                    commands=[];printed=set();expanded_counts.update(counts_before)
                    minimum=compact_row(current,y,previous_before);previous=current['clinic_print']
                    adjustments.append({'workno':current['workno'],'department':current['department'],'reason':str(e),'min_font_size':round(minimum,2)})
                except ValueError as e:
                    raise ValueError(f"工作號 {current['workno']}：{e}") from None
                pending=commands;commands=None
                for kind,args in pending:{'text':text,'fit':fitted_text,'item':item_text,'line':line}[kind](*args)
            line(10,end,20,end)
            # No footer; use the recovered space for the workbook.
            c.showPage()
        c.save();os.replace(tmp,path)
    except Exception:
        if tmp.exists():tmp.unlink()
        raise
    return {'pages':pages,'workbook_pages':workbook_pages,'glucose_ac':{k:v for k,v in ac_plan.items() if k!='numbers'},'records':len(rows),'rows_per_page':20 if fixed_20 else None,'fixed_20_rows':fixed_20,'row_height_mm':base_rowh if fixed_20 else None,'body_top_mm':body,'biochemistry_expanded_rows':expanded_counts,'reserved_blank_slots':sum(r is None for r in slots),'a4_portrait':True,'show_column_headers':headers,
            'page_counts':[sum(slots[e['index']] is not None for e in p) for p in page_plan],
            'row_layout':[dict(page=n+1,slot=e['index'],top_mm=e['top'],height_mm=e['height'],workno=slots[e['index']]['workno'] if slots[e['index']] is not None else None) for n,p in enumerate(page_plan) for e in p],
            'forced_adjustments':adjustments,'forced_export':force,'font_sizes':fonts,'subregions_enabled':subregions_enabled,
            'sequences':{g:sum(bool(r[g+'_seq']) for r in prepared) for g in ('e411','hba1c','mab')},
            'subregion_columns':fixed_columns,'show_region_lines':bool(settings.get('show_region_lines',False)),
            'machine_serial_style':'superscript' if settings.get('serial_superscript',False) else 'baseline',
            'serial_font_size':float(settings.get('serial_font_size',14)),
            'serial_colors':serial_colors(settings),
            'ditto_alignment':settings.get('ditto_alignment','center'),'ditto_keep_adult':settings.get('ditto_keep_adult',True),
            'latin_font':typefaces.mono_family,
            'ditto_rows':[dict(workno=row['workno'],department=row['department'],**flags)
                          for row,flags in zip(slots,ditto_flags) if row is not None and (flags['bio'] or flags['patient'])]}
