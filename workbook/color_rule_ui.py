"""Editable, ordered print-code color rules; changes stay local until saved."""
import copy,re
import tkinter as tk
from tkinter import ttk,colorchooser
from . import print_style as ps,layout_settings as ls
from .ui_styles import readable_table


class ColorRules:
    def __init__(self,parent,settings,on_save):
        self.window=tk.Toplevel(parent);self.window.title('列印代碼配色規則')
        self.window.geometry('940x680');self.window.minsize(820,640);self.window.transient(parent)
        self.on_save=on_save;self.rules=copy.deepcopy(ps.color_rules(settings));self.selected=None;self.updating=False
        self.codes=tk.StringVar();self.zone=tk.StringVar(value=ps.ALL_ZONES)
        self.ink=tk.StringVar(value='紅色');self.enabled=tk.BooleanVar(value=True);self.status=tk.StringVar()
        body=ttk.Frame(self.window,padding=20);body.pack(fill='both',expand=True)
        ttk.Label(body,text='列印代碼配色規則',font=('Microsoft JhengHei UI',18,'bold')).pack(anchor='w')
        hints=[]
        for text,padding in [('完整比對列印代碼，不分英文大小寫。多個代碼用逗號分隔，例如 CBC, Plt, WBC, Hb。',(6,4)),('由上往下套用第一條符合規則，優先於個別項目色、併單色；機器流水號維持原色。',(0,12))]:
            label=ttk.Label(body,text=text,wraplength=860);label.pack(anchor='w',pady=padding);hints.append(label)
        footer=ttk.Frame(body);footer.pack(side='bottom',fill='x',pady=(12,0))
        ttk.Button(footer,text='取消',command=self.window.destroy).pack(side='right')
        self.save_button=ttk.Button(footer,text='儲存配色規則',style='Save.TButton',command=self.save)
        self.save_button.pack(side='right',padx=(0,10))
        self.status_label=ttk.Label(body,textvariable=self.status,foreground='#B02631',wraplength=850)
        self.status_label.pack(side='bottom',fill='x',pady=(10,0))
        self.window.bind('<Configure>',lambda e:[label.configure(wraplength=max(400,e.width-44)) for label in [*hints,self.status_label]] if e.widget==self.window else None)
        form=ttk.Frame(body);form.pack(side='bottom',fill='x',pady=(12,0));form.columnconfigure(1,weight=1)
        ttk.Label(form,text='列印代碼').grid(row=0,column=0,sticky='w',padx=(0,12))
        self.codes_entry=ttk.Entry(form,textvariable=self.codes);self.codes_entry.grid(row=0,column=1,columnspan=3,sticky='ew',pady=(0,10))
        ttk.Label(form,text='適用區域').grid(row=1,column=0,sticky='w',padx=(0,12))
        self.zone_box=ttk.Combobox(form,textvariable=self.zone,values=(ps.ALL_ZONES,*ls.ZONES),state='readonly',width=17)
        self.zone_box.grid(row=1,column=1,sticky='w')
        ttk.Checkbutton(form,text='啟用',variable=self.enabled).grid(row=1,column=2,sticky='w',padx=(16,0))
        ttk.Label(form,text='字體顏色').grid(row=2,column=0,sticky='w',padx=(0,12),pady=(10,0))
        color_line=ttk.Frame(form);color_line.grid(row=2,column=1,columnspan=3,sticky='w',pady=(10,0))
        self.color_box=ttk.Combobox(color_line,textvariable=self.ink,values=[k for k in ps.PALETTE if k!='自動'],width=17)
        self.color_box.pack(side='left');ttk.Button(color_line,text='選色',command=self.choose_color).pack(side='left',padx=8)
        self.apply_button=ttk.Button(color_line,text='套用此列',command=self.apply);self.apply_button.pack(side='left')
        toolbar=ttk.Frame(body);toolbar.pack(side='bottom',fill='x',pady=(10,0))
        for title,command in [('新增規則',self.add),('刪除規則',self.delete),('上移',lambda:self.move(-1)),('下移',lambda:self.move(1))]:
            ttk.Button(toolbar,text=title,command=command).pack(side='left',padx=(0,8))
        holder=ttk.Frame(body);holder.pack(fill='both',expand=True);holder.rowconfigure(0,weight=1);holder.columnconfigure(0,weight=1)
        self.tree=ttk.Treeview(holder,columns=('enabled','codes','zone','color'),show='headings',selectmode='browse',height=5,style=readable_table(parent))
        for key,title,width in [('enabled','啟用',60),('codes','列印代碼',390),('zone','適用區域',160),('color','字體顏色',140)]:
            self.tree.heading(key,text=title);self.tree.column(key,width=width,minwidth=width,stretch=key=='codes')
        self.tree.grid(row=0,column=0,sticky='nsew')
        ttk.Scrollbar(holder,orient='vertical',command=self.tree.yview).grid(row=0,column=1,sticky='ns')
        ttk.Scrollbar(holder,orient='horizontal',command=self.tree.xview).grid(row=1,column=0,sticky='ew')
        scrolls=holder.winfo_children();self.tree.configure(yscrollcommand=scrolls[1].set,xscrollcommand=scrolls[2].set)
        self.tree.bind('<<TreeviewSelect>>',self.select)
        self.refresh(0 if self.rules else None);self.window.grab_set()

    def refresh(self,index):
        self.updating=True
        self.tree.delete(*self.tree.get_children())
        for i,rule in enumerate(self.rules):
            self.tree.insert('',tk.END,iid=str(i),values=('是' if rule['enabled'] else '否',', '.join(rule['codes']) or '請填入列印代碼',rule['zone'],ps.title(rule['color'])))
        self.selected=index
        if index is not None:
            self.tree.selection_set(str(index));self.tree.see(str(index));self.load_form(self.rules[index])
        else:self.load_form(dict(codes=[],zone=ps.ALL_ZONES,color=ps.RED,enabled=True))
        self.updating=False

    def load_form(self,rule):
        self.codes.set(', '.join(rule['codes']));self.zone.set(rule['zone']);self.ink.set(ps.title(rule['color']));self.enabled.set(rule['enabled'])

    def apply(self):
        if self.selected is None:
            self.status.set('請先新增或選擇一條規則。');return False
        try:
            value=dict(codes=[s.strip() for s in re.split(r'[,，、;；|\r\n]+',self.codes.get()) if s.strip()],
                zone=self.zone.get(),color=ps.choice(self.ink.get()),enabled=self.enabled.get())
            value=ps.color_rules({'print_color_rules':[value]})[0]
        except ValueError as error:self.status.set(str(error));return False
        self.rules[self.selected]=value
        self.tree.item(str(self.selected),values=('是' if value['enabled'] else '否',', '.join(value['codes']),value['zone'],ps.title(value['color'])))
        self.status.set('此列已套用；按「儲存配色規則」後生效。');return True

    def select(self,event=None):
        if self.updating or not self.tree.selection():return
        index=int(self.tree.selection()[0])
        if index==self.selected:return
        if self.selected is not None and not self.apply():
            self.tree.selection_set(str(self.selected));return
        self.selected=index;self.load_form(self.rules[index]);self.status.set('')

    def add(self):
        if self.selected is not None and not self.apply():return
        self.rules.append(dict(codes=[],zone=ps.ALL_ZONES,color=ps.RED,enabled=True))
        self.refresh(len(self.rules)-1);self.status.set('請填入列印代碼與顏色。');self.codes_entry.focus_set()

    def delete(self):
        if self.selected is None:return
        index=self.selected;self.rules.pop(index)
        self.refresh(min(index,len(self.rules)-1) if self.rules else None)
        self.status.set('規則已移除；儲存後生效。刪除全部規則表示停用代碼配色。')

    def move(self,direction):
        if self.selected is None or not self.apply():return
        index=self.selected;target=index+direction
        if 0<=target<len(self.rules):
            self.rules[index],self.rules[target]=self.rules[target],self.rules[index];self.refresh(target)

    def choose_color(self):
        try:initial=ps.color(ps.choice(self.ink.get()))
        except ValueError:initial=ps.RED
        value=colorchooser.askcolor(color=initial,parent=self.window,title='列印代碼顏色')[1]
        if value:self.ink.set(value.upper())

    def save(self):
        if self.selected is not None and not self.apply():return False
        try:self.on_save(ps.color_rules({'print_color_rules':self.rules}))
        except ValueError as error:self.status.set(str(error));return False
        except OSError:self.status.set('無法儲存配色規則，原設定已保留；請確認資料夾寫入權限。');return False
        self.window.destroy();return True
