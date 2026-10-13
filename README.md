# 工作簿輸出

Windows 64 位元桌面程式。唯讀擷取本機 Access 檢驗資料，依可調整的區域、簡稱、套組與流水號規則產生 A4 工作簿 PDF。

## 安裝及更新

1. 在 [Releases](https://github.com/RenHuang-Huang/lab-workbook/releases) 下載 `lab-workbook-年月日-v版號-windows-x64.zip`，完整解壓縮至可寫入的資料夾。不要只複製 EXE。
2. 雙擊 `工作簿輸出.exe`。第一次使用請在系統設定選擇 Access 資料庫及輸出位置，按「測試連線」。
3. 若已有舊版，關閉舊程式後將新版完整覆蓋到原程式資料夾，或在系統設定按「匯入設定」並選取舊版程式資料夾。**不要刪除原資料夾或其設定。**
4. 後續更新：系統設定 →「檢查並更新程式」。有正式新版時會列出版本和下載大小，確認後儲存設定、關閉主程式，交由獨立工具下載、驗證、替換及重新啟動。
5. 更新工具在安裝資料夾的 `.update-backups/` 保留程式備份；下載或替換失敗會提示，已開始替換的更新會嘗試還原。若斷電或工具被強制終止，下次啟動會嘗試復原，也可手動執行 `修復未完成更新.cmd`。請不要刪除未完成更新的備份。

更新需要網路、安裝資料夾寫入權限及足夠備份空間；請先關閉同資料夾的其他工作簿視窗。程式及更新工具尚未購買程式碼簽章憑證，Windows 或現場防毒軟體可能要求確認。

## 本機設定與資料

- `preferences.json`：系統設定，包含資料庫位置、輸出位置與拆併單偏好。
- `print_settings/`：列印版面、字級、項目／診所簡稱、流水號及本機字典快取。
- `config_backups/`：設定變更及匯入時的備份。
- PDF 與工作進度檔留在使用者選定的本機輸出資料夾。

**GitHub 原始碼與公開安裝包不包含 Access 資料庫、病患紀錄、診所字典或使用者儲存過的設定。**首次啟動由程式內建預設值建立本機設定，現場規則須匯入或設定並核對。更新包不覆蓋既有設定、資料庫及輸出檔案。每日資料處理不呼叫雲端服務；更新功能只讀取固定 GitHub 倉庫的公開版本資訊及安裝包，不上傳檢驗資料。

缺少 Access 元件時，在系統設定的連線工具依指示安裝。安裝包附 Microsoft 官方 x86／x64 Access Runtime **線上安裝程式**，需要網路；程式會先核對雜湊及 Microsoft 簽章，保留官方安裝流程。Office 位元及既有安裝方式須相容。

## 開發

Python 3.12、Windows、Tkinter。安裝 `workbook/requirements.txt`，在專案根目錄執行：

```powershell
python -m workbook.app
python -m unittest workbook.test_updates workbook.test_config_store
```

應用程式可從乾淨原始碼啟動並建立本機設定；讀取 Access 需要相容的 ACE provider。公開測試使用人工資料；部分歷史測試依賴本機參考資料，這些資料不隨倉庫提供。

## 發行

1. 在 `workbook/version.py` 設定固定版本，格式 `YYYYMMDD-vN`。
2. 安裝 PyInstaller。先執行 `python scripts/fetch_runtime_installers.py` 取得並校驗 Microsoft 線上安裝檔，再執行 `python scripts/build_desktop.py --public`。
3. 測試產出的 EXE、獨立更新工具、設定保留及回復流程，並執行 `python scripts/audit_public.py`。
4. 推送經審查的原始碼；以同版號建立 GitHub Release，上傳 `lab-workbook-版號-windows-x64.zip`。必須先完成所有附件再發布 Release；自動更新只接受正式版本及 GitHub 提供的 SHA256。

`--settings-from` 只供本機延續設定的私用包，檔名標記 `LOCAL_ONLY`，不得上傳 GitHub。公開模式拒絕本機字典參數。不要提交 `output/`、`tmp/`、設定 JSON、分析資料、照片、檢驗單或資料庫。

更新保護包含：固定倉庫與檔名、TLS、GitHub SHA256、解壓縮容量限制、路徑／連結檢查、檔案清單校驗、保護本機設定、程式備份、更新日誌及安裝前後啟動檢查。雜湊用於偵測內容損壞；發行來源的信任仍依賴 GitHub 帳號及倉庫權限，維護者應啟用兩步驟驗證。
