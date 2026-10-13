"""On-demand local case viewer; no results are persisted or sent to services."""
import copy
import queue
import threading
import tkinter as tk
from tkinter import ttk

from . import case_lookup, layout_settings
from .date_picker import DatePicker
from .help_tip import help_icon
from .ui_theme import FONT, INK, MUTED, PRIMARY, SURFACE


class CaseLookup:
    def __init__(self, page, app):
        self.page = page; self.app = app; self.ready = False; self.running = False
        self.generation = 0; self.events = queue.SimpleQueue(); self.poll_id = None
        self.records = {}; self.result = None
        page.bind('<Map>', self.build, add='+')
        page.bind('<Destroy>', self.destroy, add='+')
        self.database_trace = app.db.trace_add('write', self.invalidate)

    def build(self, event=None):
        if self.ready or event is not None and event.widget is not self.page:
            return
        self.ready = True
        from .desktop_view import card
        ttk.Label(self.page, text='病例查詢', style='PageTitle.TLabel').pack(anchor='w',pady=(0,12))
        edge, form = card(self.page, padding=12);edge.pack(fill='x', pady=(0,10))
        fields = ttk.Frame(form, style='Card.TFrame');fields.pack(fill='x')
        self.day = tk.StringVar(value=self.app.date.get());self.number = tk.StringVar()
        ttk.Label(fields, text='工作日期', style='Card.TLabel').grid(row=0, column=0, sticky='w', pady=(0,4))
        self.picker = DatePicker(fields, self.day);self.picker.grid(row=1, column=0, sticky='w', padx=(0,16))
        ttk.Label(fields, text='工作號', style='Card.TLabel').grid(row=0, column=1, sticky='w', pady=(0,4))
        self.entry = ttk.Entry(fields, textvariable=self.number, width=12, font=(FONT,14))
        self.entry.grid(row=1, column=1, sticky='ew', padx=(0,12));fields.columnconfigure(1, weight=1)
        self.query_button = ttk.Button(fields, text='查詢', style='Primary.TButton', command=self.search)
        self.query_button.grid(row=1, column=2)
        self.entry.bind('<Return>', lambda _:self.search())
        self.day.trace_add('write', self.invalidate);self.number.trace_add('write', self.invalidate)
        bar = ttk.Frame(self.page);bar.pack(fill='x', pady=(0,8))
        self.status = tk.StringVar(value='選擇日期並輸入工作號，可省略前面的 0。')
        self.status_label = ttk.Label(bar, textvariable=self.status, wraplength=700)
        self.status_label.pack(side='left', fill='x', expand=True)
        bar.bind('<Configure>', lambda e:self.status_label.configure(wraplength=max(220,e.width-50)))
        help_icon(bar, '套組階層依目前資料庫定義對照當單明細，不表示歷史開單時的父項關聯。'
            '\n「當單未登錄」沒有結果；共用子項可出現在多個套組內，統計不重複計數。'
            '\n併單來源依目前已儲存的併單規則比對，包含排除工作號；拆單模式仍可查看可併單的來源。'
            '\n檢驗值原樣顯示 VALUE／VALUE2／VALUE3／RESULT，不判讀正常或異常。'
            '\n列印區域與代碼採目前已儲存設定；停印項目也保留。選取項目可查看完整內容。').pack(side='right')
        # Reserve the read-only detail pane first, so the tree uses remaining room.
        detail_frame = ttk.Frame(self.page);detail_frame.pack(side='bottom', fill='x', pady=(8,0))
        ttk.Label(detail_frame, text='選取項目明細', style='PageHint.TLabel').pack(anchor='w')
        self.detail = tk.Text(detail_frame, height=4, wrap='word', font=(FONT,11),
            background=SURFACE, foreground=INK, relief='flat', padx=10, pady=6, state='disabled')
        detail_scroll = ttk.Scrollbar(detail_frame, command=self.detail.yview)
        detail_scroll.pack(side='right', fill='y');self.detail.pack(fill='x', expand=True)
        self.detail.configure(yscrollcommand=detail_scroll.set)
        tools = ttk.Frame(self.page);tools.pack(fill='x', pady=(0,6))
        ttk.Button(tools, text='展開全部', style='Table.TButton', command=lambda:self.expand(True)).pack(side='left')
        ttk.Button(tools, text='收合套組', style='Table.TButton', command=lambda:self.expand(False)).pack(side='left', padx=6)
        ttk.Button(tools, text='清除結果', style='Table.TButton', command=self.clear).pack(side='right')
        holder = ttk.Frame(self.page);holder.pack(fill='both', expand=True)
        style = ttk.Style(self.page)
        style.configure('Case.Treeview', font=(FONT,12), rowheight=34)
        columns = ('code','result','unit','zone','label','status')
        self.tree = ttk.Treeview(holder, columns=columns, show='tree headings', selectmode='browse', style='Case.Treeview')
        for key, title, width in [('#0','原始檢驗單／套組／項目名稱',310),('code','來源代碼',95),
            ('result','檢驗值',170),('unit','單位',85),('zone','列印區域',125),('label','列印代碼',100),('status','登錄狀態',165)]:
            self.tree.heading(key,text=title);self.tree.column(key,width=width,minwidth=width,stretch=key=='#0',anchor='w')
        y = ttk.Scrollbar(holder, orient='vertical', command=self.tree.yview)
        x = ttk.Scrollbar(holder, orient='horizontal', command=self.tree.xview)
        holder.rowconfigure(0, weight=1);holder.columnconfigure(0, weight=1)
        self.tree.grid(row=0,column=0,sticky='nsew');y.grid(row=0,column=1,sticky='ns');x.grid(row=1,column=0,sticky='ew')
        self.tree.configure(yscrollcommand=y.set,xscrollcommand=x.set)
        self.tree.tag_configure('matched',background='#E7F5F6',foreground='#005F70',font=(FONT,12,'bold'))
        self.tree.tag_configure('related',background='#EDF2FA',foreground='#215CAE',font=(FONT,12,'bold'))
        self.tree.tag_configure('missing',foreground=MUTED)
        self.tree.bind('<<TreeviewSelect>>', self.show_detail)
        self.set_detail('選取套組或單項後，這裡會顯示完整數值、來源工作號與列印設定。')

    def set_detail(self, value):
        self.detail.configure(state='normal');self.detail.delete('1.0','end')
        self.detail.insert('1.0',value);self.detail.configure(state='disabled');self.detail.yview_moveto(0)

    def invalidate(self, *_):
        self.generation += 1;self.result = None;self.records.clear()
        if self.ready:
            self.tree.delete(*self.tree.get_children());self.set_detail('')
            self.feedback('條件已變更，請重新查詢。')

    def clear(self):
        self.invalidate();self.feedback('已清除查詢結果。')

    def feedback(self, message, error=False):
        self.status.set(message);self.status_label.configure(foreground='#B42318' if error else INK)

    def search(self):
        if self.running:
            return
        try:
            day, number = case_lookup.validate_query(self.day.get(), self.number.get())
            database = self.app.db.get().strip()
            if not database:
                self.app.settings_status.set('請先選擇資料庫並測試連線，再使用病例查詢。')
                self.app.settings_status_label.configure(foreground='#B42318')
                self.app.tabs.select(self.app.system_page)
                raise ValueError('請先在系統設定選擇資料庫並測試連線。')
            settings = copy.deepcopy(self.app.settings);layout = layout_settings.load()
        except ValueError as error:
            self.invalidate();self.feedback(str(error),True);return
        except (OSError,TypeError):
            self.invalidate();self.feedback('無法讀取列印設定，請確認設定檔及讀取權限後重試。',True);return
        self.invalidate();generation = self.generation;self.running = True
        self.query_button.configure(state='disabled',text='查詢中…')
        self.picker.set_enabled(False);self.entry.configure(state='disabled')
        self.feedback('正在讀取指定檢驗單及可併單來源…')
        split = self.app.order_mode.get() == 'split'
        def worker():
            try:
                data = case_lookup.read_case(database,day,number)
                value = case_lookup.build_result(data,number,settings,layout)
                self.events.put((generation,day,number,split,value,None))
            except ValueError as error:
                self.events.put((generation,day,number,split,None,str(error)))
            except Exception:
                self.events.put((generation,day,number,split,None,'病例查詢失敗，請確認資料庫連線及資料格式後重試。'))
        threading.Thread(target=worker,daemon=True).start()
        self.poll_id = self.page.after(80,self.poll)

    def poll(self):
        self.poll_id = None
        try:
            generation,day,number,split,value,error = self.events.get_nowait()
        except queue.Empty:
            self.poll_id = self.page.after(80,self.poll);return
        self.running = False;self.query_button.configure(state='normal',text='查詢')
        self.picker.set_enabled(True);self.entry.configure(state='normal')
        if generation != self.generation:
            return  # The DB path or conditions changed while the worker was running.
        if error:
            self.feedback(error,True);return
        self.render(value,day,number,split)

    def render(self, result, day, number, split=False):
        self.result = result;self.records.clear();self.tree.delete(*self.tree.get_children())
        if not result['groups']:
            self.feedback(f'{day} 沒有工作號 {number} 的檢驗單，請確認工作日期與工作號。',True);return
        def add_node(parent,node,order):
            iid = self.tree.insert(parent,'end',text=node['name'],open=True,
                values=tuple(str(node[k]).replace('\n',' / ').replace('\r','') for k in ('code','result','unit','zone','label','status')),
                tags=('missing',) if node['status']=='當單未登錄' else ())
            self.records[iid] = (node,order)
            for child in node['children']:
                add_node(iid,child,order)
        for index,group in enumerate(result['groups'],1):
            title = f"{'可併單對照' if split else '併單組'} {index} · {len(group['orders'])} 張原單" if group['merged'] else '獨立檢驗單'
            if group['excluded']:
                title += ' · 工作號排除併單'
            group_id = self.tree.insert('','end',text=title,open=True)
            for order in group['orders']:
                flag = '查詢命中' if order['matched'] else '可併單來源' if split else '併單來源'
                title = f"工作號 {order['workno']} · {flag} · {order['name']} · {order['clinic']}"
                if order['department']:
                    title += f" · 部門 {order['department']}"
                iid = self.tree.insert(group_id,'end',text=title,open=True,
                    values=('','','','','',f"{order['panel_count']} 套組／{order['item_count']} 單項"),
                    tags=('matched' if order['matched'] else 'related',))
                self.records[iid] = (None,order)
                for node in order['nodes']:
                    add_node(iid,node,order)
        self.feedback(f"{day} · 命中 {result['matched_count']} 張／共 {result['order_count']} 張原單 · "
            f"{result['panel_count']} 套組、{result['item_count']} 筆單項明細"+
            (' · 目前匯出為拆單，這裡仍顯示可併單來源。' if split else ''))
        self.set_detail('青綠色：查詢命中的原單。藍色：同組其他原單。各單檢驗值分開保留。\n點選項目可查看完整內容；左右、上下捲軸可查看其餘欄位。')

    def show_detail(self, *_):
        selected = self.tree.selection()
        if not selected or selected[0] not in self.records:
            self.set_detail('');return
        node,order = self.records[selected[0]]
        lines = [f"工作號 {order['workno']} · 部門 {order['department'] or '未指定'} · {order['clinic']}",
                 f"姓名：{order['name']}　病歷號：{order['chart']}　開單：{order['order_date']}　就醫：{order['visit_date'] or '未填'}"]
        if node:
            lines += [f"{node['kind']} {node['code']} · {node['name']} · {node['status']}",
                      f"列印區域：{node['zone'] or '空白'}　子區域：{node['subregion']}　列印代碼：{node['label'] or '未設定'}　是否列印：{node['print_state']}"]
            if node['item_serial']:
                lines.append('來源明細序號：'+node['item_serial'])
            lines += [f'{label}：{value}' for label,value in node['values'] if value]
            if not any(value for _,value in node['values']):
                lines.append('檢驗值：'+('當單未登錄' if node['status']=='當單未登錄' else '未填值'))
            if node['unit']:
                lines.append('單位：'+node['unit'])
        self.set_detail('\n'.join(lines))

    def expand(self, opened):
        def walk(parent):
            for iid in self.tree.get_children(parent):
                node = self.records.get(iid,(None,None))[0]
                self.tree.item(iid,open=opened if node else True);walk(iid)
        walk('')

    def destroy(self, event):
        if event.widget is not self.page:
            return
        if self.poll_id:
            self.page.after_cancel(self.poll_id);self.poll_id = None
        self.app.db.trace_remove('write',self.database_trace)
        self.records.clear();self.result = None
