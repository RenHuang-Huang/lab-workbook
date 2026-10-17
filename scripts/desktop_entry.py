"""Frozen Windows entry point; diagnostic mode never reads the laboratory database."""
import sys
from pathlib import Path

def self_test(destination):
    import json,tempfile,tkinter as tk
    from workbook import core,layout_settings as ls,catalog_cache
    from pypdf import PdfReader
    with tempfile.TemporaryDirectory(prefix='workbook_check_') as folder:
        folder=Path(folder)
        from workbook import config_store
        bundle=config_store.read_bundle(core.ROOT,allow_defaults=True)
        settings=bundle['settings'];layout=bundle['layout']
        from workbook import subregions
        ranked=[dict(label=str(n),placement=dict(subregion='A',position=n,position_mode='order')) for n in (6,2,5,3)]
        placed=subregions.arrange(ranked,'生化／糞便',layout)
        assert [(g['letter'],[i['label'] for _,i in g['entries']]) for g in placed]==[('A',['2','3','5']),('B',['6'])]
        assert subregions.arrange(ranked[:1],'CBC／尿液',layout)[0]['entries'][0][0]==1
        for zone in subregions.ZONE_KEYS:
            groups=subregions.arrange(ranked,zone,layout,expand_vertical=True)
            assert all(position<=3 for group in groups for position,_ in group['entries'])
            assert len(groups)==2
        upgrade=folder/'upgrade'
        for target,value in config_store.targets(upgrade/'defaults',bundle,include_system=False):core.save_json(target,value)
        core.save_json(upgrade/'defaults/system_seed.json',dict(config_store.system_defaults(upgrade),database_path='synthetic.mdb'))
        config_store.ensure_configuration(upgrade)
        assert core.load_json(upgrade/'preferences.json')['database_path']=='synthetic.mdb'
        changed=dict(settings,ditto_font_size=23,ditto_bold=True)
        core.save_json(upgrade/'print_settings/settings.json',changed)
        config_store.ensure_configuration(upgrade)
        assert core.load_json(upgrade/'print_settings/settings.json')['ditto_font_size']==23
        assert not set(config_store.SYSTEM_KEYS)&core.load_json(upgrade/'print_settings/settings.json').keys()
        core.CONFIG=folder/'settings.json';ls.PATH=folder/'layout.json'
        catalog_cache.PATH=folder/'catalog.json'
        core.save_json(core.CONFIG,settings);ls.save(layout)
        import workbook.app as app_module
        assert app_module.PREFERENCES==core.ROOT/'preferences.json'
        if getattr(sys,'frozen',False):assert app_module.PREFERENCES.parent==Path(sys.executable).resolve().parent
        app_module.PREFERENCES=Path(folder)/'preferences.json'
        from workbook.app import App
        root=tk.Tk();root.withdraw()
        try:
            app=App(root,auto_connect=False);root.update()
            assert app.order_mode.get()=='merge_first' and app.db.get()==''
            assert core.load_json(app_module.PREFERENCES)==app_module.default_preferences()
            assert app.submit_button['text']=='送出並產生 PDF'
            assert [app.tabs.tab(t,'text') for t in app.tabs.tabs()]==['匯出工作簿','系統設定','列印設定','病例查詢']
            assert not app.case_lookup.ready
            app.case_lookup.build()
            app.case_lookup.number.set('00001')
            from workbook.case_lookup import build_result
            case_data=core.load_json(core.ROOT/'assets/demo.json')
            case_data['details'][0]['LCHK_VALUE']='101'
            case_result=build_result(case_data,'1',settings,layout)
            assert case_result['matched_count']==1 and case_result['order_count']==1
            app.case_lookup.render(case_result,case_data['date'],'1')
            assert len(app.case_lookup.tree.get_children())==1
            app.case_lookup.clear();assert not app.case_lookup.tree.get_children()
            app.usage_statistics();usage=app.usage_view
            assert usage.exclude.get() is True and not usage.running
            usage.snapshot_settings()
            usage.data=dict(usage_statistics=True,start_date='2023-10-15',end_date='2026-10-14',order_count=1,
                unknown_detail_count=0,unresolved_detail_count=0,linked_detail_count=0,
                catalog={key:case_data.get(key,[]) for key in ('items','sets','set_members','hospitals')},
                counts=[dict(kind='I',code='101',total_count=1,direct_count=1,uncertain_count=0,
                    first_used='2026-10-14',last_used='2026-10-14',first_direct='2026-10-14',last_direct='2026-10-14')])
            usage.render();assert len(usage.tables['單項'].rows)==1
            assert usage.document['rows'][0]['count']==1;usage.close()
            assert not hasattr(app,'setting_tabs')
            assert len(app.print_scroll.buttons)==6
            assert [b.cget('text') for b in app.print_scroll.buttons]==['頁面版面','欄位與分區','併單與同上符號','併單來源配色','項目列印與簡稱','項目對應顏色']
            assert app.tabs.buttons[1].master.pack_info()['side']=='bottom'
            assert not app.tabs.expanded
            assert not hasattr(app,'sidebar_toggle')
            app.tabs.buttons[0].invoke();assert app.tabs.expanded
            app.tabs.set_expanded(False);assert not app.tabs.expanded
            app.tabs.buttons[2].invoke()
            assert app.tabs.expanded and app.tabs.select()==str(app.print_page)
            app.tabs.buttons[2].invoke();assert not app.tabs.sections_open
            app.tabs.buttons[2].invoke();assert app.tabs.sections_open
            app.tabs.buttons[0].invoke();assert app.tabs.select()==str(app.export_page)
            for index,button in enumerate(app.print_scroll.buttons):
                button.invoke()
                assert [bool(f.winfo_manager()) for f in app.print_cards]==[i==index for i in range(6)]
            app.print_scroll.select(0)
            for button,value in zip(app.mode_buttons,('split','merge','merge_first')):
                button.invoke();assert app.order_mode.get()==value
                button.config(state='disabled');button.invoke();assert app.order_mode.get()==value
                button.config(state='normal')
            def labels(widget):
                out=[]
                for child in widget.winfo_children():
                    try:out.append(str(child.cget('text')))
                    except tk.TclError:pass
                    out.extend(labels(child))
                return out
            assert not any('範例' in x for x in labels(root))
            assert '測試連線' in labels(root)
            assert '暫時加印檢驗單備註' in labels(root) and '依備註欄調整' in labels(root)
            note_options={name:bool(settings.get(name,True)) for name in ('show_order_notes','apply_order_note_rules')}
            for name,value in note_options.items():
                assert getattr(app,name).get()==value
                getattr(app,name).set(not value)
            assert app.save_preferences(False,scope='print')
            for name,value in note_options.items():
                assert core.get_settings()[name]==(not value)
                getattr(app,name).set(value)
            assert app.save_preferences(False,scope='print')
            assert '安裝 Access 元件' in labels(root) and '匯出連線診斷' in labels(root)
            from workbook import access_runtime
            import hashlib
            for name,digest in access_runtime.INSTALLERS.values():
                assert hashlib.sha256((core.ROOT/'dependencies'/name).read_bytes()).hexdigest()==digest
            assert (core.ROOT/'workbook/diagnose_connection.ps1').is_file()
            assert (core.ROOT/'workbook/install_access_runtime.ps1').is_file()
            from workbook.version import APP_VERSION
            assert f'版本 {APP_VERSION}' in labels(root)
            assert root.title()==f'工作簿輸出 {APP_VERSION}'
            assert '列印設定' in labels(root) and '項目列印設定' not in labels(root) and '診所列印簡稱' not in labels(root)
            assert '列印字體設定' in labels(root)
            assert any('同頁生化' in x for x in labels(root)) and any('同頁同病患' in x for x in labels(root))
            assert '每張 A4 固定 20 筆' in labels(root)
            for key,default in [('fixed_20_rows',True),('ditto_bio',True),('ditto_patient',True),('show_region_lines',False),('export_glucose_ac',True)]:
                assert getattr(app,key).get()==settings.get(key,default)
            assert app.glucose_ac_columns.get()==str(settings.get('glucose_ac_columns',5))
            app.fixed_20_rows.set(True);app.export_glucose_ac.set(True)
            app.show_region_lines.set(True);app.merged_order_colors[1].set('#246B45');app.ditto_font_size.set('18');app.ditto_bold.set(True);assert app.save_preferences(False)
            assert core.get_settings()['show_region_lines'] and core.get_settings()['merged_order_colors'][1]=='#246B45' and core.get_settings()['ditto_bold']
            app.show_region_lines.set(False);app.glucose_ac_columns.set('5')
            app.ditto_bio.set(True);app.ditto_patient.set(True);assert app.save_preferences(False)
            assert core.get_settings()['ditto_bio'] and core.get_settings()['ditto_patient']
            app.ditto_bio.set(False);app.ditto_patient.set(False);assert app.save_preferences(False)
            app.font_editor();root.update()
            assert len(app.font_window.inputs)==12
            app.font_window.variables['name'].set('15')
            assert app.font_window.save()
            assert core.get_settings()['font_sizes']['name']==15
            from workbook import print_style
            original_colors=print_style.color_rules(app.settings)
            assert [print_style.choice(v.get()) for v in app.merged_order_colors]==print_style.order_colors(app.settings)
            app.merge_exclusions_enabled.set(False);app.merge_excluded_worknos.set('009, 10, 69, 70, 129, 130')
            assert app.save_preferences(False,scope='print')
            assert core.get_settings()['merge_exclusions_enabled'] is False
            app.merge_exclusions_enabled.set(True);assert app.save_preferences(False,scope='print')
            assert core.get_settings()['merge_excluded_worknos']==['9','10','69','70','129','130']
            assert '列印代碼配色規則' in labels(root)
            app.color_rule_editor();root.update();editor=app.color_rule_window
            assert editor.rules==original_colors
            editor.add();editor.codes.set('人工配色');editor.zone.set(print_style.ALL_ZONES);editor.ink.set('#246B45')
            assert editor.save()
            assert core.get_settings()['print_color_rules'][-1]['codes']==['人工配色']
            app.color_rule_editor();root.update();editor=app.color_rule_window
            editor.refresh(len(editor.rules)-1);editor.delete();assert editor.save()
            assert core.get_settings()['print_color_rules']==original_colors
            database=folder/'synthetic.mdb';database.write_bytes(b'demo-only')
            app.db.set(str(database));app.output_dir.set(str(folder/'output'))
            app.show_headers.set(True);assert app.save_preferences(False)
            assert core.get_settings()['show_column_headers'] is True
            layout['rules'][0]['label']='保存測試';ls.save(layout)
            assert ls.load()['rules'][0]['label']=='保存測試'
            ls.save(app.settings.get('layout') or layout)
            from unittest.mock import patch
            import time
            fixture=core.safe_fixture()
            # Old synthetic demo assets predate the explicit memo field.
            for header in fixture['headers']:header.setdefault('ORDER_NOTE','')
            import copy
            probe=copy.deepcopy(fixture);probe['headers']=probe['headers'][:2]
            worknos={h['LCHK_WORKNO'] for h in probe['headers']}
            probe['details']=[d for d in probe['details'] if d['LCHK_WORKNO'] in worknos]
            second=probe['headers'][1]['LCHK_WORKNO']
            for record in probe['headers']+probe['details']:
                if record['LCHK_WORKNO']==second:record['LCHK_WORKNO']='00009'
            for h in probe['headers']:h.update(LCHK_PATNAME='人工併單排除',CHART_NUMBER='TEST-MERGE')
            merge_settings=dict(app.settings,order_mode='merge')
            assert len(core.make_rows(probe,merge_settings))==2
            merge_settings['merge_exclusions_enabled']=False
            assert len(core.make_rows(probe,merge_settings))==1
            fixture['headers'][0].update(LCHK_INDATE='2026-09-20T09:00:00',LCHK_OPDDATE='2026-09-18T10:00:00')
            with patch('workbook.app.read_access',return_value=fixture), patch('workbook.app.os.startfile') as opener:
                app.connected_path=str(database)
                app.submit()
                assert app.busy and app.submit_button.instate(['disabled'])
                deadline=time.monotonic()+30
                while app.busy and time.monotonic()<deadline:
                    root.update();time.sleep(.01)
            assert not app.busy and app.last_pdf and app.last_pdf.exists(), app.status.get()
            assert len(PdfReader(app.last_pdf).pages)==2 and len(app.rows)==24
            assert app.rows[0]['visit_dates']==['2026-09-18']
            assert app.open_button.instate(['!disabled'])
            assert len(list((folder/'output').glob('*.pdf')))==1 and 'Glucose AC' in PdfReader(app.last_pdf).pages[0].extract_text()
            assert core.load_json(app.last_pdf.with_suffix('.工作進度.json'))['export_summary']['glucose_ac']['records']==24
            from workbook.pdf_fonts import PdfFonts
            latin_family=PdfFonts(app.settings).mono_family
            font_runs=[]
            for page in PdfReader(app.last_pdf).pages:
                page.extract_text(visitor_text=lambda text,cm,tm,font,size:font_runs.append((text,str(font.get('/BaseFont','')) if font else '')))
            assert all(latin_family in font for text,font in font_runs if any(c.isascii() and c.isalnum() for c in text))
            opener.assert_called_once_with(app.last_pdf)
            assert (core.ROOT/'workbook/access_bridge.ps1').is_file()
            from workbook import catalog_settings
            lookup=copy.deepcopy(core.safe_fixture())
            lookup.setdefault('sets',[]).append(dict(LCS_ID='LOOKUP',LCS_NAME='人工套組查找',LCS_UNIKEY='LOOKUP-ID'))
            lookup.setdefault('set_members',[]).extend([dict(LCS_UNIKEY='LOOKUP-ID',LCS_ITEM='0921',LCS_SERIAL=1),dict(LCS_UNIKEY='LOOKUP-ID',LCS_ITEM='UNKNOWN',LCS_SERIAL=2)])
            win=catalog_settings.editor(root,lookup,app.settings);win.withdraw();root.update()
            assert len(win.catalog_tabs.tabs())==3
            table=win.catalog_pages['items'].table
            assert len(table.filters)==12 and 'updated_display' in table.filters
            assert 'tree' in str(table.tree.cget('show')) and 'headings' not in str(table.tree.cget('show'))
            assert all(hasattr(app,name) for name in ('catalog_import_button','catalog_export_button','catalog_update_button'))
            assert '套組、單項、診所設定' in labels(root)
            edit_page=win.catalog_pages['items'];original_labels={}
            for key in ('0921','096'):
                index=next(i for i,r in enumerate(table.rows) if r['key']==key)
                table.tree.selection_set(str(index));root.update()
                original_labels[key]=edit_page.label.get();edit_page.label.set('人工批次'+key)
                assert table.tree.item(str(index),'tags')==('dirty',)
            assert len(win.batch.drafts.changes)==2
            with patch('workbook.catalog_batch.confirm_changes',return_value=False):assert not win.batch.save()
            assert len(win.batch.drafts.changes)==2
            for key,label in original_labels.items():
                index=next(i for i,r in enumerate(table.rows) if r['key']==key)
                table.tree.selection_set(str(index));root.update();edit_page.label.set(label)
            assert not win.batch.drafts.changes
            assert {r['kind'] for r in table.rows}<={'單項','套組','套組子項'}
            assert not any(r['key'].startswith('PRINT:') for r in table.rows)
            table.filters['kind'].set('單項');table.filters['zone'].set('e411');root.update()
            assert table.tree.get_children()
            table.sort('code');assert table.column=='code' and not table.descending
            table.sort('code');assert table.descending
            table.clear_filters();table.query.set('LOOKUP');root.update()
            table.tree.selection_set(table.tree.get_children()[0]);root.update()
            page=win.catalog_pages['items'];page.members_button.invoke();root.update()
            parent_id=table.tree.selection()[0]
            assert len(table.tree.get_children(parent_id))==2
            assert table.tree.item(parent_id,'open')
            assert list(page.panel_print_box['values'])==['是','否']
            child_id=table.tree.get_children(parent_id)[0]
            table.tree.selection_set(child_id);root.update()
            assert page.selected['kind']=='套組子項'
            prior_child=page.print_enabled.get();page.print_enabled.set(not prior_child);root.update()
            _,child_layout=win.batch.drafts.prepare(app.settings,ls.load())
            assert child_layout['panel_children']['G:LOOKUP'][page.selected['code']]==(not prior_child)
            assert table.tree.item(child_id,'tags')==('dirty',)
            win.batch.drafts.changes.clear()
            win.destroy()
            assert '子區域與自動起始區' in labels(root)
            win=catalog_settings.editor(root,core.safe_fixture(),app.settings,initial='subregions');win.withdraw();root.update()
            assert win.catalog_tabs.index('current')==2
            sub=win.catalog_pages['subregions'];original_start=sub.auto_start.get()
            assert list(sub.auto_start_box['values'])==list('ABCDEF')
            sub.auto_start.set('C')
            with patch('workbook.catalog_batch.confirm_changes',return_value=True):sub.save_auto_start()
            root.update()
            assert ls.load()['bio_auto_start']=='C'
            win.destroy()
            win=catalog_settings.editor(root,core.safe_fixture(),app.settings,initial='subregions');win.withdraw();root.update()
            sub=win.catalog_pages['subregions'];assert sub.auto_start.get()=='C'
            sub.auto_start.set(original_start)
            with patch('workbook.catalog_batch.confirm_changes',return_value=True):sub.save_auto_start()
            win.destroy()
            assert (core.ROOT/'workbook/catalog_bridge.ps1').is_file()
            assert len(core.load_json(app.last_pdf.with_suffix('.工作進度.json'))['rows'])==24
            app.fixed_20_rows.set(False)
            with patch('workbook.app.read_access',return_value=fixture),patch('workbook.app.os.startfile'),patch('workbook.app.messagebox.askyesno',return_value=True):
                app.submit();deadline=time.monotonic()+30
                while app.busy and time.monotonic()<deadline:root.update();time.sleep(.01)
            assert not app.busy and app.last_pdf
            adaptive_summary=core.load_json(app.last_pdf.with_suffix('.工作進度.json'))['export_summary']
            assert adaptive_summary['fixed_20_rows'] is False and adaptive_summary['rows_per_page'] is None
            # Unabbreviated CBC members now spill horizontally after three rows;
            # this artificial dense row may correctly ask for force confirmation.
            assert sum(adaptive_summary['page_counts'])==24
            assert all(entry['workno']=='00012' for entry in adaptive_summary['forced_adjustments'])
            app.fixed_20_rows.set(True)
            merged_fixture=core.safe_fixture()
            for h in merged_fixture['headers'][:2]:h.update(LCHK_PATNAME='人工併單範例',CHART_NUMBER='TEST-MERGE')
            app.order_mode.set('merge')
            with patch('workbook.app.read_access',return_value=merged_fixture),patch('workbook.app.os.startfile'),patch('workbook.app.messagebox.askyesno',return_value=True):
                app.submit();deadline=time.monotonic()+30
                while app.busy and time.monotonic()<deadline:root.update();time.sleep(.01)
            assert not app.busy and len(app.rows)==23 and app.rows[0]['merged_count']==2,app.status.get()
            assert core.load_json(app_module.PREFERENCES)['order_mode']=='merge'
            assert 'order_mode' not in core.get_settings()
            assert len(core.load_json(app.last_pdf.with_suffix('.工作進度.json'))['data']['headers'])==24
            app.order_mode.set('merge_first')
            with patch('workbook.app.read_access',return_value=merged_fixture),patch('workbook.app.os.startfile'),patch('workbook.app.messagebox.askyesno',return_value=True):
                app.submit();deadline=time.monotonic()+30
                while app.busy and time.monotonic()<deadline:root.update();time.sleep(.01)
            assert not app.busy and len(app.rows)==23 and app.rows[0]['workno_display']=='1'
            assert 'workno_lines' not in app.rows[0] and len(app.rows[0]['source_orders'])==2
            assert core.load_json(app_module.PREFERENCES)['merge_workno_style']=='first'
            forced_rows=core.make_rows(fixture,dict(app.settings,order_mode='split'))
            forced_rows[6].update(e411='VeryLongMachineLabel0123456789',source_items=[dict(code='FORCE',type='I',label='VeryLongMachineLabel0123456789',name='',namec='')],verified_panels=[])
            app.settings['rules']['FORCE']={'group':'e411','label':'VeryLongMachineLabel0123456789'}
            with patch('workbook.app.read_access',return_value=fixture) as reader,patch('workbook.app.make_rows',return_value=forced_rows),patch('workbook.app.messagebox.askyesno',return_value=True) as confirm,patch('workbook.app.os.startfile'):
                app.submit();deadline=time.monotonic()+30
                while app.busy and time.monotonic()<deadline:root.update();time.sleep(.01)
            assert not app.busy and app.last_pdf and '強制輸出' in app.last_pdf.name,app.status.get()
            assert reader.call_count==confirm.call_count==1
            forced_summary=core.load_json(app.last_pdf.with_suffix('.工作進度.json'))['export_summary']
            assert forced_summary['forced_export'] and forced_summary['pages']==2 and forced_summary['workbook_pages']==2
            assert forced_summary['forced_adjustments'][0]['workno']=='00007'
            assert str(app.status_label['foreground'])=='#b42318'
            assert not core.get_settings().get('force_export')
            with patch('workbook.app.read_catalog',return_value=fixture) as dictionary_reader:
                app.catalog_editor('items');deadline=time.monotonic()+30
                while app.catalog_loading and time.monotonic()<deadline:root.update();time.sleep(.01)
                assert not app.catalog_loading and app.catalog_document['counts']['items']>0
                app.catalog_window.destroy()
                app.catalog_editor('clinics');deadline=time.monotonic()+30
                while app.catalog_loading and time.monotonic()<deadline:root.update();time.sleep(.01)
                assert dictionary_reader.call_count==1
                app.catalog_window.destroy()
            summary={'ok':True,'frozen':bool(getattr(sys,'frozen',False)),'app_version':APP_VERSION,
                     'gui':True,'settings_persist':True,'portable_preferences':True,'preferences_auto_created':True,'red_visit_date':True,'layout_editor':True,
                     'session_roundtrip':True,'sample_records':24,'pdf_pages':2,'workbook_pages':2,'merge_mode':True,'merged_rows':23,'merge_first_mode':True,
                     'force_confirmation':True,'force_single_read':True,'force_same_pages':True,'force_warning':True,
                     'catalog_json_reused':True,'catalog_single_read':True,'column_font_settings':True,'unified_catalog_filters_sort':True,'default_merge_first':True,
                     'runtime_installers_verified':True,'connection_repair_controls':True,'database_only_catalog':True,'ditto_controls_persist':True,
                     'new_defaults_checked':True,'adaptive_export':True,'unified_print_settings_button':True,
                     'glucose_sheet_export':True,'glucose_in_header':True,'merged_color_control':True,'ditto_font_bold_control':True,'region_and_sheet_preferences':True,
                     'separate_system_print_settings':True,'upgrade_preserves_user_settings':True,'seed_system_settings':True,'three_primary_pages':True,
                     'six_print_categories':True,'panel_member_lookup':True,'native_mode_tiles':True,'ranked_positions':True,'collapsible_sidebar':True,'print_accordion':True,
                     'bottom_system_gear':True,'print_category_order':[b.cget('text') for b in app.print_scroll.buttons],
                     'batch_catalog_edits':True,'single_filter_header':True,'external_json_controls':True,
                     'pdf_monospace':True,'latin_font':latin_family,'print_color_rule_editor':True,'print_color_rules_persist':True,
                     'merge_exclusions_toggle':True,'per_order_color_controls':True,'bio_auto_start_persists':True,'bio_subregions_a_to_f':True}
        finally:root.destroy()
    Path(destination).write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--update-smoke':
        import json,tkinter as tk
        from workbook.version import APP_VERSION
        from workbook import app,pdf_document,catalog_settings
        from reportlab.pdfgen import canvas
        root=tk.Tk();root.withdraw();root.update();root.destroy()
        Path(sys.argv[2]).write_text(json.dumps({'ok':True,'version':APP_VERSION}),encoding='utf-8')
    elif len(sys.argv)==3 and sys.argv[1]=='--self-test':
        try:self_test(sys.argv[2])
        except Exception as error:
            import json
            Path(sys.argv[2]).write_text(json.dumps({'ok':False,'error':type(error).__name__,
                'message':str(error)},ensure_ascii=False),encoding='utf-8')
            sys.exit(1)
    else:
        from workbook.paths import ROOT
        from workbook import update_install as installation,updates
        if (ROOT/installation.LOCK).exists():
            import json,tkinter as tk
            from tkinter import messagebox
            try:active=installation.process_running(json.loads((ROOT/installation.LOCK).read_text(encoding='utf-8'))['pid'])
            except Exception:active=True
            if active:
                root=tk.Tk();root.withdraw();messagebox.showinfo('更新中','更新工具正在處理，請等候完成後自動重啟。');root.destroy();sys.exit(0)
        if (ROOT/installation.JOURNAL).exists():
            import os
            updates.launch(ROOT,os.getpid(),recover=True)
            sys.exit(0)
        from workbook.app import main
        main()
