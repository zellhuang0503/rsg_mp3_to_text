import whisper
from pathlib import Path

def load_whisper_model():
    model_dir = Path("./models")
    try:
        model = whisper.load_model("medium", download_root=model_dir)
        print(f"模型已成功加載至：{model_dir.absolute()}")
        return model
    except Exception as e:
        print(f"加載失敗：{str(e)}")
        raise

if __name__ == "__main__":
    load_whisper_model()
