from http.server import HTTPServer, SimpleHTTPRequestHandler
import os

class CORSRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def guess_type(self, path):
        """Guess the type of a file based on its extension."""
        if path.endswith('.js'):
            return 'application/javascript'
        if path.endswith('.html'):
            return 'text/html'
        return super().guess_type(path)

    def translate_path(self, path):
        """將 URL 路徑轉換為文件系統路徑"""
        # 移除查詢字符串
        path = path.split('?', 1)[0]
        path = path.split('#', 1)[0]
        
        # 確保路徑以 / 開始
        path = '/' + path.lstrip('/')
        
        # 獲取當前工作目錄的絕對路徑
        base_path = os.path.abspath(os.path.dirname(__file__))
        
        # 將 URL 路徑轉換為文件系統路徑
        path = os.path.normpath(path.replace('/', os.path.sep))
        
        # 組合完整路徑
        full_path = os.path.join(base_path, path.lstrip(os.path.sep))
        
        print(f"請求路徑: {path}")
        print(f"完整路徑: {full_path}")
        print(f"檔案是否存在: {os.path.exists(full_path)}")
        
        return full_path

if __name__ == '__main__':
    # 切換到前端目錄
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # 設置服務器
    port = 5500
    server = HTTPServer(('localhost', port), CORSRequestHandler)
    print(f'啟動前端服務器在 http://localhost:{port}')
    print(f'當前工作目錄: {os.getcwd()}')
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n關閉服務器...')
        server.server_close()
