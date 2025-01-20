from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from werkzeug.utils import secure_filename
import whisper
from pydub import AudioSegment
import re
import sys
import traceback

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

print(f"應用程序啟動")
print(f"當前工作目錄: {os.getcwd()}")
print(f"上傳目錄設置為: {UPLOAD_FOLDER}")
print(f"Python 版本: {sys.version}")
print(f"已安裝的套件:")
for name, module in sys.modules.items():
    if hasattr(module, '__version__'):
        print(f"- {name}: {module.__version__}")

# 確保上傳目錄存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def safe_filename(filename):
    # 保留中文字符和底線
    filename = secure_filename(filename)
    # 使用正則表達式替換連續的底線為單個底線
    filename = re.sub(r'_{2,}', '_', filename)
    return filename

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
            original_filename = file.filename
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

        # 構建文件路徑
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
        print("正在載入模型...")
        try:
            model = whisper.load_model("base")
            print("模型載入成功")
        except Exception as e:
            print(f"錯誤：無法載入模型: {str(e)}")
            traceback.print_exc()
            return jsonify({'error': f'無法載入模型: {str(e)}'}), 500
        
        print(f"開始轉錄檔案: {filepath}")
        try:
            # 轉錄音頻
            result = model.transcribe(filepath)
            print("轉錄完成")
            return jsonify({
                'text': result['text'],
                'message': '轉錄完成'
            }), 200
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
