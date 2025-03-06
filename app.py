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
import opencc  # 在文件開頭添加 OpenCC 的導入

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
            
            # 確保文本為繁體中文
            converter = opencc.OpenCC('s2t')  # 簡體轉繁體
            text = converter.convert(text)
            
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
            
            # 最終確保輸出為繁體中文
            converter = opencc.OpenCC('s2t')  # 簡體轉繁體
            improved_text = converter.convert(improved_text)
            
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

# 定義專有名詞對照表
PROPER_NOUNS = {
    "觀西花園": "關係花園",
    "關西花園": "關係花園",
    "慧青": "慧卿",
    "關西聊天室": "關係聊天室",
    "心靈補夢網": "心靈捕夢網",
    "從關西切入": "從關係切入"
}

# 定義上下文相關詞彙替換（基於上下文的複雜替換）
CONTEXT_SPECIFIC_TERMS = [
    {
        "pattern": "關照",  # 比對模式
        "replacement": "觀照",  # 替換詞
        "context_before": ["心靈", "靈性", "自己", "內在", "意識"],  # 前文關鍵詞
        "context_distance": 20,  # 關鍵詞與目標詞的最大距離（字元數）
        "exceptions": ["關照家人", "關照朋友", "關照他人"]  # 例外情況，這些短語不替換
    }
]

def improve_text_quality(text, max_retries=3, chunk_size=1500):
    """使用 Gemini 改善文字品質
    
    Args:
        text (str): 要改善的文字
        max_retries (int): API 調用失敗時的最大重試次數
        chunk_size (int): 每個文本塊的最大字符數
    
    Returns:
        str: 改善後的文字
    """
    def split_text(text, chunk_size):
        """將文本分割成較小的塊，確保不會切斷句子"""
        # 首先按句號分割
        sentences = text.split('。')
        chunks = []
        current_chunk = []
        current_size = 0
        
        for sentence in sentences:
            # 確保句子結尾有句號
            sentence = sentence.strip() + '。' if sentence.strip() else ''
            sentence_size = len(sentence)
            
            if current_size + sentence_size > chunk_size and current_chunk:
                # 當前塊已滿，保存並開始新的塊
                chunks.append(''.join(current_chunk))
                current_chunk = [sentence]
                current_size = sentence_size
            else:
                current_chunk.append(sentence)
                current_size += sentence_size
        
        # 添加最後一個塊
        if current_chunk:
            chunks.append(''.join(current_chunk))
            
        return chunks

    try:
        logger.info("開始改善文字品質")
        
        # 初始化繁簡轉換器
        converter = opencc.OpenCC('s2t')  # 簡體轉繁體
        
        # 如果文本為空，直接返回
        if not text.strip():
            logger.warning("收到空文本，直接返回")
            return text
            
        # 分割文本為較小的塊
        text_chunks = split_text(text, chunk_size)
        improved_chunks = []
        
        # 配置模型
        model = genai.GenerativeModel('gemini-pro')
        
        # 處理每個文本塊
        for i, chunk in enumerate(text_chunks):
            logger.info(f"處理第 {i+1}/{len(text_chunks)} 個文本塊")
            
            for attempt in range(max_retries):
                try:
                    # 設置提示詞
                    prompt = f"""
                    作為一個文字校對專家，請幫我修正以下繁體中文文本。你需要：

                    1. 基本要求：
                       - 修正所有錯別字
                       - 改善文字的通順度
                       - 保持原意不變
                       - 維持繁體中文輸出
                       
                    2. 特別注意：
                       - "觀西花園" 應該是 "關係花園"
                       - "關西花園" 應該是 "關係花園"
                       - "慧青" 應該是 "慧卿"
                       - "關西聊天室" 應該是 "關係聊天室"
                       - "心靈補夢網" 應該是 "心靈捕夢網"
                       - 這些是特定名詞，請務必正確使用

                    3. 格式要求：
                       - 根據語意適當添加標點符號（逗號、句號、分號等）
                       - 按照內容邏輯分段，每段表達一個完整的思想
                       - 使用適當的段落間距來提高可讀性
                       - 重要觀點可以使用破折號來強調
                       - 對話或引述內容使用引號標示

                    以下是需要校正的文本：
                    {chunk}

                    請注意：
                    1. 保持原文的語氣和風格
                    2. 分段時要考慮上下文的連貫性
                    3. 標點符號的使用要自然，不要過度
                    4. 確保所有專有名詞的正確性
                    5. 段落長度要適中，避免過長或過短
                    """
                    
                    # 生成回應
                    response = model.generate_content(prompt)
                    
                    if response.text:
                        # 確保輸出為繁體中文
                        response_text = converter.convert(response.text)
                        
                        # 檢查並修正特定名詞
                        for wrong, correct in PROPER_NOUNS.items():
                            response_text = response_text.replace(wrong, correct)
                        
                        # 處理上下文相關詞彙替換
                        for term in CONTEXT_SPECIFIC_TERMS:
                            pattern = term['pattern']
                            replacement = term['replacement']
                            context_before = term['context_before']
                            context_distance = term['context_distance']
                            exceptions = term['exceptions']
                            
                            # 搜尋模式
                            for match in re.finditer(pattern, response_text):
                                start = match.start()
                                end = match.end()
                                
                                # 檢查前文關鍵詞
                                has_context = False
                                for keyword in context_before:
                                    if keyword in response_text[max(0, start - context_distance):start]:
                                        has_context = True
                                        break
                                
                                # 檢查例外情況
                                is_exception = False
                                for exception in exceptions:
                                    if exception in response_text[max(0, start - context_distance):end + context_distance]:
                                        is_exception = True
                                        break
                                
                                # 執行替換
                                if has_context and not is_exception:
                                    response_text = response_text[:start] + replacement + response_text[end:]
                        
                        improved_chunks.append(response_text)
                        break  # 成功處理，跳出重試循環
                    else:
                        logger.warning(f"文本塊 {i+1} 的 API 回應為空，嘗試重試 ({attempt + 1}/{max_retries})")
                
                except Exception as e:
                    logger.error(f"處理文本塊 {i+1} 時發生錯誤: {str(e)}")
                    if attempt == max_retries - 1:  # 最後一次嘗試
                        logger.error("已達到最大重試次數，使用原始文本")
                        improved_chunks.append(chunk)
                    time.sleep(1)  # 等待一秒後重試
        
        # 合併所有改善後的文本塊
        improved_text = ''.join(improved_chunks)
        
        # 最後的清理和確保繁體輸出
        improved_text = re.sub(r'\n{3,}', '\n\n', improved_text)  # 移除過多的空行
        improved_text = improved_text.strip()
        
        # 最終確保輸出為繁體中文
        improved_text = converter.convert(improved_text)
        
        # 檢查並修正特定名詞
        for wrong, correct in PROPER_NOUNS.items():
            improved_text = improved_text.replace(wrong, correct)
        
        # 處理上下文相關詞彙替換
        for term in CONTEXT_SPECIFIC_TERMS:
            pattern = term['pattern']
            replacement = term['replacement']
            context_before = term['context_before']
            context_distance = term['context_distance']
            exceptions = term['exceptions']
            
            # 搜尋模式
            for match in re.finditer(pattern, improved_text):
                start = match.start()
                end = match.end()
                
                # 檢查前文關鍵詞
                has_context = False
                for keyword in context_before:
                    if keyword in improved_text[max(0, start - context_distance):start]:
                        has_context = True
                        break
                
                # 檢查例外情況
                is_exception = False
                for exception in exceptions:
                    if exception in improved_text[max(0, start - context_distance):end + context_distance]:
                        is_exception = True
                        break
                
                # 執行替換
                if has_context and not is_exception:
                    improved_text = improved_text[:start] + replacement + improved_text[end:]
        
        logger.info("文字品質改善完成")
        return improved_text
        
    except Exception as e:
        logger.error(f"改善文字品質時發生錯誤: {str(e)}")
        logger.error(traceback.format_exc())
        return text  # 如果發生錯誤，返回原始文字

if __name__ == '__main__':
    # 確保上傳目錄存在
    Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
    # 監聽所有網絡接口
    app.run(host='0.0.0.0', port=5000, debug=True)
