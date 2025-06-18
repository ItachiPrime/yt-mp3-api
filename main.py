from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from yt_dlp import YoutubeDL
import os

app = FastAPI()

# Enable CORS so frontend can call it
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],  # change this to your frontend domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request body schema
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
        'cookiefile': './youtube_cookies.txt',  # Make sure this file exists
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
        'noplaylist': True,
        'quiet': True,
        'merge_output_format': 'mp3',
        'keepvideo': False,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            filename = filename.replace(".webm", ".mp3").replace(".m4a", ".mp3")

        return {
            "status": "success",
            "title": info.get("title"),
            "url": url,
            "filename": os.path.basename(filename)
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}
