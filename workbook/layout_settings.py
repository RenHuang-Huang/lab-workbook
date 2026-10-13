"""Layout destinations are independent of machine sequence groups (v2 planning)."""
import json, re, os
from pathlib import Path

from .paths import ROOT
PATH=ROOT/'print_settings'/'layout_settings.json'
ZONES=('生化／糞便','CBC／尿液','外送','e411','其他')
GENERATED={'UR18':('uB','CBC／尿液','尿液18項合併'),
           'CBC(7)':('CBC','CBC／尿液','CBC 7項合併'),
           'CBC':('CBC','CBC／尿液','完整CBC合併'),
           'Stool':('Stool','生化／糞便','糞便13項合併'),
           'LFT':('LFT','生化／糞便','已驗證肝功能套組合併'),
           'SMA':('SMA','生化／糞便','已驗證SMA套組合併')}

def generated_definitions(catalog=None):
    from .core import CBC_DETAIL_CODES
    import re
    urine=max(18,len({i['LCI_ID'] for i in (catalog or {}).get('items',[]) if re.fullmatch(r'U\d{2}',str(i['LCI_ID']))}))
    rows={f'UR{n}':(f'UR{n}','CBC／尿液',f'尿液{n}項合併') for n in range(5,urine+1)}
    rows.update({f'CBC({n})':(f'CBC({n})','CBC／尿液',f'CBC {n}項合併') for n in range(4,len(CBC_DETAIL_CODES)+1)})
    rows.update(GENERATED);return rows
SENDOUT=['K','TIBC','Na','Cortisol','CPK','Ca153','Ca125','Cl','IgE','VDRL','Ca 72-4','Free-PSA','Ca','P','Vit.D','Cholinesterase','Mg','Lipase','B12','FSH','E2','PIVKA-II','過敏原','HAV IgM','AIDS','HAV IgG','Anti-HBe','CA19-9']
ALIASES={'K':['Potassium'],'Na':['Sodium'],'Cl':['Chloride'],'Ca':['Calcium'],'P':['Phosphorus'],'Mg':['Magnesium'],
 'Ca153':['CA15-3','CA 15-3'],'Ca125':['CA-125','CA 125'],'Ca 72-4':['CA72-4'],
 'Free-PSA':['Free PSA'],'Vit.D':['25-OH Vitamin D'],'B12':['Vitamin B12'],
 'PIVKA-II':['PIVKA II'],'Anti-HBe':['Anti HBe'],'CA19-9':['CA-19-9','CA19-09','CA-199']}

def normalize(value):
    return re.sub(r'[\s.\-_/]','',str(value)).casefold()

def defaults():
    return {'version':2,'updated_at':None,'item_updated_at':{},'status':'已接入三小列PDF',
            'rules':[{'label':name,'aliases':[name,*ALIASES.get(name,[])],'codes':['710','7101'] if name=='CA19-9' else [],
                      'zone':'生化／糞便' if name=='Lipase' else '外送','enabled':True,'source':'使用者2026-10-13指定' if name=='Lipase' else '使用者2026-09-20指定'} for name in SENDOUT]}

def load():
    return json.loads(PATH.read_text(encoding='utf-8')) if PATH.exists() else defaults()

def validate(data):
    from .settings_history import validate as validate_history
    validate_history(data)
    from .subregions import validate as validate_positions
    validate_positions(data)
    from .print_style import color
    if not isinstance(data.get('code_colors',{}),dict):raise ValueError('代碼顏色設定格式不正確。')
    for key,value in data.get('code_colors',{}).items():
        if not isinstance(key,str) or not key:raise ValueError('代碼顏色的項目代碼不可空白。')
        color(value)
    used={}
    for i,r in enumerate(data['rules']):
        if not r['label'].strip() or r['zone'] not in ZONES:raise ValueError('名稱不可空白，區域須從列表選擇。')
        if not isinstance(r.get('enabled'),bool):raise ValueError('啟用設定格式錯誤。')
        if not r['enabled']:continue
        keys=[('alias',normalize(a)) for a in r['aliases'] if normalize(a)]+[('code',str(c).strip()) for c in r['codes'] if str(c).strip()]
        for key in set(keys):
            if key in used:raise ValueError('同一名稱別名或代碼不可同時套用兩條啟用規則。')
            used[key]=i
    return data

def save(data):
    validate(data)
    temp=PATH.with_suffix('.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(temp,PATH)

def matcher(data):
    """Validate once and index reusable rules for a whole catalog or export."""
    validate(data)
    rules=[r for r in data['rules'] if r['enabled']]
    codes={str(code).strip():rule for rule in rules for code in rule['codes'] if str(code).strip()}
    aliases={normalize(alias):index for index,rule in enumerate(rules) for alias in rule['aliases'] if normalize(alias)}
    def resolve(item):
        code=str(item.get('LCI_ID','')).strip()
        if code in codes:return codes[code]
        names={normalize(item.get(k) or '') for k in ('LCI_NAME','LCI_NAMEC','LCI_NAMES')}-{''}
        hit={aliases[name] for name in names if name in aliases}
        if len(hit)>1:raise ValueError('同一項目命中多個區域，請以明確代碼核對。')
        return rules[next(iter(hit))] if hit else None
    return resolve


def match(item,data):
    """Explicit codes have priority. Exact normalized aliases only; no substrings."""
    return matcher(data)(item)

def editor(parent):
    import tkinter as tk
    from tkinter import ttk,messagebox
    data=load();win=tk.Toplevel(parent);win.title('版面／外送設定');win.geometry('970x690');win.transient(parent);win.grab_set()
    ttk.Label(win,text='新版列印區域設定：可新增、停用、改區域；下次匯出套用。不改機器分組；結果列仍保留原機器序號。',wraplength=930).pack(padx=12,pady=10)
    tree=ttk.Treeview(win,columns=('label','zone','enabled','aliases','codes'),show='headings',selectmode='browse')
    for key,title,width in [('label','列印簡稱',120),('zone','區域',90),('enabled','啟用',50),('aliases','名稱別名（精確比對）',330),('codes','已核對代碼',170)]:tree.heading(key,text=title);tree.column(key,width=width)
    tree.pack(fill='both',expand=True,padx=12)
    form=ttk.Frame(win,padding=12);form.pack(fill='x');variables={}
    for i,(key,title) in enumerate([('label','列印簡稱'),('zone','區域'),('aliases','名稱別名，用 | 分隔'),('codes','明確項目代碼，用 | 分隔')]):
        ttk.Label(form,text=title).grid(row=i,column=0,sticky='w');v=tk.StringVar();variables[key]=v
        widget=ttk.Combobox(form,textvariable=v,values=ZONES,state='readonly') if key=='zone' else ttk.Entry(form,textvariable=v)
        widget.grid(row=i,column=1,sticky='ew',pady=3)
    variables['zone'].set('外送');enabled=tk.BooleanVar(value=True);ttk.Checkbutton(form,text='啟用',variable=enabled).grid(row=4,column=1,sticky='w');form.columnconfigure(1,weight=1)
    selected=[None]
    def populate():
        tree.delete(*tree.get_children())
        for i,r in enumerate(data['rules']):tree.insert('','end',iid=str(i),values=(r['label'],r['zone'],'是' if r['enabled'] else '否',' | '.join(r['aliases']),' | '.join(r['codes'])))
    def pick(*_):
        if not tree.selection():return
        selected[0]=int(tree.selection()[0]);r=data['rules'][selected[0]]
        for k,v in variables.items():v.set(' | '.join(r[k]) if isinstance(r[k],list) else r[k])
        enabled.set(r['enabled'])
    def fresh():
        selected[0]=None;tree.selection_remove(*tree.selection())
        for v in variables.values():v.set('')
        variables['zone'].set('外送');enabled.set(True)
    def apply():
        import copy
        candidate=copy.deepcopy(data)
        r={k:v.get().strip() for k,v in variables.items()}
        for k in ('aliases','codes'):r[k]=[s.strip() for s in r[k].split('|') if s.strip()]
        if r['label'] not in r['aliases']:r['aliases'].insert(0,r['label'])
        r.update(enabled=enabled.get(),source='使用者設定')
        if selected[0] is None:candidate['rules'].append(r)
        else:candidate['rules'][selected[0]]=r
        try:save(candidate)
        except (ValueError,OSError) as e:messagebox.showerror('未儲存',str(e),parent=win);return
        data.clear();data.update(candidate);populate();fresh()
        status.set('已儲存在本機；下次開啟仍保留。機器分組設定未變更。')
    tree.bind('<<TreeviewSelect>>',pick)
    buttons=ttk.Frame(win);buttons.pack(pady=8)
    ttk.Button(buttons,text='新增一項',command=fresh).pack(side='left',padx=8)
    ttk.Button(buttons,text='儲存本項設定',command=apply).pack(side='left',padx=8)
    ttk.Button(buttons,text='關閉',command=win.destroy).pack(side='left',padx=8)
    status=tk.StringVar(value='別名採精確比對。套組簡稱使用 G:套組代碼（例如 G:047405）；只合併該筆已登錄套組的現有成員，不補缺項。')
    ttk.Label(win,textvariable=status,wraplength=930).pack(padx=12,pady=10);populate()
    return win

if __name__=='__main__':
    import tkinter as tk
    root=tk.Tk();root.withdraw();win=editor(root);root.wait_window(win);root.destroy()
