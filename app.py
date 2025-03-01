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
import torch
import numpy as np
from pydub import AudioSegment
import json
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
from werkzeug.utils import secure_filename
import whisper
import google.generativeai as genai

# 設置日誌記錄
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
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
MAX_CONTENT_LENGTH = 40 * 1024 * 1024  # 40MB

app = Flask(__name__, 
    static_folder='frontend/static',  # 設定靜態檔案資料夾
    static_url_path='/static'         # 設定靜態檔案 URL 路徑
)

CORS(app, resources={
    r"/api/*": {
        "origins": ["http://localhost:5500"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "expose_headers": ["Content-Range", "X-Content-Range"],
        "supports_credentials": True
    }
})

# 初始化 Gemini API
genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))

# 載入 Whisper 模型（使用較大的模型以提高準確度）
try:
    logger.info("正在載入 Whisper 模型...")
    model = whisper.load_model("medium")
    logger.info("Whisper 模型載入成功")
except Exception as e:
    logger.error(f"載入 Whisper 模型失敗: {str(e)}")
    logger.error(traceback.format_exc())
    raise

# 儲存轉錄進度的字典
transcription_progress = {}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def normalize_filename(filename):
    """保留原始中文檔名和底線"""
    # 解碼 URL 編碼的檔名
    decoded_filename = unquote(filename)
    # 移除非法字符但保留中文、底線和空格
    safe_filename = re.sub(r'[^\w\u4e00-\u9fff_ \-]', '', decoded_filename)
    # 替換連續空格為單一底線
    safe_filename = re.sub(r'\s+', '_', safe_filename.strip())
    return safe_filename

def preprocess_audio(file_path):
    """預處理音頻文件"""
    try:
        logger.info(f"開始預處理音頻文件: {file_path}")
        
        # 讀取音頻文件
        audio = AudioSegment.from_file(file_path)
        logger.info(f"音頻文件信息: 格式={file_path.split('.')[-1].upper()}, 通道數={audio.channels}, 採樣率={audio.frame_rate}")
        
        # 獲取音頻基礎信息
        sample_rate = audio.frame_rate  # 正確屬性
        channels = audio.channels       # 正確屬性
        
        # 轉換為單聲道
        if audio.channels > 1:
            logger.info("轉換為單聲道")
            audio = audio.set_channels(1)
        
        # 設置採樣率為 16kHz（Whisper 模型的標準要求）
        if audio.frame_rate != 16000:
            logger.info(f"調整採樣率從 {audio.frame_rate} 到 16000")
            audio = audio.set_frame_rate(16000)
        
        # 導出為臨時 WAV 文件
        temp_path = file_path + '.temp.wav'
        audio.export(temp_path, format='wav')
        logger.info(f"音頻預處理完成，臨時文件保存為: {temp_path}")
        
        return temp_path
    except Exception as e:
        logger.error(f"音頻預處理失敗: {str(e)}")
        logger.error(traceback.format_exc())
        raise

@app.route('/')
def index():
    return send_from_directory('frontend', 'index.html')

@app.route('/static/js/<path:filename>')

def serve_static(filename):
    return send_from_directory('frontend/static/js', filename)

@app.route('/api/upload', methods=['POST'])
def api_upload():
    if 'file' not in request.files:
        return jsonify({'error': '未找到檔案'}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '未選擇檔案'}), 400
        
    if not allowed_file(file.filename):
        return jsonify({'error': '不支援的檔案格式'}), 400
        
    try:
        # 獲取並保留原始檔名（包含中文）
        original_filename = normalize_filename(file.filename)
        
        # 確保上傳目錄存在
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        
        # 保存檔案
        file_path = os.path.join(UPLOAD_FOLDER, original_filename)
        file.save(file_path)
        
        return jsonify({
            'message': '檔案上傳成功',
            'filename': original_filename
        })
    except Exception as e:
        logger.error(f"檔案上傳失敗: {str(e)}")
        return jsonify({'error': '檔案上傳失敗'}), 500

@app.route('/api/progress/<task_id>')
def get_progress(task_id):
    def generate():
        while True:
            if task_id in transcription_progress:
                progress_data = transcription_progress[task_id]
                yield f"data: {json.dumps(progress_data)}\n\n"
                
                if progress_data['status'] in ['completed', 'error']:
                    break
            time.sleep(0.5)  # 每0.5秒檢查一次進度
            
    return Response(generate(), mimetype='text/event-stream')

@app.route('/api/transcribe', methods=['POST'])
def api_transcribe():
    try:
        data = request.get_json()
        if not data or 'filename' not in data:
            return jsonify({'error': 'No filename provided'}), 400
        
        filename = data['filename']
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        task_id = os.path.splitext(filename)[0]
        
        if not os.path.exists(file_path):
            logger.error(f"找不到文件: {file_path}")
            return jsonify({'error': 'File not found'}), 404
        
        logger.info(f"開始處理文件: {filename}")
        transcription_progress[task_id] = {
            'status': 'processing',
            'progress': 0,
            'message': '正在初始化...'
        }
        
        # 預處理音頻
        try:
            logger.info("開始音頻預處理")
            transcription_progress[task_id].update({
                'progress': 20,
                'message': '正在處理音頻文件...'
            })
            
            processed_file = preprocess_audio(file_path)
            logger.info("音頻預處理完成")
            
            # 執行轉錄
            transcription_progress[task_id].update({
                'progress': 40,
                'message': '正在進行語音識別...'
            })
            
            # 使用 Whisper 進行轉錄
            logger.info("開始 Whisper 轉錄")
            audio_tensor = whisper.load_audio(processed_file)
            logger.info(f"音頻張量形狀: {audio_tensor.shape}")
            result = model.transcribe(audio_tensor, language="zh")
            logger.info("Whisper 轉錄完成")
            
            text = result.get('text', '')
            
            # 使用 Gemini 改善文字品質
            transcription_progress[task_id].update({
                'progress': 80,
                'message': '正在改善文字品質...'
            })
            
            improved_text = improve_text_quality(text)
            
            # 保存結果
            transcription_progress[task_id].update({
                'progress': 90,
                'message': '正在保存結果...'
            })
            
            # 生成输出文件名
            safe_filename = normalize_filename(filename)
            base_name = os.path.splitext(safe_filename)[0]
            output_filename = f"{base_name}.md"
            output_path = os.path.join(TRANSCRIPTS_FOLDER, output_filename)

            # 處理重複文件名
            counter = 1
            while os.path.exists(output_path):
                output_filename = f"{base_name}_{counter}.md"
                output_path = os.path.join(TRANSCRIPTS_FOLDER, output_filename)
                counter += 1
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(improved_text)
            
            # 清理臨時文件
            if os.path.exists(processed_file):
                os.remove(processed_file)
            
            transcription_progress[task_id].update({
                'status': 'completed',
                'progress': 100,
                'message': '轉錄完成！',
                'text': improved_text
            })
            
            return jsonify({'task_id': task_id})
            
        except Exception as e:
            logger.error(f"轉錄過程中發生錯誤: {str(e)}")
            logger.error(traceback.format_exc())
            transcription_progress[task_id].update({
                'status': 'error',
                'progress': 0,
                'message': f'發生錯誤：{str(e)}'
            })
            return jsonify({'error': str(e)}), 500
            
    except Exception as e:
        logger.error(f"API 處理過程中發生錯誤: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

def improve_text_quality(text):
    """使用 Gemini 改善文字品質"""
    try:
        # 配置模型
        model = genai.GenerativeModel('gemini-pro')
        # 設置提示詞
        prompt = f"""
        作為一個文字校對專家，請幫我修正以下繁體中文文本。你需要：

        1. 基本要求：
           - 修正所有錯別字
           - 改善文字的通順度
           - 保持原意不變
           - 維持繁體中文輸出

        2. 專有名詞規範：
           - "關係花園" (不是其他變體)
           - "關係聊天室" (不是其他變體)
           - "心靈捕夢網" (不是其他變體)
           - "關係聊天室Podcast" (不是其他變體)
           - "牢籠" (不要誤寫為"籠子"或其他變體)
           - "經驗" (不要誤寫為"經歷"或其他變體)

        3. 格式要求：
           - 根據語意適當添加標點符號（逗號、句號、分號等）
           - 按照內容邏輯分段，每段表達一個完整的思想
           - 使用適當的段落間距來提高可讀性
           - 重要觀點可以使用破折號來強調
           - 對話或引述內容使用引號標示

        以下是需要修正的文字：
        {text}

        請注意：
        1. 保持原文的語氣和風格
        2. 分段時要考慮上下文的連貫性
        3. 標點符號的使用要自然，不要過度
        4. 確保所有專有名詞的正確性
        5. 段落長度要適中，避免過長或過短
        """
        
        # 生成回應
        response = model.generate_content(prompt)
        
        # 檢查是否有回應
        if response.text:
            return response.text.strip()
        return text  # 如果 API 調用失敗，返回原始文字
    except Exception as e:
        logging.error(f"Gemini API 錯誤: {str(e)}")
        return text  # 如果 API 調用失敗，返回原始文字

if __name__ == '__main__':
    # 確保上傳目錄存在
    Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
    # 監聽所有網絡接口
    app.run(host='0.0.0.0', port=5000, debug=True)
