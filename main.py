from fastapi import FastAPI
from pydantic import BaseModel
from yt_dlp import YoutubeDL
from supabase import create_client, Client
from fastapi.middleware.cors import CORSMiddleware
import os

SUPABASE_URL = "https://vydfyfhndunxxcfgbzje.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ5ZGZ5ZmhuZHVueHhjZmdiemplIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTAyMzc5MjUsImV4cCI6MjA2NTgxMzkyNX0.PnBJsA4LKZO0QAFX1T8_Ps23HxLf2jj2OGuNrdUWZRI"  # Keep safe!
SUPABASE_BUCKET = "music"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],  # or ["*"] for all origins (not recommended in production)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class DownloadRequest(BaseModel):
    url: str
    user_id: str  # Unique user UID from Supabase Auth

@app.post("/download-mp3")
def download_mp3(data: DownloadRequest):
    url = data.url
    user_id = data.user_id
    output_dir = "./temp"
    os.makedirs(output_dir, exist_ok=True)

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
            filename = ydl.prepare_filename(info).replace(".webm", ".mp3").replace(".m4a", ".mp3")
            title = info.get("title")
            final_filename = os.path.basename(filename)

        # Upload to user-specific folder in private bucket
        file_path = os.path.join(output_dir, final_filename)
        storage_path = f"{user_id}/{final_filename}"

        with open(file_path, "rb") as f:
            supabase.storage.from_(SUPABASE_BUCKET).upload(storage_path, f, {"content-type": "audio/mpeg", "x-upsert": "true"})

        # Generate signed URL (valid for 24 hours)
        signed_url_data = supabase.storage.from_(SUPABASE_BUCKET).create_signed_url(storage_path, 60 * 60 * 24)

        os.remove(file_path)

        return {
            "status": "success",
            "title": title,
            "signed_url": signed_url_data.get("signedURL")
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}
