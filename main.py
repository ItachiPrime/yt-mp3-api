from fastapi import FastAPI
from pydantic import BaseModel
from yt_dlp import YoutubeDL
from supabase import create_client, Client
from fastapi.middleware.cors import CORSMiddleware
import os
import re
import unicodedata

# --- Supabase Configuration ---
SUPABASE_URL = "https://vydfyfhndunxxcfgbzje.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ5ZGZ5ZmhuZHVueHhjZmdiemplIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTAyMzc5MjUsImV4cCI6MjA2NTgxMzkyNX0.PnBJsA4LKZO0QAFX1T8_Ps23HxLf2jj2OGuNrdUWZRI"  # <<< IMPORTANT: REPLACE WITH YOUR ACTUAL SUPABASE SERVICE KEY <<<
SUPABASE_BUCKET = "music"

# Initialize Supabase client
# Ensure SUPABASE_KEY is valid for your project
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- FastAPI Application Setup ---
app = FastAPI()

# Configure CORS middleware to allow requests from your frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],  # Adjust as needed for your frontend URL
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# --- Request Body Model ---
class DownloadRequest(BaseModel):
    """
    Pydantic model for the incoming download request.
    Requires a YouTube URL and a user ID for organizing uploads.
    """
    url: str
    user_id: str

# --- Utility Function for Filename Sanitization ---
def sanitize_filename(filename: str) -> str:
    """
    Sanitizes a string to be a valid and safe filename.
    Normalizes Unicode characters, removes illegal characters, and replaces spaces.
    """
    # Normalize Unicode characters (e.g., 'ã' -> 'a', '你好' -> 'ni hao' - though 'ignore' will remove non-ascii)
    nfkd_form = unicodedata.normalize('NFKD', filename)
    only_ascii = nfkd_form.encode('ASCII', 'ignore').decode()

    # Replace spaces with underscores, and remove/replace characters not allowed in filenames
    clean = re.sub(r'[^\w.\-]', '_', only_ascii) # Allow alphanumeric, underscore, dot, hyphen
    clean = clean.strip('_') # Remove leading/trailing underscores
    return clean

# --- API Endpoint for MP3 Download and Upload ---
@app.post("/download-mp3")
async def download_mp3(data: DownloadRequest):
    """
    Downloads an MP3 from a given YouTube URL, converts it,
    uploads it to Supabase Storage, and returns a signed URL.
    """
    url = data.url
    user_id = data.user_id
    output_dir = "./temp" # Temporary directory for downloaded files

    # Ensure the temporary directory exists
    os.makedirs(output_dir, exist_ok=True)
    logger.info(f"Temporary directory '{output_dir}' ensured to exist.")


    # Path to a cookies file, useful for downloading age-restricted content
    # Make sure this file exists on your server (e.g., Render) if needed
    cookies_path = "./youtube_cookies.txt"
    if not os.path.exists(cookies_path):
        logger.warning(f"Cookies file not found at {cookies_path}. Some videos might not download.")


    # YoutubeDL options for downloading best audio and converting to MP3
    ydl_opts = {
        'format': 'bestaudio/best', # Selects the best audio quality
        'outtmpl': f'{output_dir}/%(title)s.%(ext)s', # Output template for filename
        'postprocessors': [
            {
                'key': 'FFmpegExtractAudio', # Use FFmpeg to extract audio
                'preferredcodec': 'mp3',      # Preferred audio codec is MP3
                'preferredquality': '192',    # Audio quality
            },
            {
                'key': 'FFmpegMetadata',      # Embed metadata (like title)
            }
        ],
        # 'quiet': True,      # Temporarily disabled for debugging
        'verbose': True,    # Enable verbose output for debugging
        'noplaylist': True,   # Do not download entire playlists
        'cookiefile': cookies_path, # Use cookies for authentication/age-restricted content
    }

    downloaded_filepath = None # Initialize to None for error handling
    try:
        logger.info(f"Attempting to download from URL: {url}")
        with YoutubeDL(ydl_opts) as ydl:
            # Extract information and download the video
            # 'download=True' will trigger the download and post-processing
            info = ydl.extract_info(url, download=True)

            # Log the full info dictionary for debugging
            logger.info(f"yt-dlp info dictionary: {info}")

            # Get the actual path of the downloaded and processed file.
            # This path already includes the output_dir and has the correct .mp3 extension.
            downloaded_filepath = info.get('filepath')
            logger.info(f"yt-dlp reported downloaded_filepath: {downloaded_filepath}")

            # Check files in the temp directory
            temp_files = os.listdir(output_dir)
            logger.info(f"Files in '{output_dir}' after yt-dlp execution: {temp_files}")

            if not downloaded_filepath or not os.path.exists(downloaded_filepath):
                # This is the exact error you received. Enhanced message for clarity.
                raise Exception(
                    "Failed to download or convert MP3. "
                    "File path not found or doesn't exist. "
                    "This often indicates missing FFmpeg or a post-processing failure."
                )

            title = info.get("title", "Unknown Title") # Get video title, default if not found

            # Sanitize the base filename for safe storage in Supabase
            original_base_filename = os.path.basename(downloaded_filepath)
            final_storage_filename = sanitize_filename(original_base_filename)
            logger.info(f"Original base filename: {original_base_filename}, Sanitized: {final_storage_filename}")


        # Construct the storage path within the Supabase bucket
        # e.g., "user_id/sanitized_song_title.mp3"
        storage_path = f"{user_id}/{final_storage_filename}"
        logger.info(f"Attempting to upload '{downloaded_filepath}' to Supabase bucket '{SUPABASE_BUCKET}' at path '{storage_path}'")


        # Open the downloaded file in binary read mode
        with open(downloaded_filepath, "rb") as f:
            # Upload the file to Supabase Storage
            # 'x-upsert': 'true' means it will overwrite if a file with the same name exists
            supabase.storage.from_(SUPABASE_BUCKET).upload(
                storage_path, f,
                {
                    "content-type": "audio/mpeg", # Specify content type
                    "x-upsert": "true"             # Allow overwriting
                }
            )
        logger.info(f"File '{downloaded_filepath}' successfully uploaded to Supabase.")


        # Create a signed URL for the uploaded file, valid for 24 hours
        signed_url_response = supabase.storage.from_(SUPABASE_BUCKET).create_signed_url(storage_path, 60 * 60 * 24)
        logger.info(f"Supabase signed URL response: {signed_url_response}")

        signed_url = None
        if signed_url_response and signed_url_response.get("signedURL"):
            signed_url = signed_url_response.get("signedURL")
            logger.info(f"Generated signed URL: {signed_url}")
        else:
            logger.warning(f"Could not create signed URL for {storage_path}. Response: {signed_url_response}")
            # Even if signed URL fails, we can still return success if upload was fine,
            # but log the warning. Or raise an error if signed URL is mandatory.
            # For now, it's just a warning.


        # Return success response
        return {
            "status": "success",
            "title": title,
            "signed_url": signed_url
        }

    except Exception as e:
        # Catch any exceptions during the process and return an error message
        logger.error(f"Error during download-mp3 process: {e}", exc_info=True) # Log full traceback
        return {"status": "error", "message": str(e)}

    finally:
        # Ensure the temporary downloaded file is removed, regardless of success or failure
        if downloaded_filepath and os.path.exists(downloaded_filepath):
            try:
                os.remove(downloaded_filepath)
                logger.info(f"Cleaned up temporary file: {downloaded_filepath}")
            except OSError as e:
                logger.error(f"Error removing temporary file {downloaded_filepath}: {e}")
        else:
            logger.info("No temporary file to clean up or file was not found.")