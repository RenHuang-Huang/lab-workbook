"""Searchable code dictionaries; only edits override existing rendering."""
import copy,re
from . import layout_settings as ls
from .core import display_label,GROUP_NAMES
from . import subregions as sr
from . import print_style as ps

NO_PRINT=''
MEMBER_ZONE='依成員分區'
MACHINE_NAMES={'routine':'不編流水號','e411':'e411 流水號','hba1c':'HbA1c 流水號','mab':'mab 流水號','aux':'不編流水號'}

def records(catalog,settings,layout):
    from .handwritten import SHORT
    rows=[];match_rule=ls.matcher(layout)
    for item in catalog['items']:
        code=str(item['LCI_ID']);machine=settings['rules'].get(code,{'group':'routine'})
        label=display_label(code,{code:item},machine);rule=match_rule(dict(item,LCI_NAMES=label));group=machine['group']
        if group=='e411':zone='e411'
        elif group in ('hba1c','mab') or label in ('U-cre','U-ACR','UTP','U-PCR','HBeAg'):zone='其他'
        elif code.startswith('B') or re.fullmatch(r'U\d{2}',code):zone='CBC／尿液'
        else:zone='生化／糞便'
        if rule:label,zone=rule['label'],rule['zone']
        else:label=SHORT.get(label,label)
        rows.append(dict(key=code,kind='單項',code=code,nhi=item.get('LCI_NHICODE') or '',name=item.get('LCI_NAME') or item.get('LCI_NAMEC') or '',label=label,zone=NO_PRINT if group=='aux' else zone,print_zone=zone,machine_group=group,group=MACHINE_NAMES[group],note='已列印套組內，有流水號分組的子項仍獨立列印。',search=' '.join(str(item.get(k) or '') for k in ('LCI_NAME','LCI_NAMEC','LCI_NAMES'))))
    for panel in catalog['sets']:
        code=str(panel['LCS_ID']);key='G:'+code
        rule=next((r for r in layout['rules'] if r['enabled'] and key in r['codes']),None)
        rows.append(dict(key=key,kind='套組',code=code,nhi=panel.get('LCS_NHICODE') or '',name=panel.get('LCS_NAME') or '',label=rule['label'] if rule else '',zone=rule['zone'] if rule else MEMBER_ZONE,machine_group=None,group='依成員編號',note='適用院所：'+str(panel.get('LCS_HOSPITAL') or '全部')+'；同套組代碼共用設定。「依成員分區」保留明細；機器成員仍分開顯示與編號。'))
        rows[-1].update(definition_id=panel.get('LCS_UNIKEY'),clinic_code=panel.get('LCS_HOSPITAL') or '')
    for row in rows:
        values=sr.placement(layout,row['key'],sr.default_placement(row),row.get('print_zone',row['zone']))
        row.update(values)
        if row.get('machine_group')=='aux':row['print_enabled']=False
        row['code_color']=layout.get('code_colors',{}).get(row['key'],'')
        row['color_display']=ps.title(ps.code_color(layout,row['key'],row['label'],settings,row.get('print_zone',row['zone']))) or '自動'
        row['color_rule_applied']=bool(ps.matching_color(settings,row['label'],row.get('print_zone',row['zone'])))
        row['print_state']=sr.print_state(row)
        row['subregion_display']=values['subregion'] or '自動'
        row['position_display']=str(values['position']) if values['position'] else '自動'
        from .settings_history import display
        row['updated_at']=layout.get('item_updated_at',{}).get(row['key'])
        row['updated_display']=display(row['updated_at']) or '尚無紀錄'
        if row['kind']=='套組':row['note']='適用院所：'+str(row['clinic_code'] or '全部')+'；是：印套組，取代一般子項。否：依子項設定展開。跨區列印子項：印套組，另保留不同列印區域且啟用的子項。有流水號的子項仍獨立列印。'
        if row['color_rule_applied']:row['note']+='；已套用列印代碼配色規則，優先於個別代碼顏色。'
    return rows

def set_override(layout,key,label,zone):
    candidate=copy.deepcopy(layout)
    if zone not in ls.ZONES or not label.strip():raise ValueError('請填列印簡稱並選擇區域。')
    for r in candidate['rules']:r['codes']=[c for c in r['codes'] if c!=key]
    candidate['rules'].append(dict(label=label.strip(),zone=zone,codes=[key],aliases=[],enabled=True,source='代碼清單設定'))
    ls.validate(candidate);return candidate


def edit_item(settings,layout,record,label,zone,group=None,*,print_enabled=None,subregion=None,position=...,position_mode=None,code_color=None):
    """Change placement and numbering together without renaming source tokens."""
    candidate=copy.deepcopy(settings);updated=copy.deepcopy(layout);label=label.strip()
    mode=position_mode if position_mode is not None else record.get('position_mode','slot')
    if mode not in ('slot','order'):raise ValueError('位置模式不正確。')
    single=record['kind']=='單項';old_group=record.get('machine_group')
    cross_zone=record.get('print_mode')=='cross_zone'
    if isinstance(print_enabled,str):
        if single or print_enabled not in sr.PRINT_STATES:raise ValueError('套組列印請選是、否或跨區列印子項。')
        cross_zone=print_enabled=='跨區列印子項';print_enabled=print_enabled!='否'
    if single:
        if group not in MACHINE_NAMES:raise ValueError('請選擇流水號分組。')
        if group=='aux':
            if print_enabled:raise ValueError('若要列印，請選擇列印區域並改為一般項目或指定流水號分組。')
            if not zone:zone=record['print_zone']
        elif not zone and print_enabled is False:zone=record['print_zone']
        elif zone not in ls.ZONES:raise ValueError('請選擇列印區域。')
        if group!=old_group:
            candidate['rules'].setdefault(record['key'],{})['group']=group
            candidate['mapping_confirmed']=False
    elif group is not None:raise ValueError('套組的流水號依成員規則，不可指定整組機器。')
    if record['kind']=='套組' and zone==MEMBER_ZONE:
        if label:raise ValueError('依成員分區時不使用套組列印代碼，請清空套組簡稱。')
        for rule in updated['rules']:rule['codes']=[c for c in rule['codes'] if c!=record['key']]
        ls.validate(updated)
    elif label!=record['label'] or zone!=record.get('print_zone',record['zone']) or (single and group!=old_group and group!='aux'):
        updated=set_override(updated,record['key'],label,zone)
    elif not label:raise ValueError('列印代碼／簡稱不可空白。')
    # An unchanged save must not create a rule that breaks existing CBC/urine compression.
    if print_enabled is not None:
        if record['kind']=='套組' and print_enabled and zone==MEMBER_ZONE:raise ValueError('列印套組時請設定簡稱及列印區域。')
        if single and print_enabled and group=='aux':raise ValueError('計算／行政項目若要列印，請先改為「不編流水號」或指定流水號分組。')
        values=dict(print_enabled=print_enabled,subregion=subregion if subregion is not None else record.get('subregion',''),
                    position=record.get('position') if position is ... else position)
        if not single and print_enabled and cross_zone:values['print_mode']='cross_zone'
        if mode=='order':values['position_mode']='order'
        if values!={k:record.get(k) for k in values} or layout.get('version',2)>=3:
            updated=sr.migrate(updated,[record]);updated['placements'][record['key']]=values;ls.validate(updated)
    if zone=='生化／糞便' and print_enabled is not None:
        if subregion not in (None,'','A','B','C','D','E','F'):raise ValueError('生化子區域請選 A～F 或自動。')
    if print_enabled is not None and mode!='order' and position is not ... and position is not None and position>3 and position!=record.get('position'):
        raise ValueError('每欄最多三列，固定位置請選 1～3；排列順位可選 1～10。')
    if code_color is not None:
        colors=updated.setdefault('code_colors',{})
        if code_color:colors[record['key']]=ps.color(code_color)
        else:colors.pop(record['key'],None)
    candidate.pop('layout',None)
    return candidate,updated


def editor(parent,catalog,settings,initial='items',resolved_rows=None,on_save=None,description='',on_export=None,on_import=None):
    import tkinter as tk
    from tkinter import ttk
    from . import catalog_cache as cc
    data=ls.load()
    if not data.get('bio_adult_slot') or not data.get('bio_groups_version'):
        data=sr.migrate(data,records(catalog,settings,data))
        data=sr.apply_bio_groups(data,records(catalog,settings,data));ls.save(data);resolved_rows=None
    win=tk.Toplevel(parent);win.title('列印設定');win.geometry('1200x810');win.minsize(940,680);win.transient(parent)
    cached_rows=copy.deepcopy(resolved_rows) if resolved_rows is not None else records(catalog,settings,data)
    def save(candidate,layout):
        if on_save:document=on_save(candidate,layout)
        else:
            active=cc.build(catalog,settings,data)
            document=cc.apply_settings(active,candidate,layout)
        settings.clear();settings.update(candidate);data.clear();data.update(layout)
        cached_rows[:]=document['records']
    from .catalog_batch import BatchEditor
    batch=BatchEditor(win,settings,data,save)
    tabs=ttk.Notebook(win);tabs.pack(fill='both',expand=True,padx=12,pady=(12,0))
    win.catalog_tabs=tabs;win.catalog_pages=batch.pages
    for mode,title in [('items','項目列印設定'),('clinics','診所列印簡稱')]:
        page=ttk.Frame(tabs,padding=12);tabs.add(page,text=title)
        if mode==('items' if initial=='mapping' else initial):tabs.select(page)
        win.catalog_pages[mode]=CatalogPage(page,mode,data,catalog,settings,lambda:cached_rows,batch)
    from .subregion_ui import SubregionPage
    page=ttk.Frame(tabs,padding=12);tabs.add(page,text='子區域與位置')
    win.catalog_pages['subregions']=SubregionPage(page,data,settings,save,batch=batch)
    if initial=='subregions':tabs.select(page)
    tabs.bind('<<NotebookTabChanged>>',lambda e:win.catalog_pages[('items','clinics','subregions')[tabs.index('current')]].refresh())
    return win


class CatalogPage:
    def __init__(self,page,mode,data,catalog,settings,get_rows,batch):
        import tkinter as tk
        from tkinter import ttk
        from .catalog_table import CatalogTable
        from .help_tip import help_icon
        self.page=page;self.mode=mode;self.clinics=mode=='clinics';self.data=data;self.catalog=catalog;self.settings=settings
        self.get_rows=get_rows;self.batch=batch;self.selected=None;self.loading=False;self.base_rows={}
        self.label=tk.StringVar();self.zone=tk.StringVar();self.group=tk.StringVar()
        self.print_enabled=tk.BooleanVar(value=True);self.subregion=tk.StringVar(value='自動');self.position=tk.StringVar(value='自動')
        self.panel_print=tk.StringVar(value='是')
        self.ranked=tk.BooleanVar(value=False);self.code_color=tk.StringVar(value='自動')
        self.info=tk.StringVar(value='請先選擇一筆');self.status=tk.StringVar()
        self.save_button=batch.save_button
        form=ttk.Frame(page);form.pack(side='bottom',fill='x',pady=(8,0))
        self.info_label=ttk.Label(form,textvariable=self.info,wraplength=980)
        self.info_label.grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,6))
        help_icon(form,lambda:self.selected.get('note','') if self.selected else '選擇項目後編輯；切換列會保留修改，黃色列代表尚未儲存。').grid(row=0,column=2,sticky='e')
        titles=['列印簡稱'] if self.clinics else ['列印代碼／簡稱','列印區域','流水號分組']
        for col,title in enumerate(titles):
            ttk.Label(form,text=title).grid(row=1,column=col,sticky='w',padx=(0,12))
            form.columnconfigure(col,weight=2 if col==0 else 1)
        self.label_entry=ttk.Entry(form,textvariable=self.label,font=('Microsoft JhengHei UI',13))
        self.label_entry.grid(row=2,column=0,sticky='ew',padx=(0,12),pady=(4,8))
        self.zone_box=ttk.Combobox(form,textvariable=self.zone,values=ls.ZONES,state='readonly',width=20,font=('Microsoft JhengHei UI',13))
        self.group_box=ttk.Combobox(form,textvariable=self.group,values=list(dict.fromkeys(MACHINE_NAMES.values())),state='readonly',width=22,font=('Microsoft JhengHei UI',13))
        if not self.clinics:
            self.zone_box.grid(row=2,column=1,sticky='ew',padx=(0,12),pady=(4,8))
            self.group_box.grid(row=2,column=2,sticky='ew',pady=(4,8))
            extra=ttk.Frame(form);extra.grid(row=3,column=0,columnspan=3,sticky='ew')
            print_holder=ttk.Frame(extra);print_holder.pack(side='left',padx=(0,12))
            self.print_check=ttk.Checkbutton(print_holder,text='是否列印',variable=self.print_enabled,command=self.print_changed);self.print_check.pack(side='left')
            self.panel_print_box=ttk.Combobox(print_holder,textvariable=self.panel_print,values=sr.PRINT_STATES,state='readonly',width=14,font=('Microsoft JhengHei UI',13))
            self.panel_print_box.bind('<<ComboboxSelected>>',lambda _:self.print_changed())
            ttk.Label(extra,text='子區域').pack(side='left')
            self.subregion_box=ttk.Combobox(extra,textvariable=self.subregion,state='readonly',width=5,font=('Microsoft JhengHei UI',13));self.subregion_box.pack(side='left',padx=(8,16))
            ttk.Label(extra,text='位置').pack(side='left')
            self.position_box=ttk.Combobox(extra,textvariable=self.position,state='readonly',width=5,font=('Microsoft JhengHei UI',13));self.position_box.pack(side='left',padx=8)
            ttk.Label(extra,text='代碼顏色').pack(side='left',padx=(8,6))
            self.color_box=ttk.Combobox(extra,textvariable=self.code_color,values=list(ps.PALETTE),width=8,font=('Microsoft JhengHei UI',13));self.color_box.pack(side='left')
            self.color_button=ttk.Button(extra,text='選色',style='Table.TButton',command=self.choose_color,width=5);self.color_button.pack(side='left',padx=4)
            ranked=ttk.Frame(form);ranked.grid(row=4,column=0,columnspan=3,sticky='ew',pady=(4,0))
            self.rank_check=ttk.Checkbutton(ranked,text='位置作為排列順位',variable=self.ranked,command=self.position_choices);self.rank_check.pack(side='left')
            help_icon(ranked,'排列順位可選 1～10 或自動；依實際項目排序，滿了往下一欄補位。所有區域固定位置皆為 1～3，同位順延。').pack(side='left',padx=4)
            self.members_button=ttk.Button(ranked,text='查看套組子項',style='Table.TButton',command=self.show_members,state='disabled');self.members_button.pack(side='right')
        form.bind('<Configure>',lambda e:self.info_label.configure(wraplength=max(300,e.width-60)))
        self.zone_box.bind('<<ComboboxSelected>>',self.zone_changed)
        self.group_box.bind('<<ComboboxSelected>>',self.group_changed)
        columns=[('code','診所代碼',135),('name','診所名稱',360),('label','列印簡稱',260)] if self.clinics else [
            ('kind','類型',100),('code','系統／套組代碼',140),('nhi','健保代碼',120),('name','項目名稱',235),
            ('print_state','是否列印',155),('zone','列印區域',150),('subregion_display','子區域',100),('position_display','位置',85),('label','列印代碼／簡稱',170),('color_display','代碼顏色',120),('group','流水號分組',180),('updated_display','最後更新',190)]
        self.table=CatalogTable(page,columns,self.pick)
        for var in (self.label,self.zone,self.group,self.print_enabled,self.panel_print,self.subregion,self.position,self.ranked,self.code_color):var.trace_add('write',self.changed)
        self.refresh()

    @staticmethod
    def values(record,clinics=False):
        if clinics:return dict(label=record['label'])
        return dict(label=record['label'],zone=record['zone'],group=record['group'],print_enabled=sr.print_state(record) if record['kind']=='套組' else record['print_enabled'],
            subregion=record['subregion_display'],position=str(record['position']) if record['position'] else '自動',
            position_mode=record.get('position_mode','slot'),code_color=ps.title(record.get('code_color','')))

    @staticmethod
    def identity(record):return (record['key'],record.get('definition_id'),record.get('clinic_code'))

    def refresh(self):
        if self.clinics:
            rows=[dict(key=str(h['HOS_ID']),code=str(h['HOS_ID']),name=h.get('HOS_NAME') or '',
                  label=self.data.get('clinic_aliases',{}).get(str(h['HOS_ID']),(h.get('HOS_NAME') or str(h['HOS_ID'])).replace('診所','').strip())) for h in self.catalog['hospitals']]
        else:rows=copy.deepcopy(self.get_rows())
        self.base_rows={self.identity(r):copy.deepcopy(r) for r in rows}
        for row in rows:
            edit=self.batch.drafts.get(self.mode,row['key'])
            if edit:row.update(self.project(edit['after']));row['_dirty']=True
        self.table.set_rows(rows)

    def pick(self,record):
        self.loading=True
        try:
            self.selected=self.base_rows.get(self.identity(record)) if record else None
            if not self.clinics:self.members_button.configure(state='normal' if record and record.get('kind')=='套組' else 'disabled')
            if record is None:
                self.info.set('請先選擇一筆');self.label.set('');self.zone.set('');self.group.set('')
                controls=[self.label_entry,self.zone_box,self.group_box]
                if not self.clinics:controls += [self.print_check,self.panel_print_box,self.subregion_box,self.position_box,self.rank_check,self.color_box,self.color_button]
                for widget in controls:widget.configure(state='disabled')
                return
            edit=self.batch.drafts.get(self.mode,record['key'])
            values=edit['after'] if edit else self.values(self.selected,self.clinics)
            self.info.set(str(record['code'])+'  '+record['name']);self.label.set(values['label']);self.label_entry.configure(state='normal')
            if self.clinics:return
            self.zone.set(values['zone']);self.group.set(values['group'])
            if record['kind']=='套組':
                self.panel_print.set(values['print_enabled']);self.print_check.pack_forget();self.panel_print_box.pack(side='left');self.panel_print_box.configure(state='readonly')
            else:
                self.print_enabled.set(values['print_enabled']);self.panel_print_box.pack_forget();self.print_check.pack(side='left')
            self.subregion.set(values['subregion']);self.position.set(values['position']);self.ranked.set(values['position_mode']=='order');self.code_color.set(values['code_color'])
            for widget in (self.print_check,self.rank_check,self.color_button):widget.configure(state='normal')
            for widget in (self.subregion_box,self.position_box,self.color_box):widget.configure(state='readonly' if widget!=self.color_box else 'normal')
            self.zone_box.configure(values=[MEMBER_ZONE,*ls.ZONES] if record['kind']=='套組' else ['',*ls.ZONES],state='readonly')
            self.group_box.configure(state='readonly' if record['kind']=='單項' else 'disabled')
            self.label_entry.configure(state='disabled' if record['kind']=='套組' and values['zone']==MEMBER_ZONE else 'normal')
            self.position_choices()
        finally:self.loading=False

    def project(self,values):
        if self.clinics:return dict(label=values['label'])
        try:color_display=ps.title(ps.matching_color(self.settings,values['label'],values['zone']) or ps.choice(values['code_color'])) or '自動'
        except ValueError:color_display=values['code_color']
        state=values['print_enabled'] if isinstance(values['print_enabled'],str) else '是' if values['print_enabled'] else '否'
        return dict(label=values['label'],zone=values['zone'],group=values['group'],print_state=state,
            subregion_display=values['subregion'],position_display=values['position'],color_display=color_display)

    def changed(self,*_):
        if self.loading or not self.selected:return
        record=self.selected
        after=dict(label=self.label.get())
        if not self.clinics:after.update(zone=self.zone.get(),group=self.group.get(),print_enabled=self.panel_print.get() if record['kind']=='套組' else self.print_enabled.get(),
            subregion=self.subregion.get(),position=self.position.get(),position_mode='order' if self.ranked.get() else 'slot',code_color=self.code_color.get())
        self.batch.drafts.put(self.mode,record,self.values(record,self.clinics),after)
        self.table.update_rows(record['key'],self.project(after),bool(self.batch.drafts.get(self.mode,record['key'])))
        self.batch.changed()

    def show_members(self):
        if not self.selected or self.selected.get('kind')!='套組':return
        from .catalog_members import show
        old=getattr(self,'members_window',None)
        if old is not None and old.winfo_exists():old.destroy()
        self.members_window=show(self.page,self.selected,self.catalog,self.get_rows())

    def choose_color(self):
        from tkinter.colorchooser import askcolor
        try:initial=ps.color(ps.choice(self.code_color.get()) or ps.BLACK)
        except ValueError:initial=ps.BLACK
        picked=askcolor(color=initial,parent=self.page,title='列印代碼顏色')[1]
        if picked:self.code_color.set(picked.upper())

    def position_choices(self):
        bio=self.zone.get()=='生化／糞便'
        self.position_box.configure(values=['自動',*map(str,range(1,11 if self.ranked.get() else 4))])
        self.subregion_box.configure(values=['自動',*('ABCDEF' if bio else sr.LETTERS)])

    def group_changed(self,*_):
        if not self.selected:return
        if self.group.get()!='不編流水號' and not self.zone.get():self.zone.set(self.selected['print_zone'])

    def print_changed(self):
        if not self.selected:return
        if (self.panel_print.get()!='否' if self.selected['kind']=='套組' else self.print_enabled.get()):
            if self.selected['kind']=='套組' and self.zone.get()==MEMBER_ZONE:
                self.zone.set('生化／糞便');self.label_entry.configure(state='normal');self.label.set(self.selected['name'])
            elif not self.zone.get():self.zone.set(self.selected.get('print_zone','生化／糞便'))
        self.position_choices()

    def zone_changed(self,*_):
        self.position_choices()
        if not self.selected:return
        if self.selected['kind']=='套組':
            inherited=self.zone.get()==MEMBER_ZONE
            self.label_entry.configure(state='disabled' if inherited else 'normal')
            if inherited:self.label.set('')
            if inherited:self.panel_print.set('否')
        elif not self.zone.get():self.print_enabled.set(False)

    def save(self):return self.batch.save()
