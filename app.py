# 在導入任何模組之前設置環境變量
import os
import sys
import datetime

# 強制使用 UTF-8 編碼
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUTF8'] = '1'
os.environ['PYTHONLEGACYWINDOWSFSENCODING'] = 'utf-8'
os.environ['LANG'] = 'zh_TW.UTF-8'
os.environ['LC_ALL'] = 'zh_TW.UTF-8'

import logging
import traceback
from pathlib import Path
import re
from urllib.parse import unquote, quote
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import whisper
from pydub import AudioSegment
import json

# 設置日誌
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

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

# 配置
UPLOAD_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), 'uploads'))
TRANSCRIPTS_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), 'transcripts'))
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'm4a', 'ogg', 'flac'}
MAX_CONTENT_LENGTH = 45 * 1024 * 1024  # 45MB

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
    """安全地處理檔名，確保中文字符可以正確處理"""
    try:
        # 如果提供了原始檔名，優先使用它
        if original_filename:
            filename = original_filename
            
        # 移除不安全的字符，但保留中文
        filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)
        
        # 確保檔名不為空
        if not filename:
            return 'unnamed_file'
            
        # 取得檔案副檔名
        name, ext = os.path.splitext(filename)
        if not ext and '.' in filename:
            name = filename
            ext = ''
            
        # 如果檔名太長，截短它但保留副檔名
        max_length = 200  # Windows 最大路徑長度是 260，留些餘地
        if len(name) + len(ext) > max_length:
            name = name[:max_length - len(ext)]
            
        # 組合檔名
        safe_name = name + ext
        
        # 記錄檔名處理過程
        logger.debug(f"檔名處理過程:")
        logger.debug(f"- 原始檔名: {filename}")
        logger.debug(f"- 處理後檔名: {safe_name}")
        logger.debug(f"- 編碼: {safe_name.encode('utf-8')}")
        
        return safe_name
            
    except Exception as e:
        logger.error(f"檔名處理出錯: {str(e)}")
        logger.error(traceback.format_exc())
        return 'error_filename'

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
    """將轉錄結果保存為 Markdown 文件"""
    try:
        # 確保轉錄結果目錄存在
        Path(TRANSCRIPTS_FOLDER).mkdir(parents=True, exist_ok=True)
        
        # 生成 Markdown 文件名（使用原始音頻文件名，但改為 .md 副檔名）
        md_filename = os.path.splitext(original_filename)[0] + '.md'
        md_path = os.path.join(TRANSCRIPTS_FOLDER, md_filename)
        
        # 準備 Markdown 內容
        md_content = f"# 音頻轉錄結果：{original_filename}\n\n"
        md_content += f"轉錄時間：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        md_content += "## 內容\n\n"
        
        # 添加轉錄內容
        for segment in transcript_data['segments']:
            start_time = format_timestamp(segment['start'])
            end_time = format_timestamp(segment['end'])
            text = segment['text'].strip()
            md_content += f"[{start_time} - {end_time}] {text}\n\n"
        
        # 寫入文件
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
            
        return md_filename
    except Exception as e:
        logger.error(f"保存 Markdown 文件時出錯: {str(e)}")
        logger.error(traceback.format_exc())
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
        logger.info("開始處理轉錄請求")
        data = request.get_json()
        if not data or 'filename' not in data:
            return jsonify({'error': '未提供檔名'}), 400
            
        filename = data['filename']
        original_filename = data.get('originalFilename', filename)
        
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        if not os.path.exists(file_path):
            return jsonify({'error': '找不到檔案'}), 404
            
        if not model:
            return jsonify({'error': 'Whisper 模型未正確載入'}), 500
            
        # 使用 whisper 進行轉錄
        result = model.transcribe(file_path, language='zh')
        
        # 檢測說話者並更新結果
        result['segments'] = detect_speakers(result['segments'])
        
        # 保存為 Markdown 文件
        md_filename = save_transcript_to_markdown(result, original_filename)
        
        # 在回應中加入 Markdown 文件名
        response_data = {
            'text': result['text'],
            'segments': result['segments'],
            'markdown_file': md_filename
        }
        
        return jsonify(response_data)
    except Exception as e:
        logger.error(f"轉錄錯誤: {str(e)}")
        logger.error(f"錯誤類型: {type(e)}")
        traceback.print_exc()
        return jsonify({'error': f'轉錄失敗: {str(e)}'}), 500

if __name__ == '__main__':
    # 確保上傳目錄存在
    Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
    # 監聽所有網絡接口
    app.run(host='0.0.0.0', port=5000, debug=True)
