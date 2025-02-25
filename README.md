# MP3 轉文字工具

這是一個基於 Flask 和 React 的 Web 應用程序，用於將 MP3 和其他音頻文件轉換為文字。

## 功能特點

- 支援多種音頻格式（MP3、WAV、M4A、OGG、FLAC）
- 批量上傳和處理
- 支援多語言識別
- 直觀的用戶界面

## 安裝說明

### 系統要求
- 儲存路徑需求：建議安裝在 **E:\CascadeProjects** 目錄下以確保最佳相容性
- 磁碟空間：至少 2GB 可用空間（用於音頻處理和臨時文件）

### 後端設置
1. 克隆倉庫到指定路徑：
```bash
git clone https://github.com/your-repo/rsg_mp3_to_text.git E:\CascadeProjects\rsg_mp3_to_text
```

2. 進入專案目錄：
```powershell
cd E:\CascadeProjects\rsg_mp3_to_text
```

3. 安裝 Python 依賴：
```bash
pip install -r requirements.txt
```

### 文件儲存位置
- 上傳音頻存放路徑：`E:\CascadeProjects\rsg_mp3_to_text\uploads`
- 轉寫結果存放路徑：`E:\CascadeProjects\rsg_mp3_to_text\transcripts`
- 日誌文件路徑：`E:\CascadeProjects\rsg_mp3_to_text\app.log`

### 自定義路徑設定
如需修改默認路徑，請編輯 `.env` 文件：
```ini
# 上傳目錄（絕對路徑）
UPLOAD_FOLDER=E:/CascadeProjects/rsg_mp3_to_text/uploads
# 轉寫結果目錄
TRANSCRIPTS_FOLDER=E:/CascadeProjects/rsg_mp3_to_text/transcripts
```

> **注意事項**  
> 請勿將專案放置在包含中文或特殊字符的路徑中，例如：  
> ❌ `E:\我的專案\`  
> ✅ `E:\CascadeProjects\`

## 使用方法

1. 打開應用程序
2. 點擊「選擇音頻檔案」按鈕
3. 選擇一個或多個音頻文件
4. 等待處理完成
5. 查看轉錄結果

## 系統要求

- Python 3.8 或更高版本
- 網絡瀏覽器（建議使用 Chrome 或 Firefox 最新版本）
- 至少 4GB RAM（用於音頻處理）
