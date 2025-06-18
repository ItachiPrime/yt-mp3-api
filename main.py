from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from yt_dlp import YoutubeDL
import os

app = FastAPI()

# ✅ Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],  # Replace with ["http://localhost:8080"] for stricter security
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class DownloadRequest(BaseModel):
    url: str

@app.post("/download-mp3")
def download_mp3(data: DownloadRequest):
    url = data.url
    output_dir = "./downloads"

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{output_dir}/%(title)s.%(ext)s',
        'postprocessors': [
            {
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            },
            {
                'key': 'FFmpegMetadata',
            }
        ],
        'quiet': True,
        'noplaylist': True,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # Replace common audio extensions with .mp3
            filename = ydl.prepare_filename(info)
            filename = (
                filename.replace(".webm", ".mp3")
                        .replace(".m4a", ".mp3")
                        .replace(".opus", ".mp3")
            )

        return {
            "status": "success",
            "title": info.get("title"),
            "url": url,
            "filename": filename.split("/")[-1]
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }
