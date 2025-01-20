function App() {
    const [files, setFiles] = React.useState([]);
    const [transcribedText, setTranscribedText] = React.useState('');
    const [isLoading, setIsLoading] = React.useState(false);
    const [error, setError] = React.useState('');

    const API_BASE_URL = 'http://localhost:5000';  // 修改為正確的後端地址

    const handleFileUpload = async (event) => {
        const uploadedFiles = Array.from(event.target.files);
        setFiles(uploadedFiles);
        setError('');

        for (const file of uploadedFiles) {
            if (file.size > 25 * 1024 * 1024) {
                setError('檔案大小不能超過 25MB');
                return;
            }

            const formData = new FormData();
            formData.append('file', file);

            try {
                setIsLoading(true);
                setError('');
                
                console.log('開始上傳檔案...');
                const response = await fetch(`${API_BASE_URL}/api/upload`, {
                    method: 'POST',
                    body: formData,
                    credentials: 'include',
                    headers: {
                        'Accept': 'application/json'
                    }
                });

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.error || `上傳失敗: ${response.status}`);
                }

                const data = await response.json();
                console.log('檔案上傳成功，開始轉錄...');
                console.log('檔案名:', data.filename);
                
                // 開始轉錄
                const transcribeResponse = await fetch(`${API_BASE_URL}/api/transcribe`, {
                    method: 'POST',
                    credentials: 'include',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    body: JSON.stringify({ 
                        filename: data.filename
                    }),
                });

                if (!transcribeResponse.ok) {
                    const errorData = await transcribeResponse.json().catch(() => ({}));
                    throw new Error(errorData.error || `轉錄失敗: ${transcribeResponse.status}`);
                }

                const transcribeData = await transcribeResponse.json();
                setTranscribedText(transcribeData.text);
                console.log('轉錄完成');
            } catch (error) {
                console.error('錯誤:', error);
                setError(error.message || '處理過程中發生錯誤');
            } finally {
                setIsLoading(false);
            }
        }
    };

    return (
        <div className="container mx-auto px-4 py-8">
            <h1 className="text-3xl font-bold mb-8 text-center">MP3 轉文字工具</h1>
            
            <div className="max-w-xl mx-auto bg-white rounded-lg shadow-md p-6">
                <div className="mb-6">
                    <label className="block text-gray-700 text-sm font-bold mb-2">
                        選擇音頻檔案
                    </label>
                    <input
                        type="file"
                        accept=".mp3,.wav,.m4a,.ogg,.flac"
                        onChange={handleFileUpload}
                        className="w-full p-2 border rounded"
                        disabled={isLoading}
                    />
                    <p className="text-sm text-gray-500 mt-1">
                        支援的格式：MP3, WAV, M4A, OGG, FLAC（最大 25MB）
                    </p>
                </div>

                {error && (
                    <div className="mb-4 p-3 bg-red-100 text-red-700 rounded">
                        {error}
                    </div>
                )}

                {isLoading && (
                    <div className="text-center my-4">
                        <p className="text-gray-600">處理中，請稍候...</p>
                    </div>
                )}

                {transcribedText && (
                    <div className="mt-6">
                        <h2 className="text-xl font-semibold mb-2">轉錄結果：</h2>
                        <div className="p-4 bg-gray-50 rounded border">
                            {transcribedText}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

ReactDOM.render(<App />, document.getElementById('root'));
