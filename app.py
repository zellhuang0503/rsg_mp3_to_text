from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from werkzeug.utils import secure_filename
import whisper
from pydub import AudioSegment
import re
import sys
import traceback
import json

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
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'm4a', 'ogg', 'flac'}
MAX_CONTENT_LENGTH = 25 * 1024 * 1024  # 25MB

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
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def safe_filename(filename):
    # 先將檔名轉換為 UTF-8 編碼
    filename = filename.encode('utf-8').decode('utf-8')
    # 移除不安全的字符
    filename = secure_filename(filename)
    # 確保檔名是 UTF-8 編碼
    return filename.encode('utf-8').decode('utf-8')

# 說話者分割的時間閾值（秒）
SPEAKER_SPLIT_THRESHOLD = 2.0

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
        if last_end_time > 0 and (segment['start'] - last_end_time) > SPEAKER_SPLIT_THRESHOLD:
            current_speaker += 1
        
        # 使用 UTF-8 編碼處理文字
        text = segment['text'].encode('utf-8').decode('utf-8')
        formatted_text = (
            f"[說話者 {current_speaker}] "
            f"({format_timestamp(segment['start'])} - {format_timestamp(segment['end'])}) "
            f"{text}"
        ).encode('utf-8').decode('utf-8')
        
        formatted_segments.append(formatted_text)
        last_end_time = segment['end']
    
    return formatted_segments

@app.route('/api/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            print("錯誤：請求中沒有文件")
            return jsonify({'error': '沒有檔案'}), 400
        
        file = request.files['file']
        if file.filename == '':
            print("錯誤：沒有選擇文件")
            return jsonify({'error': '沒有選擇檔案'}), 400
        
        if file and allowed_file(file.filename):
            # 確保檔名使用 UTF-8 編碼
            original_filename = file.filename.encode('utf-8').decode('utf-8')
            safe_name = safe_filename(original_filename)
            filepath = os.path.join(UPLOAD_FOLDER, safe_name)
            
            print(f"原始文件名: {original_filename}")
            print(f"安全文件名: {safe_name}")
            print(f"完整文件路徑: {filepath}")
            
            # 如果文件已存在，先刪除
            if os.path.exists(filepath):
                os.remove(filepath)
                print(f"刪除已存在的文件: {filepath}")
            
            file.save(filepath)
            
            if os.path.exists(filepath):
                size = os.path.getsize(filepath)
                print(f"文件成功保存，大小: {size} 字節")
                
                # 驗證文件是否可讀
                try:
                    with open(filepath, 'rb') as f:
                        f.read(1024)  # 嘗試讀取文件
                    print("文件可以正常讀取")
                except Exception as e:
                    print(f"警告：文件無法讀取: {str(e)}")
                    
                return jsonify({
                    'message': '檔案上傳成功',
                    'filename': safe_name,
                    'original_filename': original_filename,
                    'size': size
                }), 200
            else:
                print("錯誤：文件保存失敗")
                return jsonify({'error': '文件保存失敗'}), 500
        
        print(f"錯誤：不支援的文件格式: {file.filename}")
        return jsonify({'error': '不支援的檔案格式'}), 400
    except Exception as e:
        print(f"上傳錯誤: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': f'上傳失敗: {str(e)}'}), 500

@app.route('/api/transcribe', methods=['POST'])
def transcribe_audio():
    try:
        data = request.get_json()
        if not data:
            print("錯誤：無效的請求數據")
            return jsonify({'error': '無效的請求數據'}), 400
            
        filename = data.get('filename')
        if not filename:
            print("錯誤：未提供檔案名")
            return jsonify({'error': '未提供檔案名'}), 400

        # 構建文件路徑並確保使用 UTF-8 編碼
        filename = filename.encode('utf-8').decode('utf-8')
        filepath = os.path.abspath(os.path.join(UPLOAD_FOLDER, filename))
            
        print(f"檔案資訊：")
        print(f"- 檔案名：{filename}")
        print(f"- 完整路徑：{filepath}")
        print(f"- 目錄是否存在：{os.path.exists(UPLOAD_FOLDER)}")
        print(f"- 檔案是否存在：{os.path.exists(filepath)}")
        print(f"- 目錄內容：")
        for f in os.listdir(UPLOAD_FOLDER):
            print(f"  - {f}")
        
        if not os.path.exists(UPLOAD_FOLDER):
            print(f"錯誤：上傳目錄不存在: {UPLOAD_FOLDER}")
            return jsonify({'error': '系統錯誤：上傳目錄不存在'}), 500
        
        if not os.path.exists(filepath):
            print(f"錯誤：檔案不存在: {filepath}")
            return jsonify({'error': '檔案不存在'}), 404

        size = os.path.getsize(filepath)
        print(f"檔案存在，大小: {size} 字節")

        # 驗證文件是否可讀
        try:
            with open(filepath, 'rb') as f:
                f.read(1024)  # 嘗試讀取文件
            print("檔案可以正常讀取")
        except Exception as e:
            print(f"錯誤：檔案無法讀取: {str(e)}")
            return jsonify({'error': f'檔案無法讀取: {str(e)}'}), 500

        # 載入 Whisper 模型
        if model is None:
            print("錯誤：Whisper 模型未初始化")
            return jsonify({'error': '系統錯誤：Whisper 模型未初始化'}), 500
        
        print(f"開始轉錄檔案: {filepath}")
        try:
            # 轉錄音頻
            result = model.transcribe(
                filepath,
                language="zh",
                task="transcribe",
                verbose=True
            )
            print("轉錄完成")
            
            # 從轉錄結果中提取分段並確保使用 UTF-8 編碼
            segments = result.get('segments', [])
            if not segments:
                text = result['text'].encode('utf-8').decode('utf-8')
                segments = [{
                    'start': 0,
                    'end': 0,
                    'text': text
                }]
            
            # 處理分段並識別說話者
            formatted_segments = detect_speakers(segments)
            
            response_data = {
                'text': '\n'.join(formatted_segments),
                'segments': formatted_segments,
                'message': '轉錄完成'
            }
            
            # 確保 JSON 響應使用 UTF-8 編碼
            return app.response_class(
                response=json.dumps(response_data, ensure_ascii=False),
                status=200,
                mimetype='application/json'
            )
            
        except Exception as e:
            print(f"轉錄錯誤: {str(e)}")
            print(f"錯誤類型: {type(e)}")
            traceback.print_exc()
            return jsonify({'error': f'轉錄失敗: {str(e)}'}), 500

    except Exception as e:
        print(f"轉錄錯誤: {str(e)}")
        print(f"錯誤類型: {type(e)}")
        traceback.print_exc()
        return jsonify({'error': f'轉錄失敗: {str(e)}'}), 500

if __name__ == '__main__':
    # 確保上傳目錄存在
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    # 監聽所有網絡接口
    app.run(host='0.0.0.0', port=5000, debug=True)
