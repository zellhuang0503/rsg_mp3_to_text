# 在導入任何模組之前設置環境變量
import os
import sys
import re
import time
import datetime
import logging
import traceback
from pathlib import Path
from urllib.parse import unquote

# 設置日誌記錄
logging.basicConfig(level=logging.DEBUG,
                   format='%(asctime)s [%(levelname)s] %(message)s',
                   handlers=[logging.FileHandler('app.log', encoding='utf-8'),
                           logging.StreamHandler()])
logger = logging.getLogger(__name__)

# 設置環境變量
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUTF8'] = '1'
os.environ['LANG'] = 'zh_TW.UTF-8'
os.environ['LC_ALL'] = 'zh_TW.UTF-8'

# 設置常量
UPLOAD_FOLDER = 'uploads'
TRANSCRIPTS_FOLDER = 'transcripts'
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'm4a', 'ogg', 'flac'}
MAX_CONTENT_LENGTH = 25 * 1024 * 1024  # 25MB

import json
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import whisper
from pydub import AudioSegment

# 強制使用 UTF-8 編碼
# os.environ['PYTHONIOENCODING'] = 'utf-8'
# os.environ['PYTHONUTF8'] = '1'
# os.environ['PYTHONLEGACYWINDOWSFSENCODING'] = 'utf-8'
# os.environ['LANG'] = 'zh_TW.UTF-8'
# os.environ['LC_ALL'] = 'zh_TW.UTF-8'

# 設置日誌
# logging.basicConfig(
#     level=logging.DEBUG,
#     format='%(asctime)s [%(levelname)s] %(message)s',
#     handlers=[
#         logging.StreamHandler(),
#         logging.FileHandler('app.log', encoding='utf-8')
#     ]
# )
# logger = logging.getLogger(__name__)

# 打印系統環境信息
logger.info("=== 系統環境信息 ===")
logger.info(f"Python 版本: {sys.version}")
logger.info(f"系統平台: {sys.platform}")
logger.info(f"文件系統編碼: {sys.getfilesystemencoding()}")
logger.info(f"默認編碼: {sys.getdefaultencoding()}")
logger.info(f"環境變量:")
logger.info(f"- PYTHONIOENCODING: {os.environ.get('PYTHONIOENCODING')}")
logger.info(f"- PYTHONUTF8: {os.environ.get('PYTHONUTF8')}")
logger.info(f"- LANG: {os.environ.get('LANG')}")
logger.info(f"- LC_ALL: {os.environ.get('LC_ALL')}")

app = Flask(__name__)
# 配置 CORS
CORS(app, resources={
    r"/api/*": {
        "origins": ["http://localhost:5500"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "expose_headers": ["Content-Range", "X-Content-Range"],
        "supports_credentials": True
    }
})

# 初始化 whisper 模型
try:
    model = whisper.load_model("base")
    print("Whisper 模型載入成功")
except Exception as e:
    print(f"Whisper 模型載入失敗: {str(e)}")
    model = None

print(f"應用程序啟動")
print(f"當前工作目錄: {os.getcwd()}")
print(f"上傳目錄設置為: {UPLOAD_FOLDER}")
print(f"Python 版本: {sys.version}")
print(f"已安裝的套件:")
for name, module in list(sys.modules.items()):
    try:
        if hasattr(module, '__version__'):
            print(f"- {name}: {module.__version__}")
    except:
        continue

# 確保上傳目錄存在
Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)

def debug_string(s, prefix=""):
    """調試字符串的編碼和內容"""
    try:
        info = {
            'value': s,
            'type': type(s).__name__,
            'length': len(s),
            'bytes_repr': repr(s.encode('utf-8')),
            'is_ascii': all(ord(c) < 128 for c in s),
            'contains_chinese': bool(re.search(r'[\u4e00-\u9fff]', s)),
            'url_encoded': quote(s),
            'url_decoded': unquote(s)
        }
        
        logger.debug(f"{prefix} 字符串分析:")
        for key, value in info.items():
            logger.debug(f"{prefix} - {key}: {value}")
        
        return info
    except Exception as e:
        logger.error(f"{prefix} 分析字符串時出錯: {str(e)}")
        return None

def safe_filename(filename, original_filename=None):
    """強化版文件名安全處理"""
    try:
        # 優先使用原始文件名
        if original_filename:
            filename = original_filename
            
        # 多層次清理
        filename = str(filename).strip()
        filename = os.path.basename(filename)  # 去除路徑
        filename = re.sub(r'[\\/*?:"<>|]', '_', filename)  # 替換特殊符號
        filename = filename.replace('\n', '_').replace('\r', '_')  # 處理控制字符
        filename = filename.strip('. ')  # 避免隱藏文件
        filename = filename[:200]  # 限制長度
        
        # 確保副檔名有效
        name, ext = os.path.splitext(filename)
        ext = ext.split('?')[0]  # 去除URL參數
        ext = ext[:10]  # 限制副檔名長度
        filename = f"{name}{ext}"
        
        # 最終後備機制
        if not filename:
            filename = f"unnamed_{int(time.time())}"
            
        return filename
    except Exception as e:
        logger.error(f"文件名處理失敗: {str(e)}")
        return f"error_{int(time.time())}"

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def format_timestamp(seconds):
    """將秒數轉換為時間戳格式"""
    minutes = int(seconds // 60)
    seconds = int(seconds % 60)
    return f"{minutes:02d}:{seconds:02d}"

def detect_speakers(segments):
    """根據時間間隔檢測不同的說話者"""
    current_speaker = 1
    last_end_time = 0
    formatted_segments = []
    
    for segment in segments:
        # 檢查是否需要切換說話者
        if last_end_time > 0 and (segment['start'] - last_end_time) > 2.0:
            current_speaker += 1
        
        # 處理文字
        text = segment['text']
        formatted_text = (
            f"[說話者 {current_speaker}] "
            f"({format_timestamp(segment['start'])} - {format_timestamp(segment['end'])}) "
            f"{text}"
        )
        
        formatted_segments.append(formatted_text)
        last_end_time = segment['end']
    
    return formatted_segments

def save_transcript_to_markdown(transcript_data, original_filename):
    """將轉錄結果保存為 Markdown 文件 (強化版)"""
    try:
        logger.info("=== 開始保存 Markdown 文件 ===")
        
        # 確保原始文件名有效性
        if not original_filename or not isinstance(original_filename, str):
            logger.warning("原始文件名無效，使用預設文件名")
            original_filename = "unnamed_audio_" + datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        
        # 生成安全文件名
        cleaned_name = safe_filename(original_filename)
        base_name = os.path.splitext(cleaned_name)[0]
        md_filename = f"{base_name}.md"
        md_path = Path(TRANSCRIPTS_FOLDER) / md_filename
        
        logger.info(f"最終文件路徑: {md_path}")
        logger.debug(f"路徑組成檢查: {TRANSCRIPTS_FOLDER} + {md_filename}")

        # 驗證並創建目錄
        try:
            Path(TRANSCRIPTS_FOLDER).mkdir(parents=True, exist_ok=True)
            logger.info("目錄驗證成功")
            
            # 測試目錄可寫性
            test_file = Path(TRANSCRIPTS_FOLDER) / "write_test.tmp"
            test_file.touch()
            test_file.unlink()
        except Exception as e:
            logger.critical(f"目錄權限異常: {str(e)}")
            raise PermissionError(f"無法寫入目錄: {TRANSCRIPTS_FOLDER}")

        # 生成文件內容
        md_content = f"# 音頻轉錄結果：{cleaned_name}\n\n"
        md_content += f"轉錄時間：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        md_content += "## 內容\n\n"
        
        # 處理轉錄內容
        segments = transcript_data['segments']
        if isinstance(segments, list):
            if segments and isinstance(segments[0], str):
                # 已經處理過的文本列表
                for segment in segments:
                    md_content += f"{segment}\n\n"
            else:
                # 原始的轉錄片段
                for segment in segments:
                    text = segment['text'].strip()
                    text = text.replace('\n', ' ')  # 移除內部換行
                    text = re.sub(r'\s+', ' ', text)  # 合併多餘空格
                    
                    time_range = (
                        f"{format_timestamp(segment['start'])}"
                        f" - {format_timestamp(segment['end'])}"
                    )
                    md_content += f"### {time_range}\n{text}\n\n"

        # 二階段寫入機制
        try:
            # 先寫入臨時文件
            temp_path = md_path.with_suffix('.tmp')
            with open(temp_path, 'w', encoding='utf-8', errors='replace') as f:
                f.write(md_content)
            
            # 原子操作替換文件
            if md_path.exists():
                md_path.unlink()
            temp_path.rename(md_path)
            
            # 驗證文件完整性
            if md_path.exists():
                try:
                    with open(md_path, 'r', encoding='utf-8') as f:
                        f.read(1024)
                    logger.info("文件完整性驗證通過")
                except Exception as e:
                    logger.error("文件驗證失敗，可能已損壞")
                    md_path.unlink(missing_ok=True)
                    return None
                    
            logger.info(f"文件保存成功，大小: {md_path.stat().st_size} bytes")
            return md_filename
            
        except OSError as e:
            logger.error(f"文件系統錯誤: {str(e)}")
            if e.errno == 28:
                raise Exception("磁碟空間不足")
            raise
        except UnicodeEncodeError as e:
            logger.error("編碼異常，使用錯誤替代處理")
            with open(md_path, 'w', encoding='utf-8', errors='replace') as f:
                f.write(md_content)
            return md_filename
            
    except Exception as e:
        logger.error(f"保存過程嚴重異常: {str(e)}")
        logger.error(f"異常類型: {type(e)}")
        logger.error(f"堆棧追蹤: {traceback.format_exc()}")
        return None

@app.route('/api/upload', methods=['POST'])
def upload_file():
    try:
        logger.info("=== 開始處理文件上傳請求 ===")
        logger.info(f"請求頭: {dict(request.headers)}")
        
        if 'file' not in request.files:
            logger.error("錯誤：請求中沒有文件")
            return jsonify({'error': '沒有檔案'}), 400
        
        file = request.files['file']
        original_filename = request.form.get('originalFilename')
        
        logger.info("=== 文件信息 ===")
        logger.info(f"Content-Type: {request.content_type}")
        logger.info(f"表單數據: {dict(request.form)}")
        logger.info(f"文件對象: {file}")
        logger.info(f"文件名: {file.filename}")
        debug_string(file.filename, "上傳的文件名")
        
        if original_filename:
            debug_string(original_filename, "原始文件名")
        
        if file.filename == '':
            logger.error("錯誤：沒有選擇文件")
            return jsonify({'error': '沒有選擇檔案'}), 400
        
        if file and allowed_file(file.filename):
            # 記錄文件名信息
            logger.info(f"文件名信息：")
            logger.info(f"- 上傳的檔名：{file.filename}")
            logger.info(f"- 原始檔名：{original_filename}")
            
            try:
                # 處理文件名
                filename = safe_filename(file.filename, original_filename)
                filepath = Path(UPLOAD_FOLDER) / filename
                
                logger.info(f"處理後檔名：{filename}")
                logger.info(f"完整路徑：{filepath}")
                
                # 確保上傳目錄存在
                Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
                
                # 如果文件已存在，先刪除
                if filepath.exists():
                    logger.info(f"刪除已存在的文件: {filepath}")
                    filepath.unlink()
                
                # 保存文件
                try:
                    # 對於音頻文件，使用二進制模式
                    file_content = file.read()
                    with open(str(filepath), 'wb') as f:
                        f.write(file_content)
                    logger.info(f"文件保存成功: {filepath}")
                    
                    # 驗證文件是否成功保存
                    if filepath.exists():
                        file_size = filepath.stat().st_size
                        logger.info(f"文件大小：{file_size} bytes")
                        
                        # 嘗試讀取文件開頭，確保可以訪問
                        with open(str(filepath), 'rb') as f:
                            f.read(1024)
                        logger.info("文件可以正常讀取")
                    else:
                        raise Exception("文件未能成功保存")
                    
                except Exception as save_error:
                    logger.error(f"保存文件時發生錯誤: {str(save_error)}")
                    raise save_error
                
                return jsonify({
                    'message': '檔案上傳成功',
                    'filename': filename,
                    'originalFilename': original_filename
                }), 200
            except Exception as process_error:
                logger.error(f"處理文件時發生錯誤: {str(process_error)}")
                raise process_error
        else:
            logger.error(f"不支援的檔案格式: {file.filename}")
            return jsonify({'error': '不支援的檔案格式'}), 400
            
    except Exception as e:
        logger.error(f"上傳錯誤: {str(e)}")
        logger.error(f"錯誤類型: {type(e)}")
        traceback.print_exc()
        return jsonify({'error': f'上傳失敗: {str(e)}'}), 500

@app.route('/api/transcribe', methods=['POST'])
def transcribe_audio():
    try:
        data = request.get_json()
        if not data or 'filename' not in data:
            return jsonify({'error': '未提供檔名'}), 400
            
        filename = data['filename']
        original_filename = data.get('originalFilename', filename)
        
        # URL 解碼文件名
        original_filename = unquote(original_filename)
        filename = unquote(filename)
        
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        if not os.path.exists(file_path):
            logger.error(f"找不到檔案: {file_path}")
            return jsonify({'error': '找不到檔案'}), 404
            
        if not model:
            logger.error("Whisper 模型未正確載入")
            return jsonify({'error': 'Whisper 模型未正確載入'}), 500
            
        logger.info(f"開始轉錄音頻文件:")
        logger.info(f"- 檔案路徑: {file_path}")
        logger.info(f"- 原始檔名: {original_filename}")
        
        # 使用 whisper 進行轉錄
        result = model.transcribe(file_path, language='zh')
        
        # 檢測說話者並更新結果
        result['segments'] = detect_speakers(result['segments'])
        
        # 保存為 Markdown 文件
        md_filename = save_transcript_to_markdown(result, original_filename)
        if not md_filename:
            logger.error("保存 Markdown 文件失敗")
            return jsonify({'error': '保存轉錄結果失敗'}), 500
        
        # 在回應中加入 Markdown 文件名
        response_data = {
            'text': result['text'],
            'segments': result['segments'],
            'markdown_file': md_filename
        }
        
        logger.info("轉錄完成，返回結果")
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"轉錄錯誤: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'轉錄過程中發生錯誤: {str(e)}'}), 500

if __name__ == '__main__':
    # 確保上傳目錄存在
    Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
    # 監聽所有網絡接口
    app.run(host='0.0.0.0', port=5000, debug=True)
