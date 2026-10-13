"""Pending dictionary edits, validated and committed as one transaction."""
import copy

FIELD_NAMES={'label':'列印代碼／簡稱','zone':'列印區域','group':'流水號分組',
    'print_enabled':'是否列印','subregion':'子區域','position':'位置','position_mode':'位置模式',
    'code_color':'代碼顏色','display':'顯示設定','compact_subregions':'子區域遞補',
    'compact_positions':'位置遞補','bio_auto_start':'生化自動起始區'}


class DraftError(ValueError):
    def __init__(self,mode,key,message):
        self.mode=mode;self.key=key
        super().__init__(message)


def shown(value):
    if isinstance(value,bool):return '是' if value else '否'
    if value in ('',None):return '（空白）'
    return {'slot':'固定位置','order':'排列順位'}.get(str(value),str(value))


class Drafts:
    def __init__(self):self.changes={}
    def put(self,mode,record,before,after):
        key=(mode,record['key'])
        if before==after:self.changes.pop(key,None)
        else:self.changes[key]=dict(record=copy.deepcopy(record),before=copy.deepcopy(before),after=copy.deepcopy(after))
    def get(self,mode,key):return self.changes.get((mode,key))
    def details(self):
        lines=[]
        for (mode,key),edit in self.changes.items():
            record=edit['record'];fields=[]
            for field,value in edit['after'].items():
                if value!=edit['before'].get(field):
                    fields.append(f"  {FIELD_NAMES[field]}：{shown(edit['before'].get(field))} → {shown(value)}")
            if mode=='automatic':title='生化／糞便：自動起始區'
            elif mode=='subregions':title=f"{record['zone']} · 子區域 {record['subregion_display']}"
            else:title=f"{record.get('kind','診所')} {record.get('code',key)}  {record.get('name','')}"
            lines.append(title+'\n'+'\n'.join(fields))
        return '\n\n'.join(lines)
    def prepare(self,settings,layout):
        from .catalog_settings import edit_item,MACHINE_NAMES
        from . import subregions as sr,print_style as ps,layout_settings as ls
        candidate=copy.deepcopy(settings);updated=copy.deepcopy(layout)
        for (mode,key),edit in self.changes.items():
            record=edit['record'];values=edit['after']
            try:
                if mode=='clinics':
                    label=values['label'].strip()
                    if not label:raise ValueError('診所列印簡稱不可空白。')
                    updated.setdefault('clinic_aliases',{})[key]=label
                elif mode=='items':
                    group=next((k for k,v in MACHINE_NAMES.items() if v==values['group']),None) if record['kind']=='單項' else None
                    # aux stays internal and nonprinting unless the user explicitly enables it.
                    if record.get('machine_group')=='aux' and group=='routine' and not values['print_enabled']:group='aux'
                    position=None if values['position']=='自動' else int(values['position'])
                    if position is not None and position>10 and values['position']!=edit['before']['position']:
                        raise ValueError('新設定的位置請選 1～10 或自動。')
                    candidate,updated=edit_item(candidate,updated,record,values['label'],values['zone'],group,
                        print_enabled=values['print_enabled'],subregion='' if values['subregion']=='自動' else values['subregion'],
                        position=position,position_mode=values['position_mode'],code_color=ps.choice(values['code_color']))
                elif mode=='subregions':
                    updated['subregions'][record['zone']][record['subregion_display']]=dict(
                        display=next(k for k,v in sr.MODES.items() if v==values['display']),
                        compact_subregions=values['compact_subregions'],compact_positions=values['compact_positions'])
                elif mode=='automatic':updated['bio_auto_start']=values['bio_auto_start']
                ls.validate(updated)
            except (ValueError,StopIteration) as error:
                raise DraftError(mode,key,f"{record.get('code',key)} {record.get('name','')}：{error}") from error
        return candidate,updated


def confirm_changes(parent,drafts,confirm=True):
    import tkinter as tk
    from tkinter import ttk
    from tkinter.scrolledtext import ScrolledText
    win=tk.Toplevel(parent);win.title('確認全部修改' if confirm else '尚未儲存的修改')
    from .ui_theme import BG
    win.configure(background=BG)
    win.geometry('760x560');win.minsize(580,400);win.transient(parent)
    ttk.Label(win,text=f'共 {len(drafts.changes)} 筆修改',font=('Microsoft JhengHei UI',14,'bold'),padding=14).pack(anchor='w')
    actions=ttk.Frame(win,padding=14);actions.pack(side='bottom',fill='x');result=False
    text=ScrolledText(win,wrap='word',font=('Microsoft JhengHei UI',12),padx=14,pady=10,background='white')
    text.pack(fill='both',expand=True,padx=14);text.insert('1.0',drafts.details());text.configure(state='disabled')
    def accept():
        nonlocal result
        result=True;win.destroy()
    ttk.Button(actions,text='返回修改',command=win.destroy).pack(side='right')
    if confirm:ttk.Button(actions,text='確認儲存',style='Save.TButton',command=accept).pack(side='right',padx=10)
    win.bind('<Escape>',lambda e:win.destroy());win.grab_set();win.wait_window();return result


class BatchEditor:
    def __init__(self,win,settings,layout,commit):
        import tkinter as tk
        from tkinter import ttk
        self.win=win;self.settings=settings;self.layout=layout;self.commit=commit;self.pages={};self.drafts=Drafts()
        footer=ttk.Frame(win,padding=(14,6));footer.pack(side='bottom',fill='x')
        self.status=tk.StringVar(value='尚無修改')
        ttk.Label(footer,textvariable=self.status,foreground='#775600').pack(side='left')
        self.save_button=ttk.Button(footer,text='儲存全部修改',style='Batch.Save.TButton',command=self.save,state='disabled')
        self.save_button.pack(side='right')
        self.review_button=ttk.Button(footer,text='檢視修改',style='Table.TButton',command=lambda:confirm_changes(win,self.drafts,False),state='disabled')
        self.review_button.pack(side='right',padx=8)
        win.protocol('WM_DELETE_WINDOW',self.close);win.request_close=self.close;win.batch=self
    def changed(self):
        count=len(self.drafts.changes)
        self.status.set(f'{count} 筆尚未儲存 · 黃色列為修改內容' if count else '尚無修改')
        for button in (self.save_button,self.review_button):button.configure(state='normal' if count else 'disabled')
    def save(self):
        from tkinter import messagebox
        if not self.drafts.changes:return True
        try:candidate,layout=self.drafts.prepare(self.settings,self.layout)
        except DraftError as error:
            mode='subregions' if error.mode=='automatic' else error.mode
            page=self.pages[mode];self.win.catalog_tabs.select(page.page)
            if error.mode!='automatic':
                page.table.clear_filters()
                for index,row in enumerate(page.table.rows):
                    if row['key']==error.key:
                        page.table.tree.selection_set(str(index));page.table.tree.see(str(index));break
            messagebox.showerror('未儲存',str(error),parent=self.win);return False
        if not confirm_changes(self.win,self.drafts):return False
        try:self.commit(candidate,layout)
        except (ValueError,OSError) as error:
            messagebox.showerror('未儲存',str(error)+'\n全部修改仍保留，修正問題後可重試。',parent=self.win);return False
        count=len(self.drafts.changes);self.drafts.changes.clear()
        for page in self.pages.values():page.refresh()
        self.changed();self.status.set(f'已儲存 {count} 筆修改，下次輸出套用。');return True
    def close(self):
        from tkinter import messagebox
        if self.drafts.changes:
            answer=messagebox.askyesnocancel('尚有未儲存的修改','要儲存全部修改後關閉嗎？\n選「否」會放棄這次修改，選「取消」繼續編輯。',parent=self.win)
            if answer is None or (answer and not self.save()):return False
        self.win.destroy();return True
