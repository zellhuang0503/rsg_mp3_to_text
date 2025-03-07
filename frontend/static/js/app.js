function App() {
    const [files, setFiles] = React.useState([]);
    const [transcribedText, setTranscribedText] = React.useState('');
    const [error, setError] = React.useState('');
    const [isLoading, setIsLoading] = React.useState(false);
    const [progress, setProgress] = React.useState(0);
    const [progressMessage, setProgressMessage] = React.useState('');
    const progressEventSource = React.useRef(null);

    // 監控進度狀態變化
    React.useEffect(() => {
        console.log("Progress state updated:", progress);
    }, [progress]);

    const handleFileChange = async (event) => {
        const uploadedFiles = Array.from(event.target.files);
        setFiles(uploadedFiles);
        setError('');
        setProgress(0);
        setProgressMessage('');

        for (const file of uploadedFiles) {
            if (file.size > 40 * 1024 * 1024) {
                setError('檔案大小不能超過 40MB');
                return;
            }

            if (!file.type.match('audio.*')) {
                setError('請上傳音頻檔案');
                return;
            }
        }

        await uploadFiles(uploadedFiles);
    };

    const uploadFiles = async (files) => {
        for (const file of files) {
            try {
                setIsLoading(true);
                setError('');
                setProgress(0);
                setProgressMessage('正在上傳檔案...');

                const formData = new FormData();
                formData.append('file', file);

                // 保留原始檔名，包括中文字符
                const originalFilename = file.name;
                formData.append('original_filename', originalFilename);

                const response = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData,
                });

                const data = await response.json();
                if (response.ok) {
                    await transcribeFile(data.filename, originalFilename);
                } else {
                    setError(data.error || '上傳失敗');
                    setIsLoading(false);
                }
            } catch (err) {
                console.error('Upload error:', err);
                setError('上傳過程中發生錯誤');
                setIsLoading(false);
            }
        }
    };

    const transcribeFile = async (filename, originalFilename) => {
        try {
            setError('');
            setProgress(0);
            setProgressMessage('準備開始轉錄...');

            // 關閉之前的 EventSource
            if (progressEventSource.current) {
                progressEventSource.current.close();
            }

            const response = await fetch('/api/transcribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ 
                    filename,
                    original_filename: originalFilename 
                }),
            });

            const data = await response.json();
            if (response.ok) {
                // 開始監聽進度
                const eventSource = new EventSource(`/api/progress/${data.task_id}`);
                progressEventSource.current = eventSource;

                eventSource.onmessage = (event) => {
                    try {
                        const progress = JSON.parse(event.data);
                        console.log('Progress update:', progress);
                        console.log('Progress value type:', typeof progress.progress);
                        
                        // 使用 requestAnimationFrame 確保 UI 更新順暢
                        requestAnimationFrame(() => {
                            // 確保進度值是數字且在有效範圍內
                            const progressValue = Number(progress.progress);
                            if (!isNaN(progressValue) && progressValue >= 0 && progressValue <= 100) {
                                setProgress(progressValue);
                            }
                            
                            if (progress.message) {
                                setProgressMessage(progress.message);
                            }

                            if (progress.status === 'completed') {
                                eventSource.close();
                                setTranscribedText(progress.text || '');
                                setIsLoading(false);
                                setProgress(100);
                                setProgressMessage('轉錄完成！');
                            } else if (progress.status === 'error') {
                                eventSource.close();
                                setError(progress.message || '轉錄過程中發生錯誤');
                                setIsLoading(false);
                                setProgress(0);
                                setProgressMessage('');
                            }
                        });
                    } catch (err) {
                        console.error('Error parsing progress:', err);
                        setError('處理進度更新時發生錯誤');
                    }
                };

                eventSource.onerror = (err) => {
                    console.error('EventSource error:', err);
                    eventSource.close();
                    setError('進度更新連接已斷開，請重新嘗試');
                    setIsLoading(false);
                    setProgress(0);
                    setProgressMessage('');
                };
            } else {
                setError(data.error || '轉錄失敗');
                setProgress(0);
                setIsLoading(false);
                setProgressMessage('');
            }
        } catch (err) {
            console.error('Transcription error:', err);
            setError('轉錄過程中發生錯誤');
            setProgress(0);
            setIsLoading(false);
            setProgressMessage('');
        }
    };

    // 組件卸載時清理 EventSource
    React.useEffect(() => {
        return () => {
            if (progressEventSource.current) {
                progressEventSource.current.close();
            }
        };
    }, []);

    return (
        <div className="container mx-auto px-4 py-8 max-w-3xl">
            <h1 className="text-4xl font-bold mb-8 text-center">MP3 轉文字工具</h1>
            
            <div className="bg-white rounded-lg shadow-md p-6 mb-8">
                <div className="mb-4">
                    <input
                        type="file"
                        onChange={handleFileChange}
                        accept=".mp3,.wav,.m4a,.ogg,.flac"
                        className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
                        disabled={isLoading}
                    />
                    <p className="text-sm text-gray-500 mt-1">
                        支援的格式：MP3, WAV, M4A, OGG, FLAC（最大 40MB）
                    </p>
                </div>

                {/* 進度顯示區域 */}
                {(isLoading || progress > 0) && (
                    <div className="mb-6">
                        <div className="relative pt-1">
                            <div className="flex mb-2 items-center justify-between">
                                <div>
                                    <span className="text-xs font-semibold inline-block py-1 px-2 uppercase rounded-full text-blue-600 bg-blue-200">
                                        處理進度
                                    </span>
                                </div>
                                <div className="text-right">
                                    <span className="text-xs font-semibold inline-block text-blue-600">
                                        {progress}%
                                    </span>
                                </div>
                            </div>
                            <div className="overflow-hidden h-2 mb-4 text-xs flex rounded bg-blue-200">
                                <div
                                    style={{ 
                                        width: `${progress}%`,
                                        transition: 'width 0.3s ease-in-out'
                                    }}
                                    className="shadow-none flex flex-col text-center whitespace-nowrap text-white justify-center bg-blue-500"
                                ></div>
                            </div>
                            <p className="text-sm text-gray-600 text-center">{progressMessage}</p>
                        </div>
                    </div>
                )}

                {error && (
                    <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative mb-4" role="alert">
                        <span className="block sm:inline">{error}</span>
                    </div>
                )}

                {transcribedText && (
                    <div className="mt-8">
                        <h2 className="text-2xl font-bold mb-4">轉錄結果：</h2>
                        <div className="bg-gray-50 p-4 rounded-lg whitespace-pre-wrap">
                            {transcribedText}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

ReactDOM.render(<App />, document.getElementById('root'));
