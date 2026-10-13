"""Read-only panel lookup from the local dictionary, never from patient orders."""
from .catalog_table import natural_key


def definitions(catalog,record,rows):
    """Keep clinic-specific definitions separate and retain unresolved members."""
    panels=[p for p in catalog.get('sets',[]) if str(p.get('LCS_ID') or '')==record['code']]
    uid=record.get('definition_id')
    if uid is not None and str(uid).strip():
        panels=[p for p in panels if str(p.get('LCS_UNIKEY'))==str(uid)]
    singles={r['code']:r for r in rows if r.get('kind')=='單項'}
    clinics={str(h.get('HOS_ID')):h.get('HOS_NAME') or '' for h in catalog.get('hospitals',[])}
    result=[]
    for panel in panels:
        uid=panel.get('LCS_UNIKEY');known=uid is not None and bool(str(uid).strip())
        source=[m for m in catalog.get('set_members',[]) if known and str(m.get('LCS_UNIKEY'))==str(uid)]
        source.sort(key=lambda m:(m.get('LCS_SERIAL') in (None,''),natural_key(m.get('LCS_SERIAL') or '')))
        members=[]
        for index,member in enumerate(source):
            code=str(member.get('LCS_ITEM') or '');single=singles.get(code)
            members.append(dict(key=str(index),order=member.get('LCS_SERIAL') if member.get('LCS_SERIAL') is not None else '',
                code=code,name=single['name'] if single else '未在單項字典找到',
                nhi=single.get('nhi','') if single else '',label=single.get('label','') if single else '',
                zone=single.get('zone','') if single else '待核對',group=single.get('group','') if single else '待核對',
                print_state=single.get('print_state','') if single else '待核對',found=single is not None))
        clinic=str(panel.get('LCS_HOSPITAL') or '')
        result.append(dict(name=panel.get('LCS_NAME') or record['name'],definition_id=uid,
            clinic=(clinic+' '+clinics.get(clinic,'')).strip() or '全部診所',known=known,members=members,
            unique_count=len({m['code'] for m in members if m['code']}),missing_count=sum(not m['found'] for m in members)))
    return result


def show(parent,record,catalog,rows):
    import tkinter as tk
    from tkinter import ttk
    from .catalog_table import CatalogTable
    variants=definitions(catalog,record,rows)
    win=tk.Toplevel(parent);win.title('套組子項｜'+record['code']+' '+record['name'])
    win.geometry('1000x640');win.minsize(820,560);win.transient(parent.winfo_toplevel())
    body=ttk.Frame(win,padding=16);body.pack(fill='both',expand=True)
    title=ttk.Label(body,text=record['code']+'  '+record['name'],style='PageTitle.TLabel',wraplength=940)
    title.pack(anchor='w',pady=(0,8))
    choice=ttk.Combobox(body,state='readonly',values=[f"{p['clinic']} · {p['name']} · 定義 {p['definition_id'] or '未提供'}" for p in variants])
    if len(variants)>1:choice.pack(fill='x',pady=(0,8))
    win.summary_var=tk.StringVar();ttk.Label(body,textvariable=win.summary_var,font=('Microsoft JhengHei UI',14,'bold')).pack(anchor='w',pady=(0,6))
    note=tk.StringVar();label=ttk.Label(body,textvariable=note,wraplength=940);label.pack(fill='x',pady=(0,12))
    body.bind('<Configure>',lambda e:(label.configure(wraplength=max(200,e.width-32)),title.configure(wraplength=max(200,e.width-32))))
    ttk.Button(body,text='關閉',command=win.destroy).pack(side='bottom',anchor='e',pady=(12,0))
    holder=ttk.Frame(body);holder.pack(fill='both',expand=True)
    table=CatalogTable(holder,[('order','順序',75),('code','單項代碼',110),('nhi','健保代碼',120),
        ('name','項目名稱',250),('label','列印代碼',130),('zone','列印區域',150),
        ('group','流水號分組',160),('print_state','單項列印',110)],lambda _:None)
    win.member_table=table;win.definition_choice=choice
    def refresh(*_):
        table.clear_filters()
        panel=variants[max(0,choice.current())] if variants else None
        members=panel['members'] if panel else []
        if panel and panel['known']:
            win.summary_var.set(f"共 {len(members)} 筆子項（{panel['unique_count']} 個不同代碼）")
            note.set(f"適用：{panel['clinic']}。依本機 JSON 套組定義顯示；停印與編流水號的子項皆保留。"+
                (f" {panel['missing_count']} 筆找不到單項定義，保留代碼待核對。" if panel['missing_count'] else ''))
        else:
            win.summary_var.set('無法確認子項數量')
            note.set('本機清單缺少套組定義或定義識別碼，請從資料庫更新清單後重試。')
        table.set_rows(members)
    choice.bind('<<ComboboxSelected>>',refresh)
    if variants:choice.current(0)
    refresh();win.bind('<Escape>',lambda _:win.destroy());return win
