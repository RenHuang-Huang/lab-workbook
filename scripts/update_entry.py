"""Independent, self-contained updater. No database/configuration reads."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from workbook import updates as u, update_install as ins


def main(ticket_path):
    ticket_path = Path(ticket_path).resolve()
    ticket = json.loads(ticket_path.read_text(encoding='utf-8'))
    folder = ticket_path.parent
    destination = Path(ticket['root']).resolve()
    root = tk.Tk(); root.title('工作簿更新工具'); root.geometry('520x235'); root.resizable(False, False)
    status = tk.StringVar(value='準備更新…')
    ttk.Label(root, text='工作簿更新', font=('Microsoft JhengHei UI', 18, 'bold')).pack(anchor='w', padx=24, pady=(20,10))
    label = ttk.Label(root, textvariable=status, wraplength=465, font=('Microsoft JhengHei UI', 11))
    label.pack(fill='x', padx=24, pady=8)
    bar = ttk.Progressbar(root, mode='indeterminate'); bar.pack(fill='x', padx=24, pady=10); bar.start()
    actions = ttk.Frame(root); actions.pack(fill='x', padx=24, pady=8)
    events = queue.SimpleQueue(); running = [True]
    (folder / 'ready').touch()
    root.protocol('WM_DELETE_WINDOW', lambda: messagebox.showinfo('更新中', '請等候更新完成；程式與設定會受到保護。', parent=root) if running[0] else root.destroy())
    def start_app():
        if (destination / ins.JOURNAL).exists():
            messagebox.showerror('需要復原', '請先執行程式資料夾的「修復未完成更新.cmd」。', parent=root); return
        try:
            subprocess.Popen([str(destination / u.EXE)], cwd=destination, close_fds=True)
            root.destroy()
        except OSError:
            messagebox.showerror('無法重啟', '請確認程式未被防毒軟體隔離，或手動開啟工作簿。', parent=root)
    def run():
        locked = False
        try:
            deadline=time.monotonic()+30
            while not (folder/'go').exists():
                if (folder/'cancel').exists() or time.monotonic()>deadline:
                    raise u.UpdateError('主程式未交接更新，未修改任何檔案。')
                time.sleep(.1)
            if not (destination / u.EXE).is_file():
                raise u.UpdateError('找不到原工作簿程式，未更新。')
            lock = destination / ins.LOCK
            if lock.exists():
                owner = json.loads(lock.read_text(encoding='utf-8')).get('pid', 0)
                if owner and ins.process_running(owner):
                    raise u.UpdateError('另一個更新工具正在執行。')
                lock.unlink()
            with lock.open('x', encoding='utf-8') as stream:
                json.dump({'pid': os.getpid()}, stream)
            locked = True
            progress = lambda value: events.put(('progress', value))
            if ticket.get('recover'):
                ins.wait_closed(destination, ticket.get('parent_pid', 0), progress)
                if (destination / ins.JOURNAL).exists():
                    progress('正在還原上次未完成的更新…'); ins.rollback(destination)
            else:
                chosen = ticket['release']
                # Fetch fresh metadata from the fixed repository, never trust a local download ticket alone.
                release = u.latest()
                if release != chosen:
                    raise u.UpdateError('Release 已變更，請重新開啟工作簿並檢查更新。')
                archive = folder / 'download.zip'
                u.download(release, archive, progress)
                progress('校驗與解壓縮程式…')
                stage = folder / 'stage'
                names = ins.unpack(archive, stage, release['version'])
                progress('檢查新版啟動元件…')
                ins.smoke(stage, folder / 'stage-check.json', release['version'])
                ins.wait_closed(destination, ticket['parent_pid'], progress)
                ins.install(stage, destination, names, release['version'], progress)
                try:
                    ins.smoke(destination, folder / 'installed-check.json', release['version'])
                except Exception:
                    ins.rollback(destination)
                    raise
                (destination / ins.JOURNAL).unlink()
            events.put(('done', '更新完成，正在重新啟動工作簿。'))
        except Exception as error:
            detail = str(error) if isinstance(error, u.UpdateError) else '下載、解壓縮或檔案替換失敗，請確認網路、寫入權限及防毒軟體。'
            (folder / 'error.json').write_text(json.dumps({'type': type(error).__name__, 'code': getattr(error, 'winerror', None)}), encoding='utf-8')
            events.put(('error', detail))
        finally:
            if locked:
                (destination / ins.LOCK).unlink(missing_ok=True)
    def poll():
        try:
            while True:
                kind, text = events.get_nowait(); status.set(text)
                if kind in ('done', 'error'):
                    running[0] = False; bar.stop(); bar.pack_forget()
                    if kind == 'done': root.after(400, start_app)
                    else:
                        label.configure(foreground='#b42318')
                        ttk.Button(actions, text='重新開啟工作簿', command=start_app).pack(side='left')
                        ttk.Button(actions, text='關閉', command=root.destroy).pack(side='right')
        except queue.Empty:
            pass
        root.after(80, poll)
    threading.Thread(target=run, daemon=False).start(); poll(); root.mainloop()


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--recover':
        from workbook.updates import launch
        launch(Path(sys.argv[2]), 0, recover=True)
    elif len(sys.argv) == 2:
        main(sys.argv[1])
