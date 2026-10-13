from __future__ import annotations
import datetime as dt, os, threading, tkinter as tk, queue
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from .core import *
from .date_picker import DatePicker
from .errors import LayoutCapacityError
from .version import APP_VERSION
PREFERENCES=ROOT/'preferences.json'
PREFERENCE_KEYS=('database_path','output_directory','order_mode','merge_workno_style')

def default_preferences():
    return {'database_path':'','output_directory':str(ROOT/'output'),
            'order_mode':'merge','merge_workno_style':'first'}

def load_preferences():
    preferences=default_preferences()
    if not PREFERENCES.exists():
        save_json(PREFERENCES,preferences)
        return preferences
    saved=load_json(PREFERENCES)
    if not isinstance(saved,dict):raise ValueError('系統設定格式不正確。')
    from .config_store import system_values
    return system_values(saved,ROOT)

class App:
    def __init__(self,root,auto_connect=True):
        self.root=root;root.title(f'工作簿輸出 {APP_VERSION}')
        root.geometry(f'{min(1080,max(820,root.winfo_screenwidth()-80))}x{min(860,max(640,root.winfo_screenheight()-100))}')
        root.minsize(820,640)
        self.settings=get_settings();self.data=None;self.rows=[];self.busy=False;self.pending=False;self.selected=None
        self.catalog_loading=False
        self.update_checking=False
        self.update_status=tk.StringVar(value=f'目前版本 {APP_VERSION}')
        self.settings.update(default_preferences())
        self.settings.update(load_preferences())
        self.connection_token=0;self.connection_testing=False;self.connected_path=None
        self.events=queue.SimpleQueue();self.last_pdf=None
        database=ROOT/'檢驗系統/ktlab.mdb'
        self.db=tk.StringVar(value=self.settings.get('database_path',str(database) if database.is_file() else ''))
        self.output_dir=tk.StringVar(value=self.settings.get('output_directory',str(ROOT/'output')))
        self.date=tk.StringVar(value=dt.date.today().isoformat())
        mode='merge_first' if self.settings.get('merge_workno_style')=='first' else 'merge'
        self.order_mode=tk.StringVar(value=mode if self.settings.get('order_mode')=='merge' else 'split')
        self.show_headers=tk.BooleanVar(value=self.settings.get('show_column_headers',False))
        self.fixed_20_rows=tk.BooleanVar(value=self.settings.get('fixed_20_rows',True))
        self.ditto_bio=tk.BooleanVar(value=self.settings.get('ditto_bio',True))
        self.ditto_patient=tk.BooleanVar(value=self.settings.get('ditto_patient',True))
        self.show_region_lines=tk.BooleanVar(value=self.settings.get('show_region_lines',False))
        self.export_glucose_ac=tk.BooleanVar(value=self.settings.get('export_glucose_ac',True))
        self.glucose_ac_columns=tk.StringVar(value='5')
        from . import print_style as ps
        self.merged_color_enabled=tk.BooleanVar(value=self.settings.get('merged_color_enabled',True))
        self.merged_order_colors=[tk.StringVar(value=ps.title(value)) for value in ps.order_colors(self.settings)]
        self.merge_exclusions_enabled=tk.BooleanVar(value=self.settings.get('merge_exclusions_enabled',True))
        self.merge_excluded_worknos=tk.StringVar(value=', '.join(map(str,self.settings['merge_excluded_worknos'])))
        self.ditto_font_size=tk.StringVar(value=str(self.settings.get('ditto_font_size',20)))
        self.ditto_bold=tk.BooleanVar(value=self.settings.get('ditto_bold',True))
        self.ditto_alignment=tk.StringVar(value=ps.DITTO_ALIGN[self.settings.get('ditto_alignment','center')])
        self.ditto_keep_adult=tk.BooleanVar(value=self.settings.get('ditto_keep_adult',True))
        self.serial_superscript=tk.BooleanVar(value=self.settings.get('serial_superscript',False))
        self.serial_font_size=tk.StringVar(value=str(self.settings.get('serial_font_size',14)))
        self.serial_colors={key:tk.StringVar(value=ps.title(value)) for key,value in ps.serial_colors(self.settings).items()}
        self.confirmed=tk.BooleanVar(value=self.settings.get('mapping_confirmed',False))
        self.status=tk.StringVar(value='選擇工作日期後，按下送出即可產生工作簿。')
        self.result_text=tk.StringVar(value='尚未產生檔案')
        self.settings_status=tk.StringVar(value='')
        self.db_status=tk.StringVar(value='DB尚未連線')
        from .desktop_view import build
        build(self)
        self.db.trace_add('write',self.database_changed)
        root.bind('<Configure>',self.resize)
        root.protocol('WM_DELETE_WINDOW',self.close)
        self.poll_id=root.after(100,self.poll);self.startup_id=None
        root.bind('<Destroy>',self.cancel_callbacks,add='+')
        if auto_connect:self.startup_id=root.after(200,self.test_connection)

    def cancel_callbacks(self,event):
        if event.widget!=self.root:return
        for callback in (self.poll_id,self.startup_id):
            if callback:
                try:self.root.after_cancel(callback)
                except tk.TclError:pass

    def refresh_result(self,*_):
        self.result_label.configure(state='normal')
        self.result_label.delete('1.0','end');self.result_label.insert('1.0',self.result_text.get())
        self.result_label.configure(state='disabled');self.result_label.yview_moveto(0)

    def resize(self,event):
        if event.widget==self.root:
            self.status_label.configure(wraplength=max(200,self.export_scroll.canvas.winfo_width()-8))

    def toggle_connection_tools(self,show=None):
        opened=bool(self.connection_tools.winfo_manager())
        show=not opened if show is None else show
        if show:self.connection_tools.pack(fill='x',pady=(12,0))
        else:self.connection_tools.pack_forget()
        self.tools_toggle.configure(text='收合連線工具 ▴' if show else '連線工具 ▾')

    def import_previous_settings(self):
        if self.busy or self.connection_testing or getattr(self,'catalog_loading',False):
            messagebox.showinfo('請稍候','請等候目前的輸出或連線工作完成。',parent=self.root);return
        for window in (getattr(self,'catalog_window',None),getattr(getattr(self,'font_window',None),'window',None),getattr(getattr(self,'color_rule_window',None),'window',None)):
            if window is not None and window.winfo_exists():
                messagebox.showinfo('請先關閉設定視窗','請先儲存並關閉項目或字體設定視窗，再匯入設定。',parent=self.root);return
        source=filedialog.askdirectory(parent=self.root,title='選擇已匯出的設定資料夾或舊版程式資料夾')
        if not source:return
        from . import config_store
        try:
            config_store.read_bundle(source)  # Validate before asking to replace current settings.
            if not messagebox.askyesno('匯入設定',f'將使用此資料夾的列印設定：\n{source}\n\n'+('並沿用其系統設定。\n' if self.import_system.get() else '目前系統設定會保留。\n')+'目前設定會先自動備份。是否匯入？',parent=self.root):return
            result=config_store.import_previous(source,ROOT,self.import_system.get())
            self.settings=get_settings();self.settings.update(load_preferences())
            self.reload_setting_values()
            self.data=None;self.rows=[];self.pending=False
            for name in ('catalog_document',):
                if hasattr(self,name):delattr(self,name)
            self.database_changed()
            self.test_connection()
            note='系統設定已沿用。' if result['system_imported'] else '系統設定維持目前值（未勾選或來源沒有 preferences.json）。'
            self.settings_status.set('列印設定已匯入；'+note+' 已備份於 config_backups。')
            self.settings_status_label.configure(foreground='#243449')
        except (OSError,ValueError,TypeError,KeyError):
            self.settings_status.set('無法匯入：請確認設定完整、JSON 格式及資料夾寫入權限。原設定已保留。')
            self.settings_status_label.configure(foreground='#b42318')
            messagebox.showerror('設定未匯入',self.settings_status.get(),parent=self.root)

    def reload_setting_values(self,include_system=True):
        from . import print_style as ps
        s=self.settings
        if include_system:
            self.db.set(s['database_path']);self.output_dir.set(s['output_directory'])
            self.order_mode.set('split' if s['order_mode']=='split' else 'merge_first' if s['merge_workno_style']=='first' else 'merge')
        for attr,key in [('show_headers','show_column_headers'),('confirmed','mapping_confirmed'),
                         *[(x,x) for x in ('fixed_20_rows','ditto_bio','ditto_patient','show_region_lines','export_glucose_ac','merged_color_enabled','ditto_bold')]]:
            getattr(self,attr).set(s[key])
        for variable,value in zip(self.merged_order_colors,ps.order_colors(s)):variable.set(ps.title(value))
        self.merge_exclusions_enabled.set(s['merge_exclusions_enabled'])
        self.merge_excluded_worknos.set(', '.join(map(str,s['merge_excluded_worknos'])))
        self.ditto_font_size.set(str(s['ditto_font_size']))
        self.ditto_alignment.set(ps.DITTO_ALIGN[s.get('ditto_alignment','center')])
        self.ditto_keep_adult.set(s.get('ditto_keep_adult',True))
        self.serial_superscript.set(s.get('serial_superscript',False))
        self.serial_font_size.set(str(s.get('serial_font_size',14)))
        for key,value in ps.serial_colors(s).items():self.serial_colors[key].set(ps.title(value))

    def backup_settings(self):
        if self.busy:return
        if not self.save_preferences(False):return
        folder=filedialog.askdirectory(parent=self.root,title='選擇匯出設定的儲存位置')
        if not folder:return
        from . import config_store
        try:
            dest=Path(folder)/('工作簿設定_'+dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
            config_store.export_backup(ROOT,dest)
            self.settings_status.set(f'全部設定已匯出：{dest.name}；可用「匯入設定」載入。')
        except (OSError,ValueError):
            self.settings_status.set('無法匯出設定，請選擇可寫入的資料夾。');self.settings_status_label.configure(foreground='#b42318')

    def save_system_preferences(self,notify=True):
        return self.save_preferences(notify,scope='system')

    def choose_merged_color(self,index):
        from tkinter.colorchooser import askcolor
        from . import print_style as ps
        variable=self.merged_order_colors[index];value=ps.choice(variable.get())
        try:value=ps.color(value)
        except ValueError:value=ps.BLACK if index==0 else ps.BLUE
        picked=askcolor(color=value,parent=self.root,title='併單項目顏色')[1]
        if picked:variable.set(picked.upper())

    def font_editor(self):
        from .font_settings import FontSettings
        editor=getattr(self,'font_window',None)
        if editor and editor.window.winfo_exists():
            editor.window.lift();return
        def save(values):
            candidate=dict(self.settings,font_sizes=values)
            save_print_settings(candidate,CONFIG)
            self.settings['font_sizes']=values
            self.settings_status.set('各欄字體已儲存，下次輸出與重新開啟程式都會使用。')
        try:self.font_window=FontSettings(self.root,self.settings,save)
        except ValueError as error:
            messagebox.showerror('列印字體設定',str(error),parent=self.root)

    def color_rule_editor(self):
        if self.busy or getattr(self,'catalog_loading',False):return
        editor=getattr(self,'color_rule_window',None)
        if editor and editor.window.winfo_exists():editor.window.lift();return
        catalog=getattr(self,'catalog_window',None)
        if catalog is not None and catalog.winfo_exists():
            messagebox.showinfo('請先關閉項目設定','請先儲存並關閉項目設定視窗，再調整配色規則。',parent=self.root);return
        from .color_rule_ui import ColorRules
        def save(values):
            from . import catalog_cache,layout_settings
            candidate=copy.deepcopy(self.settings);candidate['print_color_rules']=values
            from .config_store import read
            active=read(catalog_cache.PATH) if catalog_cache.PATH.exists() else None
            if active:
                if not isinstance(active.get('raw_catalog'),dict) or not isinstance(active.get('source'),dict):
                    raise ValueError('JSON 字典格式不正確，原設定已保留；請先更新項目清單。')
                updated=catalog_cache.apply_settings(active,candidate,layout_settings.load())
                self.catalog_document=updated
            else:save_print_settings(candidate,CONFIG)
            self.settings['print_color_rules']=values
            self.settings_status.set('列印代碼配色規則已儲存，下次輸出生效。')
            self.settings_status_label.configure(foreground='#243449')
        try:self.color_rule_window=ColorRules(self.root,self.settings,save)
        except ValueError as error:messagebox.showerror('配色規則',str(error),parent=self.root)

    def choose_db(self):
        p=filedialog.askopenfilename(filetypes=[('Access 資料庫','*.mdb *.accdb')])
        if p:self.db.set(p);self.save_system_preferences(False)
    def choose_output(self):
        p=filedialog.askdirectory(initialdir=self.output_dir.get() or str(ROOT))
        if p:self.output_dir.set(p)
    def save_preferences(self,notify=True,scope='all'):
        from . import print_style as ps
        from . import config_store
        candidate=copy.deepcopy(self.settings)
        invalid_control=None
        try:
            if scope!='system':
                from .merge_settings import parse_exclusions
                colors=[]
                for variable,control in zip(self.merged_order_colors,self.merged_color_inputs):
                    invalid_control=control
                    colors.append(ps.color(ps.choice(variable.get())))
                invalid_control=self.merge_exclusions_input
                excluded=parse_exclusions(self.merge_excluded_worknos.get())
                invalid_control=self.ditto_size_input
                ditto_size=ps.validate_settings({'ditto_font_size':self.ditto_font_size.get()})
                invalid_control=self.ditto_alignment_input
                alignment=next((key for key,value in ps.DITTO_ALIGN.items() if value==self.ditto_alignment.get()),None)
                if alignment is None:raise ValueError('同上符號位置請選擇置左、置中或置右。')
                invalid_control=self.serial_size_input
                ps.validate_settings({'serial_font_size':self.serial_font_size.get()})
                serial_size=float(self.serial_font_size.get());serial_colors={}
                for key,variable in self.serial_colors.items():
                    invalid_control=self.serial_color_inputs[key]
                    serial_colors[key]=ps.color(ps.choice(variable.get()))
                candidate.update(show_column_headers=self.show_headers.get(),mapping_confirmed=self.confirmed.get(),
                    fixed_20_rows=self.fixed_20_rows.get(),ditto_bio=self.ditto_bio.get(),ditto_patient=self.ditto_patient.get(),
                    show_region_lines=self.show_region_lines.get(),export_glucose_ac=self.export_glucose_ac.get(),glucose_ac_columns=5,
                    merged_color_enabled=self.merged_color_enabled.get(),merged_order_colors=colors,
                    merge_exclusions_enabled=self.merge_exclusions_enabled.get(),merge_excluded_worknos=excluded,
                    ditto_font_size=ditto_size,ditto_bold=self.ditto_bold.get(),
                    ditto_alignment=alignment,ditto_keep_adult=self.ditto_keep_adult.get(),
                    serial_superscript=self.serial_superscript.get(),serial_font_size=serial_size,serial_colors=serial_colors)
                ps.validate_settings(candidate)
            if scope!='print':
                candidate.update(database_path=self.db.get().strip(),output_directory=self.output_dir.get().strip(),
                    order_mode='split' if self.order_mode.get()=='split' else 'merge',
                    merge_workno_style='first' if self.order_mode.get()=='merge_first' else 'all')
        except ValueError as error:
            self.settings_status.set(str(error));self.settings_status_label.configure(foreground='#b42318')
            self.tabs.select(self.print_page)
            if invalid_control is not None:
                self.print_scroll.reveal(invalid_control);invalid_control.focus_set()
            return False
        try:
            targets=[]
            if scope!='system':targets.append((CONFIG,config_store.print_only(candidate)))
            if scope!='print':targets.append((PREFERENCES,{k:candidate[k] for k in PREFERENCE_KEYS}))
            config_store.transaction(targets)
        except OSError:
            self.settings_status.set('無法儲存設定，原檔已保留；請確認資料夾寫入權限。');self.settings_status_label.configure(foreground='#b42318');return False
        self.settings.update(candidate)
        self.settings_status.set('設定已儲存，下次開啟會保留。')
        self.settings_status_label.configure(foreground='#243449')
        if notify:self.test_connection()
        return True
    def set_connection_state(self,text,color):
        self.db_status.set(text);self.db_lamp.itemconfigure(self.lamp_circle,fill=color)
    def database_changed(self,*_):
        self.connection_token+=1;self.connected_path=None;self.connection_testing=False
        self.set_connection_state('DB尚未連線','#929baa')
        self.connection_button.config(state='normal',text='測試連線')
        self.repair_button.config(state='disabled')
        self.catalog_info.set('資料庫路徑已變更，請重新載入或更新清單')
    def install_access_component(self):
        from . import access_runtime
        report=access_runtime.last_report(self.db.get().strip())
        arch,reason=access_runtime.repair_plan(report)
        if not arch:
            self.settings_status.set(reason);return
        messagebox.showinfo('安裝 Access 相依元件',
            f'偵測到需要 {arch} 版 Microsoft 365 Access Runtime。\n\n'
            '1. 請先確認現場電腦可以連上網路。\n'
            '2. 在 Windows 管理員權限提示按「是」，並完成 Microsoft 安裝畫面。\n'
            '3. 安裝結束後程式會重新測試連線；若要求重開機，重開後再啟動工作簿。\n\n'
            '若安裝顯示 Office 不相容，請保留該訊息；不要移除現有 Office。',parent=self.root)
        self.test_connection(install=True)
    def export_connection_diagnostic(self):
        from . import access_runtime
        report=access_runtime.last_report(self.db.get().strip())
        if not report:
            self.settings_status.set('請先按測試連線，取得診斷結果。');return
        path=filedialog.asksaveasfilename(defaultextension='.json',initialfile='連線診斷.json',filetypes=[('JSON','*.json')])
        if path:
            try:save_json(path,report);self.settings_status.set('連線診斷已匯出；內容僅含版本、位元與錯誤碼，不含病患或完整路徑。')
            except OSError:self.settings_status.set('無法儲存診斷檔，請選擇可寫入的資料夾。')
    def test_connection(self,install=False):
        if self.busy or self.connection_testing:return
        path=self.db.get().strip();self.connection_token+=1;token=self.connection_token
        self.connected_path=None
        if not path:
            self.set_connection_state('DB未設定','#c94343');self.tabs.select(self.settings_page)
            self.tabs.select(self.system_page)
            self.settings_status.set('請選擇 Access 資料庫，然後按「測試連線」。');return
        if not self.save_system_preferences(False):return
        self.connection_testing=True;self.set_connection_state('DB連線測試中…','#d49716')
        self.connection_button.config(state='disabled',text='連線測試中…')
        self.repair_button.config(state='disabled')
        def work():
            try:
                from . import access_runtime
                ok,message=check_connection(path)
                if not ok and install and token==self.connection_token:
                    def progress(text):self.events.put(('connection_progress',(token,path,text)))
                    repair=access_runtime.install_runtime(access_runtime.last_report(path),progress)
                    ok,message=check_connection(path)
                    report=access_runtime.last_report(path)
                    access_runtime.record(path,dict(report,repair={k:repair[k] for k in ('code','exit_code','arch') if k in repair}))
                    if not ok:message=repair['message']+'\n'+message+'\n若 Microsoft 安裝畫面仍在進行，完成後請再按測試連線。'
            except Exception:
                from . import access_runtime
                access_runtime.record(path,{'ok':False,'code':'ENVIRONMENT_FAILED','attempts':[]})
                ok,message=False,'連線診斷未完成，請匯出連線診斷供檢查。［ENVIRONMENT_FAILED］'
            self.events.put(('connection',(token,path,ok,message)))
        threading.Thread(target=work,daemon=True).start()
    def connection_complete(self,result):
        token,path,ok,message=result
        if token!=self.connection_token or path!=self.db.get().strip():return
        self.connection_testing=False;self.connection_button.config(state='normal',text='測試連線')
        self.connected_path=path if ok else None
        self.set_connection_state('DB連線成功' if ok else 'DB連線失敗','#21864a' if ok else '#c94343')
        self.settings_status.set('連線成功，路徑已保存。可回到匯出工作簿選擇日期。' if ok else message)
        self.settings_status_label.configure(foreground='#21864a' if ok else '#b42318')
        from . import access_runtime
        report=access_runtime.last_report(path)
        arch,reason=access_runtime.repair_plan(report)
        self.repair_button.config(state='normal' if not ok and arch else 'disabled')
        if not ok:self.toggle_connection_tools(True)
        if not ok and report.get('code')=='NO_PROVIDER' and not report.get('repair'):
            self.settings_status.set(message+'\n'+(f'請按「安裝 Access 元件」，程式會使用隨附的 {arch} 官方安裝檔；安裝時需要網路與 Windows 管理員權限。' if arch else reason))
        elif ok and report.get('bits'):
            self.settings_status.set(f"連線成功，已自動選用 {report['bits']} 位元 Access 驅動，路徑已保存。可回到匯出工作簿選擇日期。")
        if not ok and not self.busy:
            self.tabs.select(self.settings_page);self.tabs.select(self.system_page)
    def submit(self):
        if self.busy:return
        if self.connected_path!=self.db.get().strip() or self.connection_testing:
            self.export_error('尚未確認資料庫連線，請先測試連線後再送出。')
            self.tabs.select(self.settings_page);self.test_connection();return
        try:day=dt.date.fromisoformat(self.date.get().strip()).isoformat()
        except ValueError:
            self.export_error('請輸入正確日期，例如 2026-08-29。');self.date_entry.focus_set();return
        database=Path(self.db.get().strip())
        if not self.db.get().strip() or not database.is_file():
            message='請先選擇可讀取的 Access 資料庫，再回到匯出頁送出。'
            self.export_error(message);self.settings_status.set(message);self.tabs.select(self.settings_page);return
        if not self.output_dir.get().strip():
            self.export_error('請選擇輸出資料夾。');self.settings_status.set('請選擇輸出資料夾。');self.tabs.select(self.settings_page);return
        if not self.save_preferences(False):
            self.export_error(self.settings_status.get());return
        from . import layout_settings
        try:
            settings=copy.deepcopy(self.settings);settings['layout']=layout_settings.load()
            layout_settings.validate(settings['layout'])
        except (OSError,ValueError):
            self.export_error('列印規則無法讀取，請至設定檢查簡稱與外送設定。');return
        target=Path(self.output_dir.get().strip())
        self.start_export(lambda:self.generate(database,day,target,settings))
    def export_error(self,message):
        self.last_pdf=None;self.open_button.config(state='disabled')
        self.status.set(message);self.status_label.configure(foreground='#b42318',font=('Microsoft JhengHei UI',12,'bold'))
        self.result_text.set('本次未產生 PDF。請依上方紅字提示處理後再試。')
        self.result_label.configure(foreground='#b42318',font=('Microsoft JhengHei UI',12,'bold'))
        self.settings_status.set(message);self.settings_status_label.configure(foreground='#b42318')
    def start_export(self,operation,forced=False):
        self.busy=True;self.submit_button.config(state='disabled',text='正在產生工作簿…')
        for page in (self.system_page,self.print_page):self.tabs.tab(page,state='disabled')
        self.date_picker.set_enabled(False);self.open_button.config(state='disabled');self.last_pdf=None
        for b in self.mode_buttons:b.config(state='disabled')
        self.result_text.set('');self.status.set('正在強制排版，請稍候。' if forced else '正在讀取當日資料並排版，請稍候。')
        self.status_label.configure(foreground='#243449',font=('Microsoft JhengHei UI',11))
        self.result_label.configure(foreground='#243449',font=('Microsoft JhengHei UI',11))
        def work():
            try:self.events.put(('done',operation()))
            except ValueError as e:self.events.put(('error',str(e)))
            except Exception:self.events.put(('error','未能完成輸出，請確認輸出資料夾可寫入，檔案未被占用。'))
        threading.Thread(target=work,daemon=True).start()
    def generate(self,database,day,target,settings):
        try:data=read_access(database,day,include_identity=True)
        except Exception:
            self.events.put(('connection',(self.connection_token,str(database),False,'資料庫讀取失敗，請重新測試連線。')))
            raise
        rows=make_rows(data,settings)
        if not rows:return {'empty':True,'date':day}
        return self.write_output(data,rows,day,target,settings)
    def write_output(self,data,rows,day,target,settings):
        target.mkdir(parents=True,exist_ok=True)
        mode='併單' if settings.get('order_mode')=='merge' else '拆單'
        if mode=='併單' and settings.get('merge_workno_style')=='first':mode='併單_第一工作號'
        forced='_強制輸出' if settings.get('force_export') else ''
        path=target/f'工作簿_{day}_{mode}{forced}_{dt.datetime.now():%H%M%S_%f}.pdf'
        from . import pdf_document
        try:summary=pdf_document.export(path,rows,day,settings,draft=not settings.get('mapping_confirmed',False),renderer=export_pdf)
        except LayoutCapacityError as e:
            if settings.get('force_export'):raise
            return {'capacity_error':str(e),'retry':(data,rows,day,target,settings)}
        summary.update(input_orders=len(data['headers']),order_mode=mode)
        warnings=[]
        try:save_session(path.with_suffix('.工作進度.json'),data,rows,settings,export_summary=summary)
        except OSError:warnings.append('PDF 已完成，但工作進度未能儲存。')
        return {'path':path,'summary':summary,'data':data,'rows':rows,'warning':'\n'.join(warnings)}
    def poll(self):
        try:
            kind,result=self.events.get_nowait()
            if kind=='update':self.update_complete(result)
            elif kind=='connection':self.connection_complete(result)
            elif kind=='connection_progress':
                token,path,message=result
                if token==self.connection_token and path==self.db.get().strip():
                    self.settings_status.set(message);self.set_connection_state('DB元件安裝中…','#d49716')
            elif kind=='catalog':
                token,mode,document,error=result
                self.catalog_loading=False
                for button in self.catalog_tools:button.configure(state='normal')
                if token==self.connection_token:
                    if error:
                        self.settings_status.set(error);self.settings_status_label.configure(foreground='#b42318')
                    else:
                        self.catalog_document=document
                        if document is not None:
                            self.update_catalog_info(document)
                            self.settings_status.set('清單已載入。');self.settings_status_label.configure(foreground='#243449')
                            if mode=='export_json':self.export_catalog_json()
                            elif mode=='import_json':self.import_catalog_json()
                            elif mode and mode!='summary':self.show_catalog(mode)
                        else:self.catalog_info.set('尚無相符的本機清單，請從資料庫更新清單。')
            else:self.complete(kind,result)
        except queue.Empty:pass
        self.poll_id=self.root.after(100,self.poll)
    def complete(self,kind,result):
        self.busy=False;self.submit_button.config(state='normal',text='送出並產生 PDF')
        for page in (self.system_page,self.print_page):self.tabs.tab(page,state='normal')
        self.date_picker.set_enabled(True)
        for b in self.mode_buttons:b.config(state='normal')
        if not self.connected_path:self.tabs.select(self.settings_page)
        if kind=='error':self.export_error(result);return
        if result.get('capacity_error'):
            reason=result['capacity_error'];self.export_error(reason)
            fixed=result['retry'][4].get('fixed_20_rows',True)
            format_note='強制輸出維持 A4 直式、每頁20列，檢驗項目不拆成續頁；Glucose AC&PC 填入格依設定放在頁首。生化區最多三小列。' if fixed else '自動列高仍無法容納這筆內容；強制輸出會縮字，讓單筆完整放入 A4 頁面，不拆成續列。'
            if messagebox.askyesno('版面空間不足，是否強制輸出？',reason+'\n\n'+format_note+'\n必要時會繼續縮小字體、縮短結果空白，保留全部檢驗項目；調整過的工作號會標紅，請逐筆核對。\n\n是否強制輸出本次工作簿？',parent=self.root,default='no'):
                data,rows,day,target,settings=result['retry']
                forced_settings=copy.deepcopy(settings);forced_settings['force_export']=True
                self.start_export(lambda:self.write_output(data,rows,day,target,forced_settings),forced=True)
            return
        if result.get('empty'):
            self.export_error(f"{result['date']} 沒有檢驗資料，請確認日期。");return
        self.data=result['data'];self.rows=result['rows'];self.last_pdf=result['path']
        s=result['summary'];self.status.set(result['warning'] or '完成，可以開啟 PDF 檢查並列印。')
        if result['warning']:self.status_label.configure(foreground='#b42318',font=('Microsoft JhengHei UI',12,'bold'))
        if s.get('forced_adjustments'):
            minimum=min(r['min_font_size'] for r in s['forced_adjustments'])
            self.status.set(f'強制輸出完成，最小字級 {minimum:g} pt；請核對紅字工作號與縮排內容。'+result['warning'])
            self.status_label.configure(foreground='#b42318',font=('Microsoft JhengHei UI',12,'bold'))
        review=''
        if s.get('forced_adjustments'):
            affected=s['forced_adjustments']
            review='\n需核對工作號：'+'、'.join(r['workno'] for r in affected[:10])
            if len(affected)>10:review+=f" 等 {len(affected)} 列（詳見 PDF 紅字及工作進度檔）"
        extra=''
        if s.get('glucose_ac',{}).get('enabled'):
            sheet=s['glucose_ac'];extra=f"\n\n頁首 Glucose AC&PC 填入格：{sheet['records']} 筆 · 5 列 × 5 欄 · 每 25 格接下頁"
        self.result_text.set(f"{s.get('order_mode','拆單')} · {s.get('input_orders',s['records'])} 張單 → {s['records']} 列 · {s['pages']} 頁{review}\n\n{self.last_pdf}{extra}");self.open_button.config(state='normal')
        self.open_pdf()
    def open_pdf(self):
        if self.last_pdf and self.last_pdf.exists():
            try:os.startfile(self.last_pdf)
            except OSError:
                self.open_output();self.status.set('PDF 已完成，無法直接開啟，請從輸出資料夾查看。')
    def open_output(self):
        if not self.output_dir.get().strip():
            self.tabs.select(self.settings_page);self.settings_status.set('請先選擇輸出資料夾。');return
        try:
            folder=Path(self.output_dir.get().strip());folder.mkdir(parents=True,exist_ok=True);os.startfile(folder)
        except OSError:self.status.set('無法開啟輸出資料夾，請至設定確認位置。')
    def refresh(self):pass
    def catalog_description(self,document):
        count=document['counts'];stamp=document['source'].get('fetched_at','未知')
        pending=document['review'].get('unresolved_dictionary_rows',0)
        return f"JSON 清單：診所 {count['hospitals']}／單項 {count['items']}／套組 {count['sets']}，資料庫更新：{stamp}"+(f'；{pending} 筆來源代碼待核對（見 JSON unresolved）' if pending else '')

    def update_catalog_info(self,document):
        count=document['counts'];stamp=document['source'].get('fetched_at','未知').replace('T',' ')
        pending=document['review'].get('unresolved_dictionary_rows',0)
        self.catalog_info.set(f"診所 {count['hospitals']} · 套組 {count['sets']} · 單項 {count['items']}\n資料庫更新：{stamp}"+(f'\n{pending} 筆來源代碼待核對' if pending else ''))
        self.catalog_help.set('清單只含字典，不含病患資料。匯出含目前設定與校對資料；匯入只套用 settings，不改資料庫路徑。來源代碼待核對的內容可在匯出 JSON 的 lists.unresolved 查看。')

    def catalog_editor(self,mode,refresh=False):
        if self.busy or getattr(self,'catalog_loading',False):return
        current=getattr(self,'catalog_window',None)
        if current is not None and current.winfo_exists():
            if mode in ('export_json','import_json') or refresh:
                if not current.request_close():return
            else:
                current.lift()
                if mode and mode!='summary':current.catalog_tabs.select({'clinics':1,'subregions':2}.get(mode,0))
                return
        path=self.db.get().strip()
        if refresh and not path:
            self.settings_status.set('請先設定資料庫路徑，再更新清單。');return
        self.catalog_loading=True;token=self.connection_token;path=self.db.get().strip()
        for button in self.catalog_tools:button.configure(state='disabled')
        self.settings_status.set('正在從資料庫更新 JSON 清單…' if refresh else '正在載入本機 JSON 清單…')
        settings=copy.deepcopy(self.settings)
        def work():
            from . import catalog_cache,layout_settings
            try:
                layout=layout_settings.load()
                document=None if refresh else catalog_cache.load(path,settings,layout)
                if document is None and mode!='summary':
                    if not path:raise ValueError('尚無可用 JSON 清單，請設定資料庫路徑後更新。')
                    document=catalog_cache.refresh(path,settings,layout,read_catalog)
                error=None
            except ValueError as e:document=None;error=str(e)
            except Exception:document=None;error='無法載入清單，請檢查資料庫連線及 print_settings 資料夾寫入權限；舊清單仍保留。'
            self.events.put(('catalog',(token,mode,document,error)))
        threading.Thread(target=work,daemon=True).start()

    def show_catalog(self,mode):
        from .catalog_settings import editor
        from . import catalog_cache
        document=self.catalog_document
        def save(candidate,layout):
            newrows=make_rows(self.data,dict(candidate,layout=layout)) if self.data else []
            updated=catalog_cache.apply_settings(self.catalog_document,candidate,layout)
            self.catalog_document=updated;self.confirmed.set(candidate.get('mapping_confirmed',False))
            if self.data:self.rows=newrows
            self.update_catalog_info(updated)
            self.settings_status.set('項目列印設定與 JSON 清單已同步保存。')
            return updated
        usable,_=catalog_cache.display_catalog(document['raw_catalog'])
        self.catalog_window=editor(self.root,usable,self.settings,mode,on_save=save,
            resolved_rows=document['records'])
    def export_catalog_json(self):
        from . import catalog_cache
        destination=filedialog.asksaveasfilename(parent=self.root,title='匯出 JSON 校對清單',defaultextension='.json',initialfile='診所與檢驗項目清單.json',filetypes=[('JSON 清單','*.json')])
        if not destination:return
        try:
            from . import layout_settings
            self.catalog_document=catalog_cache.reconcile(self.catalog_document,self.settings,layout_settings.load())
            catalog_cache.write(self.catalog_document,destination)
        except (OSError,ValueError):messagebox.showerror('未能匯出','請確認設定完整且目標資料夾可寫入。',parent=self.root);return
        messagebox.showinfo('已匯出','已匯出診所、單項、套組成員與目前分組／列印設定。',parent=self.root)

    def import_catalog_json(self):
        from . import catalog_cache
        source=filedialog.askopenfilename(parent=self.root,title='匯入 JSON 設定',filetypes=[('JSON 清單','*.json')])
        if not source:return
        try:
            candidate,layout=catalog_cache.import_settings(load_json(source),self.settings,self.catalog_document['raw_catalog'])
            # Validate against the current database dictionary before asking to apply.
            catalog_cache.build(self.catalog_document['raw_catalog'],candidate,layout,self.catalog_document['source'])
        except (ValueError,OSError,TypeError):
            messagebox.showerror('未匯入','JSON 設定不完整、規則衝突或無法讀取，原設定保留。',parent=self.root);return
        if not messagebox.askyesno('套用 JSON 設定？',f"將依代碼覆蓋目前的機器分組、列印簡稱與診所簡稱。\n機器規則 {len(candidate['rules'])} 筆、列印規則 {len(layout['rules'])} 筆、診所簡稱 {len(layout['clinic_aliases'])} 筆。\n\n資料庫路徑、輸出資料夾及目前資料庫字典保留。\n清單中的 lists 區塊僅供校對；套用 settings 區塊。",parent=self.root,default='no'):return
        try:updated=catalog_cache.apply_settings(self.catalog_document,candidate,layout)
        except (OSError,ValueError):
            messagebox.showerror('未完成匯入','設定無法寫入，請檢查檔案權限。',parent=self.root);return
        self.settings.clear();self.settings.update(candidate);self.confirmed.set(False);self.catalog_document=updated
        self.reload_setting_values(include_system=False);self.update_catalog_info(updated);self.settings_status.set('JSON 設定已套用，請核對分組後再輸出。')

    def mapping(self,catalog=None):
        if catalog is None:self.catalog_editor('mapping');return
        from .catalog_settings import editor
        return editor(self.root,catalog,self.settings,'items')

    def save_machine_settings(self,candidate):
        # Revalidate against loaded records before persisting a grouping change.
        newrows=make_rows(self.data,candidate) if self.data else []
        save_print_settings(candidate,CONFIG)
        self.confirmed.set(False)
        if self.data:self.rows=newrows
        self.settings_status.set('機器分組已保存，請重新核對。')

    def check_updates(self):
        if self.busy or self.update_checking:return
        self.update_checking=True;self.update_button.configure(state='disabled')
        self.update_status.set('正在查詢 GitHub Release…')
        def work():
            from .updates import latest,UpdateError
            try:self.events.put(('update',(latest(),None)))
            except UpdateError as error:self.events.put(('update',(None,str(error))))
            except Exception:self.events.put(('update',(None,'無法取得更新資訊，請稍後重試。')))
        threading.Thread(target=work,daemon=True).start()

    def update_complete(self,result):
        from . import updates
        release,error=result
        self.update_checking=False;self.update_button.configure(state='normal')
        if error:
            self.update_status.set(error)
            messagebox.showerror('無法檢查更新',error,parent=self.root);return
        if updates.version_key(release['version'])<=updates.version_key(APP_VERSION):
            self.update_status.set(f'目前已是最新版本 {APP_VERSION}');return
        self.update_status.set(f"可更新至 {release['version']}")
        if self.busy:return
        import sys
        if not getattr(sys,'frozen',False):
            messagebox.showinfo('原始碼模式','請使用安裝包中的 EXE 執行自動更新。',parent=self.root);return
        if not messagebox.askyesno('下載並更新',f"目前：{APP_VERSION}\n新版：{release['version']}\n下載：約 {release['size']/1048576:.1f} MB\n\n將儲存設定並關閉工作簿，由獨立更新工具下載、更新及重啟。\n現場資料庫、輸出檔案與設定均保留。\n\n現在更新？",parent=self.root):return
        window=getattr(self,'catalog_window',None)
        if window is not None and window.winfo_exists() and not window.request_close():return
        if not self.save_preferences(False):return
        try:
            from .update_install import application_pids
            if any(pid!=os.getpid() for pid in application_pids(ROOT/updates.EXE)):
                raise updates.UpdateError('請先關閉此安裝資料夾的其他工作簿視窗，再按更新。')
            process=updates.launch(ROOT,os.getpid(),release)
        except Exception as error:
            detail=str(error) if isinstance(error,updates.UpdateError) else '無法啟動更新工具，請確認暫存資料夾可寫入與防毒軟體設定。'
            messagebox.showerror('更新未開始',detail,parent=self.root);return
        # Give the independent process time to report an immediate launch failure.
        self.update_button.configure(state='disabled')
        self.root.withdraw()
        import time
        self.update_handoff_deadline=time.monotonic()+20
        self.root.after(700,lambda:self.finish_update_handoff(process))

    def finish_update_handoff(self,process):
        import time
        folder=process.workbook_folder
        if process.poll() is not None or time.monotonic()>self.update_handoff_deadline:
            (folder/'cancel').touch()
            self.root.deiconify()
            self.update_button.configure(state='normal')
            messagebox.showerror('更新未開始','更新工具未能啟動，原程式保持開啟。',parent=self.root);return
        if not (folder/'ready').exists():
            self.root.after(100,lambda:self.finish_update_handoff(process));return
        (folder/'go').touch()
        self.root.destroy()

    def close(self):
        if self.busy:messagebox.showinfo('正在輸出','請等候本次輸出完成。');return
        window=getattr(self,'catalog_window',None)
        if window is not None and window.winfo_exists() and not window.request_close():return
        if not self.save_preferences(False):return
        self.root.destroy()

def main():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError,OSError):pass
    root=tk.Tk();root.withdraw()
    try:
        from .config_store import ensure_configuration
        ensure_configuration(ROOT)
        App(root);root.deiconify()
    except Exception:
        root.withdraw();messagebox.showerror('啟動失敗','設定檔無法讀取或移轉。請檢查 preferences.json、print_settings 資料夾及寫入權限；原設定已保留，未重設為預設值。');root.destroy();return
    root.mainloop()
if __name__=='__main__':main()
