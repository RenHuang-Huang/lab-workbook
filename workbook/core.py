from __future__ import annotations
import copy, datetime as dt, hashlib, json, math, os, re, shutil, subprocess, tempfile
from collections import defaultdict
from pathlib import Path

from .paths import ROOT
CONFIG=ROOT/'print_settings'/'settings.json'
GROUPS=('routine','e411','hba1c','mab','aux')
CBC_DETAIL_CODES={'B02','B04','B10','B24','B38','B39','B40','B43','B721','B722','B723','B731','B732','B733','B741','B742','B743','B745'}
CBC_DETAIL_CODES |= {'B8021','B8022','B8031','B8032','B8041','B8042','B8051','B8052','B8061','B8062','B8066'}
STOOL_DETAIL_CODES={'S01','S02','S04','S06','S08','S10','S11','S12','S14','S15','S16','S18','S20'}
GROUP_NAMES={'routine':'常規／其他','e411':'e411','hba1c':'HbA1c','mab':'mab','aux':'計算／行政'}

def load_json(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def save_json(path,data):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    temp=p.with_suffix(p.suffix+'.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(temp,p)

def default_settings():
    from .font_settings import DEFAULTS
    from .print_style import default_color_rules
    from .merge_settings import DEFAULT_EXCLUSIONS
    rules={}
    aliases={'0921':'AC','101':'OT','102':'PT','204':'cre','206':'UA','202':'BUN','301':'TG','302':'CHO','3061':'HDL','307':'LDL','3072':'LDL(calc)','111':'TP','112':'Alb','342':'Fe','344':'TIBC','208':'U-cre','210':'UTP','2101':'U-PCR','2102':'U-ACR'}
    for code,label in aliases.items():rules[code]={'group':'routine','label':label}
    for code in ['096','0961']:rules[code]={'group':'hba1c','label':'HbA1c'}
    rules['205']={'group':'mab','label':'mab'}
    # Candidates from the reference photograph. Operator can edit every assignment.
    for code,label in {'136':'sAg','1361':'sAg','151':'HCV','1511':'HCV','347':'Ferritin','3471':'Ferritin','4021':'T3','4031':'FT4','4041':'T4','4061':'TSH','702':'AFP(舊)','7021':'AFP','7041':'CEA','7121':'PSA'}.items():
        rules[code]={'group':'e411','label':label}
    for code in ['2104','308','113','114','U981','U982','U983','U984','U985','U986']:
        rules[code]={'group':'aux','label':''}
    for code in ('138','1381'):rules[code]={'group':'e411','label':'eAg'}
    return {'version':1,'mapping_confirmed':False,'show_column_headers':False,'fixed_20_rows':True,'ditto_bio':True,'ditto_patient':True,
            'show_region_lines':False,'export_glucose_ac':True,'glucose_ac_columns':5,
            'merged_color_enabled':True,'merged_color':'#7042A6','ditto_font_size':14,'ditto_bold':False,'print_color_rules':default_color_rules(),
            'merged_order_colors':['#202830','#215CAE','#215CAE','#215CAE'],
            'merge_exclusions_enabled':True,'merge_excluded_worknos':list(DEFAULT_EXCLUSIONS),
            'rules':rules,'font_path':'C:/Windows/Fonts/msjh.ttc','font_sizes':dict(DEFAULTS)}

def get_settings():
    from .config_store import print_only
    result=default_settings()
    if CONFIG.exists():result.update(print_only(load_json(CONFIG)))
    return result

def save_print_settings(settings,path=None):
    from .config_store import print_only
    save_json(CONFIG if path is None else path,print_only(settings))
def sort_work(s):
    s=str(s or '');return (0,int(s),s) if s.isdigit() else (1,0,s)

def read_access(database,date,include_identity=True):
    day=dt.date.fromisoformat(date)
    database=Path(database).resolve()
    if not database.is_file():raise ValueError('找不到 Access 檔案。')
    before=(database.stat().st_size,database.stat().st_mtime_ns)
    with tempfile.TemporaryDirectory(prefix='lab_workbook_') as folder:
        target=Path(folder)/'local.json'
        from .access_runtime import read_bridge
        args=['-Date',day.isoformat(),'-Output',str(target)]
        if include_identity:args.append('-IncludeIdentity')
        read_bridge(database,'access_bridge.ps1',args,180)
        if not target.exists():raise ValueError('擷取程序未建立資料檔，請查看連線診斷。')
        data=load_json(target)
    after=(database.stat().st_size,database.stat().st_mtime_ns)
    if before!=after:raise ValueError('讀取期間來源資料庫有變動，請使用穩定備份重新匯入。')
    data['source_file']=str(database);data['extracted_at']=dt.datetime.now().isoformat(timespec='seconds')
    return data

def check_connection(database):
    from .access_runtime import diagnose,describe
    result=diagnose(database)
    return result['ok'],describe(result)


def read_catalog(database):
    from .access_runtime import read_bridge
    with tempfile.TemporaryDirectory(prefix='lab_catalog_') as folder:
        target=Path(folder)/'catalog.json'
        read_bridge(database,'catalog_bridge.ps1',['-Output',str(target)],60)
        if not target.exists():raise ValueError('字典擷取程序未建立資料檔，請查看連線診斷。')
        return load_json(target)


def safe_fixture(date='2026-08-29'):
    demo=ROOT/'assets'/'demo.json'
    if demo.exists():return load_json(demo)
    p=load_json(ROOT/'analysis'/'safe_profile.json')
    s=load_json(ROOT/'output'/f'{date}.safe.json')
    return {'date':date,'headers':s['headers'],'details':s['details'],'items':p['items'],'hospitals':p['hospitals'],'sets':p['set_headers'],'set_members':p['set_items'],'identity_local_only':False,'extracted_at':s.get('extracted_at',''),'source_file':'不含身分的測試資料'}

def display_label(code,items,rule):
    item=items.get(code,{})
    return str(rule.get('label') or item.get('LCI_NAMES') or item.get('LCI_NAME') or item.get('LCI_NAMEC') or f'[{code}]').strip()

def make_rows(data,settings):
    if settings.get('order_mode','split')=='merge':
        from .merging import merge_rows
        return merge_rows(data,settings)
    from . import layout_settings
    from .visit_dates import row_dates
    layout=settings.get('layout') or layout_settings.load()
    layout_cache={};match_rule=layout_settings.matcher(layout)
    def layout_override(code):
        if code not in layout_cache:layout_cache[code]=match_rule(items.get(code,{'LCI_ID':code}))
        return layout_cache[code]
    items={i['LCI_ID']:i for i in data['items']}
    hospitals={h['HOS_ID']:h.get('HOS_NAME') or h['HOS_ID'] for h in data['hospitals']}
    hospitals.update(layout.get('clinic_aliases',{}))
    panels=defaultdict(list);members=defaultdict(set)
    for p in data.get('sets',[]):panels[p['LCS_ID']].append(p)
    for p in data.get('set_members',[]):members[p['LCS_UNIKEY']].add(p['LCS_ITEM'])
    details=defaultdict(list);seen=set();result=[]
    adult_keys={(r.get('LCHK_DEPT') or '',r['LCHK_WORKNO']) for r in data.get('adult_health',[])}
    for d in data['details']:details[(d.get('LCHK_DEPT') or '',d['LCHK_WORKNO'])].append(d)
    for h in sorted(data['headers'],key=lambda x:(x.get('LCHK_DEPT') or '',sort_work(x['LCHK_WORKNO']))):
        key=(h.get('LCHK_DEPT') or '',h['LCHK_WORKNO'])
        if not key[1] or key in seen:raise ValueError('主工作號缺漏或同部門有重複，停止合併；請先檢查資料。')
        seen.add(key)
        row={'key':'|'.join(key),'department':key[0],'workno':key[1],'clinic':hospitals.get(h['LCHK_SOURCE'],h['LCHK_SOURCE'] or '未指定'),
             'clinic_code':h.get('LCHK_SOURCE') or '',
             'patient_identity_present':bool(str(h.get('LCHK_PATNAME') or '').strip()),
             'name':h.get('LCHK_PATNAME') or ('測試個案' if not data.get('identity_local_only') else '未填姓名'),
             'sex':h.get('LCHK_SEX') or '', 'birth':h.get('LCHK_BDAYS') or '',
             'chart_number':h.get('CHART_NUMBER') or '', 'insurance_label':h.get('INSURANCE_LABEL') or '',
             'edited':False,'notes':'','source_items':[],
             'routine':[],'e411':[],'hba1c':[],'mab':[],'aux':[]}
        try:row.update(row_dates(h,data['date']))
        except ValueError as e:raise ValueError(f"工作號 {key[1]}：{e}") from None
        local=details[key]; singles=[d for d in local if d['LCHK_ITEMTYPE']=='I']
        # None distinguishes older snapshots that never queried the card-prefix flag.
        row['adult_health_flag']=(key in adult_keys) if 'adult_health' in data else None
        codes={d['LCHK_ITEM'] for d in singles}
        row['verified_panels']=[]
        row['ordered_panels']=[]
        row['unresolved_panels']=[]
        for d in local:
            if d['LCHK_ITEMTYPE']!='G':continue
            options=panels[d['LCHK_ITEM']]
            exact=[p for p in options if p.get('LCS_HOSPITAL')==h['LCHK_SOURCE']]
            fallback=[p for p in options if p.get('LCS_HOSPITAL')=='9999']
            chosen=exact if exact else fallback if fallback else options
            if len(chosen)==1:
                p=chosen[0];pcs=members[p['LCS_UNIKEY']]
                row['ordered_panels'].append({'code':d['LCHK_ITEM'],'name':p['LCS_NAME'],
                    'source_orders':copy.deepcopy(d.get('source_orders') or [dict(department=key[0],workno=key[1])]),
                    'present_members':sorted(codes & pcs),
                    'missing_members':sorted(pcs-codes,key=str)})
                if pcs and pcs<=codes:row['verified_panels'].append({'code':d['LCHK_ITEM'],'name':p['LCS_NAME'],'members':sorted(pcs)})
            else:row['unresolved_panels'].append(d['LCHK_ITEM'])
        cbc={'B02','B04','B10','B24','B38','B39','B40','B43'}
        # Compress only whole observed sets, without adding tests.
        compressed=set()
        legacy=layout.get('version',2)<3
        if legacy and STOOL_DETAIL_CODES<=codes and all(settings['rules'].get(c,{}).get('group','routine')=='routine' and not layout_override(c) for c in STOOL_DETAIL_CODES):
            row['routine'].append('糞便(13項)');compressed |= STOOL_DETAIL_CODES
        blood=codes & CBC_DETAIL_CODES
        if legacy and len(blood)>=4 and all(settings['rules'].get(c,{}).get('group','routine')=='routine' and not layout_override(c) for c in blood):
            row['routine'].append('CBC' if blood==cbc else f'CBC({len(blood)})');compressed |= blood
        urine={c for c in codes if re.fullmatch(r'U\d{2}',c)}
        if legacy and len(urine)>=5 and all(settings['rules'].get(c,{}).get('group','routine')=='routine' and not layout_override(c) for c in urine):
            row['routine'].append(f'尿液({len(urine)}項)');compressed |= urine
        for d in local:
            code=d['LCHK_ITEM']; kind=d['LCHK_ITEMTYPE']
            if kind=='G':continue  # Already-expanded single items are authoritative.
            rule=settings['rules'].get(code,{'group':'routine'})
            label=display_label(code,items,rule)
            row['source_items'].append({'code':code,'type':kind,'label':label,'name':items.get(code,{}).get('LCI_NAME') or '', 'namec':items.get(code,{}).get('LCI_NAMEC') or '',**({'source_orders':d['source_orders']} if 'source_orders' in d else {})})
            if code in compressed:continue
            group=rule.get('group','routine')
            if group not in GROUPS:raise ValueError(f'項目 {code} 的分組設定不正確。')
            if kind!='I':label=f'[{kind}:{code}] {label}'
            if label not in row[group]:row[group].append(label)
        if not singles:
            # Never silently omit group-only orders.
            row['routine'] += [f'套組待核:{d["LCHK_ITEM"]}' for d in local if d['LCHK_ITEMTYPE']=='G']
        for g in GROUPS:row[g]=' / '.join(row[g])
        if not local:row['notes']='無項目明細，請核對'
        result.append(row)
    if set(details)-seen:raise ValueError('有無法對應主檔的明細，停止匯出。')
    return number_rows(result)

def number_rows(rows):
    counts={'e411':0,'hba1c':0,'mab':0}
    for r in rows:
        for g in counts:
            if r[g].strip():counts[g]+=1;r[g+'_seq']=counts[g]
            else:r[g+'_seq']=None
    return rows

def mapping_fingerprint(settings):
    return hashlib.sha256(json.dumps(settings,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:12]

def export_pdf_legacy(path,rows,date,settings,draft=False):
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    if not rows:raise ValueError('當日沒有資料。')
    font=Path(settings.get('font_path','C:/Windows/Fonts/msjh.ttc'))
    if not font.is_file():raise ValueError('找不到中文字型，請在設定中指定 TrueType 字型。')
    if 'LabCJK' not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont('LabCJK',str(font),subfontIndex=0))
    number_rows(rows)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.partial.pdf')
    c=canvas.Canvas(str(tmp),pagesize=A4,pageCompression=1)
    c.setTitle(f'檢驗工作簿 {date}');c.setAuthor('工作簿輸出（本機）')
    width,height=A4;left=10*mm;top=height-27*mm;rowh=12.4*mm;head=8*mm
    widths=[12,17,29,59,35,16,22];xs=[left]
    for w in widths:xs.append(xs[-1]+w*mm)
    red='#B02631';blue='#215CAE';black='#202830';gray='#64717D'
    pages=math.ceil(len(rows)/20);stamp=dt.datetime.now().strftime('%m/%d %H:%M')
    multiple_departments=len({r['department'] for r in rows})>1
    def txt(x,y,t,size=9,color=black):
        c.setFillColor(color);c.setFont('LabCJK',size);c.drawString(x,y,str(t))
    def wrap(text,limit,size):
        lines=[]
        for para in str(text).split('\n'):
            line=''
            tokens=re.findall(r'[A-Za-z0-9][A-Za-z0-9().+_-]*|[^\x00-\x7f]|[ \t]+|.',para)
            for token in tokens:
                if pdfmetrics.stringWidth(token,'LabCJK',size)>limit:
                    for ch in token:
                        if line and pdfmetrics.stringWidth(line+ch,'LabCJK',size)>limit:lines.append(line.rstrip());line=ch
                        else:line+=ch
                elif line and pdfmetrics.stringWidth(line+token,'LabCJK',size)>limit:
                    lines.append(line.rstrip());line=token.lstrip()
                else:line+=token
            lines.append(line.rstrip())
        return lines
    def cell(text,col,y,available=rowh,size=8.5,color=black,max_lines=None):
        limit=(xs[col+1]-xs[col])-4*mm
        for candidate in [size,8,7.5,7,6.5]:
            if candidate>size:continue
            lines=wrap(text,limit,candidate);leading=candidate*1.17
            if len(lines)*leading<=available-3*mm and (max_lines is None or len(lines)<=max_lines):break
        else:raise ValueError('某列內容超過 A4 每頁20筆可容納的空間。請縮短該列顯示簡稱；原始明細仍保留。')
        for j,line in enumerate(lines):txt(xs[col]+2*mm,y-2.4*mm-candidate-j*leading,line,candidate,color)
    try:
        for page in range(pages):
            chunk=rows[page*20:(page+1)*20]
            txt(left,height-13*mm,'檢驗工作簿',16)
            txt(left+52*mm,height-13*mm,date,12)
            txt(left,height-20*mm,'每頁20筆 · 主工作號依系統保留 · 空白處填寫檢驗結果',8,gray)
            txt(left+127*mm,height-13*mm,f'第 {page+1} / {pages} 頁',10)
            txt(left+127*mm,height-20*mm,'分組待核對 / 範例' if draft else '工作前清單',8,red if draft else gray)
            c.setFillColor('#EFF3F6');c.rect(left,top-head,xs[-1]-left,head,fill=1,stroke=0)
            headers=['工作號','診所','姓名／性別／生日','常規／其他項目','e411（兩台共用）','HbA1c','mab']
            for i,label in enumerate(headers):txt(xs[i]+1.5*mm,top-5*mm,label,8,red if i in (4,6) else blue if i==5 else black)
            bodytop=top-head
            for i in range(20):
                y=bodytop-i*rowh
                c.setStrokeColor('#AAB4BD');c.setLineWidth(.35);c.line(left,y-rowh,xs[-1],y-rowh)
                if i>=len(chunk):continue
                r=chunk[i]
                cell(str(int(r['workno'])) if r['workno'].isdigit() else r['workno'],0,y,size=9)
                cell(r['clinic'],1,y,size=8)
                identity=r['name']+'\n'+' '.join(str(v) for v in [r['sex'],r['birth']] if v)
                if multiple_departments:identity+='\n部門 '+r['department']
                cell(identity,2,y,size=9)
                routine=r['routine']
                if r['notes']:routine+='\n註：'+r['notes']
                if r['edited']:routine+=' *'
                cell(routine,3,y,size=8.5)
                for col,g,color in [(4,'e411',red),(5,'hba1c',blue),(6,'mab',red)]:
                    if not r[g]:continue
                    seq=str(r[g+'_seq'])+('/' if g=='mab' else '')
                    txt(xs[col]+1.6*mm,y-3.8*mm,seq,9.5,color)
                    if g=='e411':
                        tests=r[g].split(' / ')
                        if len(tests)>4:raise ValueError('單筆 e411 超過4個顯示項目，請縮短合併顯示簡稱後再輸出。')
                        size=8 if len(tests)<=3 else 6.5
                        leading=(rowh-2.4*mm)/max(3,len(tests))
                        for j,test in enumerate(tests):
                            # Reserve at least 8 mm after each item for its own handwritten result.
                            available=xs[col+1]-xs[col]-10*mm
                            if pdfmetrics.stringWidth(test,'LabCJK',size)>available-8*mm:
                                raise ValueError('e411簡稱過長，請縮短以保留每項結果的手寫空間。')
                            yy=y-3.8*mm-j*leading
                            xx=xs[col]+7*mm
                            txt(xx,yy,test,size)
                            c.setStrokeColor('#CCD3D9');c.setLineWidth(.25)
                            c.line(xx+pdfmetrics.stringWidth(test,'LabCJK',size)+1*mm,yy-.3*mm,xs[col+1]-2*mm,yy-.3*mm)
                        continue
                    # Item names sit below the number; right side/remaining lines stay writable.
                    label='' if (g=='hba1c' and r[g]=='HbA1c') or (g=='mab' and r[g]=='mab') else r[g]
                    if label:cell(label,col,y-3.5*mm,available=rowh-3.5*mm,size=7.5,color=black)
                    c.setStrokeColor('#CCD3D9');c.setLineWidth(.25)
                    c.line(xs[col]+8*mm,y-4*mm,xs[col+1]-2*mm,y-4*mm)
            bottom=bodytop-20*rowh
            c.setStrokeColor('#7A8995');c.setLineWidth(.45)
            for x in xs:c.line(x,top,x,bottom)
            c.line(left,top,xs[-1],top);c.line(left,bodytop,xs[-1],bodytop)
            txt(left,10*mm,f'本頁 {len(chunk)} 筆 / 全日 {len(rows)} 筆   ·   匯出 {stamp}   ·   * 人工調整   ·   完整項目見同名工作進度',7,gray)
            txt(left,6*mm,f'設定版本 {mapping_fingerprint(settings)}   ·   e411 紅 / HbA1c 藍 / mab 紅色斜線號',7,gray)
            c.showPage()
        c.save();os.replace(tmp,path)
    except Exception:
        if tmp.exists():tmp.unlink()
        raise
    return {'pages':pages,'records':len(rows),'rows_per_page':20,'a4_portrait':True,
            'sequences':{g:sum(bool(r[g].strip()) for r in rows) for g in ['e411','hba1c','mab']}}

def export_pdf(path,rows,date,settings,draft=False):
    from .handwritten import export
    return export(path,rows,date,settings,draft)

def save_session(path,data,rows,settings,export_summary=None):
    session={'app_version':1,'chart_source_policy':2,'data':data,'rows':rows,'settings':settings,'saved_at':dt.datetime.now().isoformat()}
    if export_summary is not None:session['export_summary']=export_summary
    save_json(path,session)

def retire_legacy_chart_source(session):
    """Clear rejected imported values in old sessions, preserving distinct manual edits."""
    if session.get('chart_source_policy',0)>=2:return
    imported={((h.get('LCHK_DEPT') or '')+'|'+h['LCHK_WORKNO']):h.get('CHART_NUMBER') for h in session['data']['headers']}
    for row in session['rows']:
        if row.get('chart_number')==imported.get(row['key']):row['chart_number']=''
    for header in session['data']['headers']:header['CHART_NUMBER']=''
    session['chart_source_policy']=2
