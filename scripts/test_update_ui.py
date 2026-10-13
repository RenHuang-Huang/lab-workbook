"""Synthetic GUI acceptance: background query, cancellation and updater handoff."""
import sys
import tempfile
import time
from pathlib import Path
import tkinter as tk
from unittest.mock import patch, Mock
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from workbook import app as am,core,layout_settings as ls,catalog_cache as cc,config_store as cs,updates
from workbook.version import APP_VERSION


def main():
    with tempfile.TemporaryDirectory() as d:
        directory=Path(d);cs.ensure_configuration(directory)
        with patch.multiple(am,ROOT=directory,PREFERENCES=directory/'preferences.json'),patch.object(core,'CONFIG',directory/'print_settings/settings.json'),patch.object(ls,'PATH',directory/'print_settings/layout_settings.json'),patch.object(cc,'PATH',directory/'print_settings/catalog.json'):
            root=tk.Tk();root.withdraw();app=am.App(root,auto_connect=False);root.update()
            assert app.update_button.cget('text')=='檢查並更新程式'
            with patch.object(updates,'latest',return_value=dict(version=APP_VERSION)):
                app.check_updates();deadline=time.monotonic()+3
                while app.update_checking and time.monotonic()<deadline:root.update();time.sleep(.02)
                assert not app.update_checking and '已是最新' in app.update_status.get()
            app.update_complete((dict(version=APP_VERSION),None))
            assert '已是最新' in app.update_status.get()
            with patch.object(am.messagebox,'showerror') as warning:
                app.update_complete((None,'測試網路中斷'))
                assert warning.call_count==1
            future=dict(version='20261013-v99',size=123,url='synthetic',sha256='0'*64)
            with patch.object(sys,'frozen',True,create=True),patch.object(am.messagebox,'askyesno',return_value=False),patch.object(updates,'launch') as launcher:
                app.update_complete((future,None));launcher.assert_not_called()
            with patch.object(sys,'frozen',True,create=True),patch.object(am.messagebox,'askyesno',return_value=True),patch.object(app,'save_preferences',return_value=False),patch.object(updates,'launch') as launcher:
                app.update_complete((future,None));launcher.assert_not_called()
            with patch.object(sys,'frozen',True,create=True),patch.object(am.messagebox,'askyesno',return_value=True),patch.object(app,'save_preferences',return_value=True),patch.object(updates,'launch',side_effect=updates.UpdateError('test')) as launcher,patch.object(am.messagebox,'showerror') as warning:
                app.update_complete((future,None));assert launcher.call_count==1 and warning.call_count==1
            with patch.object(sys,'frozen',True,create=True),patch.object(am.messagebox,'askyesno',return_value=True),patch.object(app,'save_preferences',return_value=True),patch.object(updates,'launch',return_value=Mock(poll=lambda:None)) as launcher,patch.object(root,'after') as after:
                app.update_complete((future,None));assert launcher.call_count==1
                assert any(call.args[0]==700 for call in after.call_args_list)
            process=Mock(poll=lambda:None,workbook_folder=directory)
            app.update_handoff_deadline=time.monotonic()+20
            with patch.object(root,'after') as scheduled:
                app.finish_update_handoff(process);assert scheduled.call_count==1
                assert not (directory/'go').exists()
            (directory/'ready').touch()
            with patch.object(root,'destroy') as destroy:
                app.finish_update_handoff(process);assert destroy.call_count==1 and (directory/'go').exists()
            root.destroy()
    print('UPDATE GUI PASSED: version, errors, cancel, save guard, launch failure, background handoff.')


if __name__=='__main__':main()
