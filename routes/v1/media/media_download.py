from flask import Blueprint
from app_utils import *
import logging
import os
import yt_dlp
from services.authentication import authenticate
from services.cloud_storage import upload_file

v1_media_download_bp = Blueprint('v1_media_download', __name__)
logger = logging.getLogger(__name__)

@v1_media_download_bp.route('/v1/media/download', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "media_url": {"type": "string", "format": "uri"},
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"}
    },
    "required": ["media_url"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def download(job_id, data):
    media_url = data['media_url']
    webhook_url = data.get('webhook_url')
    id = data.get('id')

    temp_file_path = f"/tmp/{job_id}.mp4"
    try:
        # Step 1: Download media using yt-dlp
        ydl_opts = {
            'outtmpl': temp_file_path,  # Output file path
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4',  # Force MP4 format
            'postprocessors': [
                {   # Ensure remux to MP4 if original format is different
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4'
                }
            ]
        }

        logger.info(f"Job {job_id}: Downloading media from {media_url} in MP4 format using yt-dlp")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([media_url])

        # Step 2: Upload downloaded MP4 file to cloud storage
        logger.info(f"Job {job_id}: Uploading MP4 file to cloud storage")
        uploaded_file_url = upload_file(temp_file_path)

        logger.info(f"Job {job_id}: MP4 file uploaded successfully to {uploaded_file_url}")
          
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

        return uploaded_file_url, "/v1/media/download", 200

    except Exception as e:
        logger.error(f"Job {job_id}: Error during download process - {str(e)}")
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        return str(e), "/v1/media/download", 500
