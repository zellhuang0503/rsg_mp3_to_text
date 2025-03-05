#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re
import glob
import logging
import argparse
from pathlib import Path
import opencc  # 繁簡轉換工具
import time

# 設置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('fix_transcripts.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 定義專有名詞對照表
PROPER_NOUNS = {
    "觀西花園": "關係花園",
    "關西花園": "關係花園",
    "慧青": "慧卿",
    "惠青": "慧卿",
    "關西聊天室": "關係聊天室",
    "關西": "關係",
    "心靈補夢網": "心靈捕夢網"
}

# 定義上下文相關詞彙替換（基於上下文的複雜替換）
CONTEXT_SPECIFIC_TERMS = [
    {
        "pattern": r"關照",  # 比對模式
        "replacement": "觀照",  # 替換詞
        "context_before": ["心靈", "靈性", "自己", "內在", "意識"],  # 前文關鍵詞
        "context_distance": 20,  # 關鍵詞與目標詞的最大距離（字元數）
        "exceptions": ["關照家人", "關照朋友", "關照他人"]  # 例外情況，這些短語不替換
    }
]

def fix_text(text):
    """修正文本內容
    
    Args:
        text (str): 要修正的文本
        
    Returns:
        str: 修正後的文本
    """
    # 初始化繁簡轉換器
    converter = opencc.OpenCC('s2t')  # 簡體轉繁體
    
    # 確保文本為繁體中文
    text = converter.convert(text)
    
    # 1. 處理專有名詞替換
    for wrong, correct in PROPER_NOUNS.items():
        text = text.replace(wrong, correct)
    
    # 2. 處理上下文相關詞彙替換
    for term in CONTEXT_SPECIFIC_TERMS:
        pattern = term["pattern"]
        replacement = term["replacement"]
        context_before = term["context_before"]
        context_distance = term["context_distance"]
        exceptions = term.get("exceptions", [])
        
        # 檢查例外情況
        for exception in exceptions:
            if exception in text:
                # 暫時替換例外情況，避免被後續規則影響
                temp_placeholder = f"__PLACEHOLDER_{int(time.time())}__"
                text = text.replace(exception, temp_placeholder)
        
        # 尋找所有匹配項
        matches = list(re.finditer(pattern, text))
        
        # 從後向前替換，以避免替換後位置變動影響
        for match in reversed(matches):
            start_idx = match.start()
            # 檢查前文是否包含上下文關鍵詞
            context_start = max(0, start_idx - context_distance)
            previous_context = text[context_start:start_idx]
            
            # 如果前文包含任一上下文關鍵詞，則進行替換
            if any(keyword in previous_context for keyword in context_before):
                # 檢查是否屬於例外情況
                is_exception = False
                for exception in exceptions:
                    if start_idx + len(pattern) <= len(text):
                        potential_match = text[start_idx:start_idx + len(exception)]
                        if exception.startswith(pattern) and potential_match == exception:
                            is_exception = True
                            break
                
                if not is_exception:
                    text = text[:start_idx] + replacement + text[start_idx + len(pattern):]
        
        # 還原例外情況的佔位符
        for exception in exceptions:
            temp_placeholder = f"__PLACEHOLDER_{int(time.time())}__"
            text = text.replace(temp_placeholder, exception)
    
    # 3. 修正標點符號和格式
    # 移除連續重複的句號
    text = re.sub(r'。{2,}', '。', text)
    
    # 移除句號後立即接著的逗號
    text = re.sub(r'。，', '。', text)
    
    # 將缺少空格的地方添加空格
    # 中文與英文之間添加空格
    text = re.sub(r'([\u4e00-\u9fff])([a-zA-Z0-9])', r'\1 \2', text)
    text = re.sub(r'([a-zA-Z0-9])([\u4e00-\u9fff])', r'\1 \2', text)
    
    # 修正連續重複的片段（超過3個相同詞組重複）
    words = re.findall(r'[\u4e00-\u9fff]+', text)  # 找出所有中文詞組
    for word in set(words):
        if len(word) >= 3:  # 只檢查長度大於等於3的詞組
            pattern = f"({word})" + r"(\s*\1){2,}"  # 匹配連續重複3次以上的詞組
            text = re.sub(pattern, r"\1", text)
    
    # 去除重複短句
    sentences = re.split(r'[。！？]', text)
    for i in range(len(sentences) - 1):
        if sentences[i] and sentences[i] == sentences[i+1]:
            text = text.replace(f"{sentences[i]}。{sentences[i]}。", f"{sentences[i]}。")
    
    # 4. 結構化文本（依據標點符號和邏輯分段）
    
    # 先替換中文中的常見分句標點為統一格式
    text = re.sub(r'，', '，\n', text)
    text = re.sub(r'；', '；\n', text)
    text = re.sub(r'：', '：\n', text)
    text = re.sub(r'。', '。\n\n', text)  # 句號後加雙換行
    text = re.sub(r'！', '！\n\n', text)
    text = re.sub(r'？', '？\n\n', text)
    
    # 分割文本為行
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # 修正行末標點
    for i in range(len(lines)):
        if lines[i] and not re.search(r'[，；：。！？]$', lines[i]):
            # 僅當行末沒有結束標點時添加逗號
            if i < len(lines) - 1:  # 非最後一行
                lines[i] += '，'
            else:  # 最後一行
                lines[i] += '。'
    
    # 移除過短行（少於5個字符）
    i = 0
    while i < len(lines) - 1:
        if len(lines[i]) < 5:
            # 如果很短，合併到下一行
            lines[i+1] = lines[i] + lines[i+1]
            lines.pop(i)
        else:
            i += 1
    
    # 將較長的段落（超過100個字符）分割成更易讀的段落
    processed_lines = []
    for line in lines:
        if len(line) > 100:
            # 尋找適當的分割點（逗號、頓號等）
            segments = []
            last_pos = 0
            potential_breaks = list(re.finditer(r'[，、；：]', line))
            
            for i, match in enumerate(potential_breaks):
                pos = match.start()
                # 如果距離上次斷點超過50個字符，考慮在這裡斷開
                if pos - last_pos > 50:
                    segments.append(line[last_pos:pos+1])
                    last_pos = pos + 1
            
            # 加入最後一段
            if last_pos < len(line):
                segments.append(line[last_pos:])
            
            processed_lines.extend(segments)
        else:
            processed_lines.append(line)
    
    # 合併段落，每3-4個短句形成一個段落
    paragraphs = []
    temp_paragraph = []
    
    for line in processed_lines:
        temp_paragraph.append(line)
        if line.endswith('。') or line.endswith('！') or line.endswith('？'):
            # 句子結束，考慮是否形成段落
            if len(''.join(temp_paragraph)) > 120 or len(temp_paragraph) >= 3:
                paragraphs.append(''.join(temp_paragraph))
                temp_paragraph = []
    
    # 添加剩餘的句子
    if temp_paragraph:
        paragraphs.append(''.join(temp_paragraph))
    
    # 最終組合文本，每個段落間添加兩個換行符
    formatted_text = '\n\n'.join(paragraphs)
    
    # 最後清理：移除過多的換行符
    formatted_text = re.sub(r'\n{3,}', '\n\n', formatted_text)
    
    return formatted_text

def process_file(file_path):
    """處理單個文件
    
    Args:
        file_path (str): 文件路徑
        
    Returns:
        bool: 處理是否成功
    """
    try:
        # 讀取文件內容
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 修正文本
        fixed_content = fix_text(content)
        
        # 如果內容有變化，才寫回文件
        if content != fixed_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(fixed_content)
            logger.info(f"已修正文件: {file_path}")
            return True
        else:
            logger.info(f"文件無需修正: {file_path}")
            return False
    
    except Exception as e:
        logger.error(f"處理文件時出錯 {file_path}: {str(e)}")
        return False

def process_directory(directory, recursive=True):
    """處理整個目錄下的所有 .md 文件
    
    Args:
        directory (str): 目錄路徑
        recursive (bool): 是否遞歸處理子目錄
        
    Returns:
        tuple: (成功數, 總數)
    """
    if recursive:
        files = glob.glob(os.path.join(directory, '**/*.md'), recursive=True)
    else:
        files = glob.glob(os.path.join(directory, '*.md'))
    
    success_count = 0
    total_count = len(files)
    
    logger.info(f"找到 {total_count} 個 .md 文件需要處理")
    
    for file_path in files:
        if process_file(file_path):
            success_count += 1
    
    return success_count, total_count

def main():
    parser = argparse.ArgumentParser(description='修正轉錄文件中的錯誤')
    parser.add_argument('--dir', type=str, default='transcripts', help='需要處理的目錄')
    parser.add_argument('--file', type=str, help='單個需要處理的文件')
    parser.add_argument('--no-recursive', action='store_true', help='不遞歸處理子目錄')
    
    args = parser.parse_args()
    
    # 設置基本路徑
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    if args.file:
        # 處理單個文件
        file_path = os.path.join(base_dir, args.file)
        if os.path.exists(file_path):
            result = process_file(file_path)
            logger.info(f"處理結果: {'成功' if result else '失敗'}")
        else:
            logger.error(f"文件不存在: {file_path}")
    else:
        # 處理目錄
        dir_path = os.path.join(base_dir, args.dir)
        if os.path.exists(dir_path) and os.path.isdir(dir_path):
            success, total = process_directory(dir_path, not args.no_recursive)
            logger.info(f"處理完成! 成功: {success}/{total}")
        else:
            logger.error(f"目錄不存在: {dir_path}")

if __name__ == '__main__':
    main()
