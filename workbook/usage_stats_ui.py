"""On-demand, aggregate-only usage analysis; database work stays off the UI thread."""
import copy
import datetime as dt
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from . import usage_stats,layout_settings
from .catalog_table import CatalogTable
from .date_picker import DatePicker
from .help_tip import help_icon
from .ui_theme import INK


class UsageStats:
    def __init__(self,parent,app):
        self.app=app;self.running=False;self.data=None;self.document=None
        self.generation=0;self.poll_id=None;self.events=queue.SimpleQueue()
        win=self.window=tk.Toplevel(parent);win.title('近三年使用統計');win.geometry('1180x760');win.minsize(940,680)
        win.transient(parent);win.protocol('WM_DELETE_WINDOW',self.close)
        body=ttk.Frame(win,padding=12);body.pack(fill='both',expand=True)
        form=ttk.Frame(body);form.pack(fill='x')
        ttk.Label(form,text='統計截至').pack(side='left',padx=(0,10))
        self.day=tk.StringVar(value=dt.date.today().isoformat());self.picker=DatePicker(form,self.day);self.picker.pack(side='left')
        self.query_button=ttk.Button(form,text='從資料庫整理',style='Primary.TButton',command=self.search)
        self.query_button.pack(side='right')
        self.range_text=tk.StringVar();ttk.Label(body,textvariable=self.range_text,style='PageHint.TLabel').pack(anchor='w',pady=6)
        options=ttk.Frame(body);options.pack(fill='x',pady=(0,8))
        self.exclude=tk.BooleanVar(value=True)
        ttk.Checkbutton(options,text='單項排除套組展開項目',variable=self.exclude,command=self.render).pack(side='left')
        help_icon(options,'同一張原始檢驗單內，同代碼最多計一次；工作簿併單不影響次數。'
            '\n僅排除同單 MKEY 明確對上已登錄套組代碼的子項。若同碼另外獨立加開，仍計一次。'
            '\n關聯不明的明細保留計數，並列待核對次數；不依目前套組成員推測歷史開單來源。'
            '\n預設按列印區域分類，再依使用次數由多到少。點「使用次數」可改全表排序。'
            '\n列印區域與簡稱採整理當下已儲存的設定，可按「重新分類」套用最新設定。').pack(side='left',padx=6)
        self.reclassify_button=ttk.Button(options,text='依目前設定重新分類',style='Table.TButton',command=self.reclassify,state='disabled')
        self.reclassify_button.pack(side='right')
        self.status=tk.StringVar(value='按「從資料庫整理」開始；只讀取日期、項目及套組關聯，不讀病患資料或檢驗值。')
        self.status_label=ttk.Label(body,textvariable=self.status,wraplength=1080)
        self.status_label.pack(fill='x',pady=(0,10))
        body.bind('<Configure>',lambda e:self.status_label.configure(wraplength=max(200,e.width-20)),add='+')
        footer=ttk.Frame(body);footer.pack(side='bottom',fill='x',pady=(10,0))
        self.export_button=ttk.Button(footer,text='匯出完整統計 CSV／JSON',command=self.export,state='disabled')
        self.export_button.pack(side='right')
        ttk.Label(footer,text='匯出包含兩種清單；不受畫面搜尋與篩選影響。',style='PageHint.TLabel').pack(side='left')
        self.tabs=ttk.Notebook(body);self.tabs.pack(fill='both',expand=True)
        columns=(('zone','列印區域',140),('count','使用次數',110),('code','來源代碼',110),('name','項目名稱',235),
            ('label','列印代碼',120),('print_state','是否列印',120),('uncertain_count','待核對次數',120),
            ('last_used','最後使用',140),('updated_display','設定最後更新',190))
        self.tables={}
        for kind in ('套組','單項'):
            page=ttk.Frame(self.tabs,padding=10);self.tabs.add(page,text=kind)
            self.tables[kind]=CatalogTable(page,columns,lambda row:None,
                help_text='各欄可篩選；點欄名排序，再點一次反向。使用次數以原始檢驗單計算，並非工作簿列數。')
        self.day.trace_add('write',self.invalidate)
        self.database_trace=app.db.trace_add('write',self.invalidate)
        self.invalidate()

    def feedback(self,text,error=False):
        self.status.set(text);self.status_label.configure(foreground='#B42318' if error else INK)

    def invalidate(self,*_):
        self.generation+=1;self.data=None;self.document=None
        for table in self.tables.values():table.set_rows([])
        self.export_button.configure(state='disabled');self.reclassify_button.configure(state='disabled')
        try:
            start,end=usage_stats.period(self.day.get());self.range_text.set(f'{start} ～ {end}（含首尾日期）')
            self.feedback('按「從資料庫整理」開始；統計以原始檢驗單計次，不受拆單／併單模式影響。')
        except ValueError as error:self.feedback(str(error),True)

    def snapshot_settings(self):
        from .core import get_settings
        self.settings=copy.deepcopy(get_settings());self.layout=layout_settings.load()

    def search(self):
        if self.running:return
        try:
            _,end=usage_stats.period(self.day.get());database=self.app.db.get().strip()
            if not database:raise ValueError('請先到系統設定選擇資料庫並測試連線。')
            self.snapshot_settings()
        except (OSError,ValueError,TypeError):
            self.invalidate();self.feedback('請確認資料庫路徑、統計日期及已儲存的列印設定。',True);return
        self.invalidate();generation=self.generation;self.running=True;self.started=time.monotonic()
        self.query_button.configure(state='disabled',text='正在整理…');self.picker.set_enabled(False)
        self.feedback('正在本機讀取近三年的項目紀錄，資料量大時需要稍候…')
        def worker():
            try:self.events.put((generation,usage_stats.read_usage(database,end),None))
            except ValueError as error:self.events.put((generation,None,str(error)))
            except Exception:self.events.put((generation,None,'無法整理使用統計，請確認 Access 連線、檔案讀取權限及資料庫格式。'))
        threading.Thread(target=worker,daemon=True).start();self.poll_id=self.window.after(100,self.poll)

    def poll(self):
        self.poll_id=None
        try:generation,data,error=self.events.get_nowait()
        except queue.Empty:
            self.feedback(f'正在整理近三年紀錄… 已經過 {int(time.monotonic()-self.started)} 秒。')
            self.poll_id=self.window.after(200,self.poll);return
        self.running=False;self.query_button.configure(state='normal',text='從資料庫整理');self.picker.set_enabled(True)
        if generation!=self.generation:self.feedback('資料庫或日期已變更，請重新整理。');return
        if error:self.feedback(error,True);return
        self.data=data;self.render()

    def render(self):
        if self.data is None:return
        try:document=usage_stats.report(self.data,self.settings,self.layout,self.exclude.get())
        except (ValueError,KeyError,TypeError):
            self.invalidate();self.feedback('統計資料或設定格式不完整，請確認後重新整理。',True);return
        self.document=document
        for index,(kind,table) in enumerate(self.tables.items()):
            rows=[row for row in document['rows'] if row['kind']==kind];table.set_rows(rows)
            self.tabs.tab(index,text=f'{kind}（{len(rows)}）')
        from .settings_history import display,latest
        modified=display(latest(self.settings.get('updated_at'),self.layout.get('updated_at'))) or '尚無紀錄'
        note=f"已整理 {document['order_count']:,} 張有明細的原始檢驗單。列印設定更新：{modified}。"
        unresolved=document['unresolved_detail_count'];unknown=document['unknown_detail_count']
        if unresolved or unknown:note+=f'\n關聯待核對 {unresolved:,} 筆（保留計數）；類型／代碼不明 {unknown:,} 筆（未計入）。'
        if not document['rows']:note+=' 此期間沒有符合條件的項目。'
        self.feedback(note,error=bool(unknown))
        self.export_button.configure(state='normal');self.reclassify_button.configure(state='normal')

    def reclassify(self):
        if self.running or self.data is None:return
        try:self.snapshot_settings()
        except (OSError,ValueError,TypeError):self.feedback('無法讀取最新設定，原分類結果保留。',True);return
        self.render()

    def export(self):
        if not self.document:return
        destination=filedialog.asksaveasfilename(parent=self.window,title='匯出完整使用統計',defaultextension='.csv',
            initialfile=f"近三年使用統計_{self.document['end_date']}.csv",filetypes=[('Excel 可讀 CSV','*.csv'),('JSON','*.json')])
        if not destination:return
        try:usage_stats.export(destination,self.document)
        except (OSError,ValueError):messagebox.showerror('匯出失敗','請確認輸出資料夾可寫入，並關閉正在開啟的同名檔案。',parent=self.window);return
        self.feedback('已匯出套組與單項的完整統計。')

    def close(self):
        if self.running:messagebox.showinfo('正在整理統計','請等候本機統計完成後再關閉。',parent=self.window);return
        if self.poll_id:self.window.after_cancel(self.poll_id)
        self.app.db.trace_remove('write',self.database_trace);self.data=None;self.document=None;self.window.destroy()
