"""Subgroup controls share the item editor's filterable and sortable table."""
import copy
import tkinter as tk
from tkinter import ttk,messagebox
from . import subregions as sr
from .catalog_table import CatalogTable


class SubregionPage:
    def __init__(self,page,layout,settings,save,batch=None):
        self.page=page;self.layout=layout;self.settings=settings;self.commit=save;self.selected=None
        self.batch=batch;self.loading=False
        from .help_tip import help_icon
        self.display=tk.StringVar(value=sr.MODES['normal'])
        self.compact_subregions=tk.BooleanVar(value=True);self.compact_positions=tk.BooleanVar(value=True)
        self.info=tk.StringVar(value='請選擇列印區域與子區域');self.status=tk.StringVar()
        automatic=ttk.Frame(page);automatic.pack(side='top',fill='x',pady=(0,12))
        ttk.Label(automatic,text='生化自動項目的起始區').pack(side='left')
        self.auto_start=tk.StringVar(value=layout.get('bio_auto_start','A'))
        self.auto_start_box=ttk.Combobox(automatic,textvariable=self.auto_start,values=list('ABCDEF'),state='readonly',width=5,font=('Microsoft JhengHei UI',13))
        self.auto_start_box.pack(side='left',padx=10)
        help_icon(automatic,'先排指定項目，再從此區往後補空位。修改後與其餘設定一起儲存。').pack(side='left')
        if batch:self.auto_save_button=batch.save_button
        else:
            self.auto_save_button=ttk.Button(automatic,text='儲存起始區',command=self.save_auto_start);self.auto_save_button.pack(side='right')
        form=ttk.Frame(page);form.pack(side='bottom',fill='x',pady=(12,0))
        ttk.Label(form,textvariable=self.info,font=('Microsoft JhengHei UI',11,'bold')).pack(anchor='w')
        row=ttk.Frame(form);row.pack(fill='x',pady=4)
        ttk.Label(row,text='顯示設定').pack(side='left')
        self.mode_box=ttk.Combobox(row,textvariable=self.display,values=list(sr.MODES.values()),state='readonly',width=34,font=('Microsoft JhengHei UI',13));self.mode_box.pack(side='left',padx=10)
        if batch:self.save_button=batch.save_button
        else:
            self.save_button=ttk.Button(row,text='儲存子區域設定',command=self.save);self.save_button.pack(side='right')
        checks=ttk.Frame(form);checks.pack(fill='x')
        self.sub_check=ttk.Checkbutton(checks,text='子區域遞補',variable=self.compact_subregions);self.sub_check.pack(side='left')
        self.pos_check=ttk.Checkbutton(checks,text='位置遞補',variable=self.compact_positions);self.pos_check.pack(side='left',padx=12)
        help_icon(checks,'子區域遞補：空區由後區往左補；位置遞補：空位由後項往上補。取消則保留空位。所有檢驗區每欄最多三列，超出往下一欄補位。').pack(side='left')
        ttk.Label(form,textvariable=self.status,wraplength=860).pack(anchor='w')
        self.table=CatalogTable(page,[('zone','列印區域',190),('subregion_display','子區域',100),('display','顯示設定',330),
                                     ('compact_subregions','子區域遞補',160),('compact_positions','位置遞補',150)],self.pick)
        self.refresh()
        if batch:
            for var in (self.display,self.compact_subregions,self.compact_positions):var.trace_add('write',self.changed)
            self.auto_start.trace_add('write',self.auto_changed)

    def refresh(self):
        self.loading=True
        auto=self.batch.drafts.get('automatic','bio_auto_start') if self.batch else None
        self.auto_start.set(auto['after']['bio_auto_start'] if auto else self.layout.get('bio_auto_start','A'))
        self.auto_start_box.configure(style='Pending.TCombobox' if auto else 'TCombobox')
        rows=[]
        for zone in sr.ZONE_KEYS:
            for letter in (sr.LETTERS[:6] if zone=='生化／糞便' else sr.LETTERS):
                options=sr.options(self.layout,zone,letter)
                rows.append(dict(key=zone+':'+letter,name=zone+' '+letter,zone=zone,subregion_display=letter,display=sr.MODES[options['display']],
                    compact_subregions='是' if options['compact_subregions'] else '否',compact_positions='是' if options['compact_positions'] else '否'))
                edit=self.batch.drafts.get('subregions',rows[-1]['key']) if self.batch else None
                if edit:rows[-1].update(self.project(edit['after']),_dirty=True)
        self.table.set_rows(rows)
        self.loading=False

    def pick(self,record):
        loading=self.loading;self.loading=True
        self.selected=record
        if not self.batch:self.save_button.configure(state='normal' if record else 'disabled')
        if record:
            self.info.set(record['zone']+' ／ 子區域 '+record['subregion_display']);self.display.set(record['display'])
            self.compact_subregions.set(record['compact_subregions']=='是');self.compact_positions.set(record['compact_positions']=='是')
            self.sub_check.configure(state='normal')
        else:self.info.set('請選擇列印區域與子區域')
        self.loading=loading

    @staticmethod
    def project(values):
        return dict(display=values['display'],compact_subregions='是' if values['compact_subregions'] else '否',
                    compact_positions='是' if values['compact_positions'] else '否')

    def changed(self,*_):
        if not self.batch or self.loading or not self.selected:return
        record=self.selected;options=sr.options(self.layout,record['zone'],record['subregion_display'])
        before=dict(options,display=sr.MODES[options['display']])
        after=dict(display=self.display.get(),compact_subregions=self.compact_subregions.get(),compact_positions=self.compact_positions.get())
        self.batch.drafts.put('subregions',record,before,after)
        self.table.update_rows(record['key'],self.project(after),bool(self.batch.drafts.get('subregions',record['key'])))
        self.batch.changed()

    def auto_changed(self,*_):
        if not self.batch or self.loading:return
        self.batch.drafts.put('automatic',dict(key='bio_auto_start',name='生化自動起始區'),
            dict(bio_auto_start=self.layout.get('bio_auto_start','A')),dict(bio_auto_start=self.auto_start.get()))
        self.auto_start_box.configure(style='Pending.TCombobox' if self.batch.drafts.get('automatic','bio_auto_start') else 'TCombobox')
        self.batch.changed()

    def save(self):
        if self.batch:return self.batch.save()
        if self.selected is None:return
        try:
            updated=sr.migrate(self.layout,[]);record=self.selected
            updated['subregions'][record['zone']][record['subregion_display']]=dict(
                display=next(key for key,value in sr.MODES.items() if value==self.display.get()),
                compact_subregions=self.compact_subregions.get(),compact_positions=self.compact_positions.get())
            self.commit(copy.deepcopy(self.settings),updated);self.refresh();self.status.set('已儲存，下次輸出套用。')
        except (ValueError,OSError) as error:messagebox.showerror('未儲存',str(error),parent=self.page)

    def save_auto_start(self):
        if self.batch:return self.batch.save()
        try:
            updated=copy.deepcopy(self.layout);updated['bio_auto_start']=self.auto_start.get();sr.validate(updated)
            self.commit(copy.deepcopy(self.settings),updated);self.refresh();self.status.set('已儲存生化自動起始區，下次輸出套用。')
        except (ValueError,OSError) as error:messagebox.showerror('未儲存',str(error),parent=self.page)
