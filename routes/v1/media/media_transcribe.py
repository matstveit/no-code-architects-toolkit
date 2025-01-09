from flask import Blueprint
from app_utils import *
import logging
import os
import yt_dlp
from services.v1.media.media_transcribe import process_transcribe_media
from services.authentication import authenticate
from services.cloud_storage import upload_file

v1_media_transcribe_bp = Blueprint('v1_media_transcribe', __name__)
logger = logging.getLogger(__name__)

@v1_media_transcribe_bp.route('/v1/media/transcribe', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "media_url": {"type": "string", "format": "uri"},
        "task": {"type": "string", "enum": ["transcribe", "translate"]},
        "include_text": {"type": "boolean"},
        "include_srt": {"type": "boolean"},
        "include_segments": {"type": "boolean"},
        "word_timestamps": {"type": "boolean"},
        "response_type": {"type": "string", "enum": ["direct", "cloud"]},
        "language": {"type": "string"},
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"}
    },
    "required": ["media_url"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def transcribe(job_id, data):
    media_url = data['media_url']
    task = data.get('task', 'transcribe')
    include_text = data.get('include_text', True)
    include_srt = data.get('include_srt', False)
    include_segments = data.get('include_segments', False)
    word_timestamps = data.get('word_timestamps', False)
    response_type = data.get('response_type', 'direct')
    language = data.get('language', None)
    webhook_url = data.get('webhook_url')
    id = data.get('id')

    logger.info(f"Job {job_id}: Received transcription request for {media_url}")

    temp_file_path = f"/tmp/{job_id}"  # Use %(ext)s so yt-dlp can insert the correct extension
    try:
        # Step 1: Download media using yt-dlp
        ydl_opts = {
            'outtmpl': temp_file_path,
            'format': 'bestaudio/best',  # Only download the best audio stream
            'postprocessors': [{
                # Extract the audio stream and convert it to FLAC
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'flac',  # or 'wav', 'm4a', 'mp3', etc.
                'preferredquality': '0'    # '0' for lossless FLAC
            }]
        }

        logger.info(f"Job {job_id}: Downloading best audio from {media_url} as FLAC")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([media_url])

        # Step 2: Upload downloaded MP4 file to cloud storage
        #logger.info(f"Job {job_id}: Uploading MP4 file to cloud storage")
        #uploaded_file_url = upload_file(temp_file_path)

        #logger.info(f"Job {job_id}: MP4 file uploaded successfully to {uploaded_file_url}")

        # Step 3: Process transcription
        logger.info(f"Job {job_id}: Starting transcription for {temp_file_path}.flac")
        result = process_transcribe_media(f"{temp_file_path}.flac", task, include_text, include_srt, include_segments, word_timestamps, response_type, language, job_id)

        # Step 4: Handle response
        logger.info(f"Job {job_id}: Transcription process completed successfully")

        if response_type == "direct":
            result_json = {
                "text": result[0],
                "srt": result[1],
                "segments": result[2]
            }
            return result_json, "/v1/media/transcribe", 200

        else:  # response_type == "cloud"
            cloud_urls = {
                "text": upload_file(result[0]) if include_text else None,
                "srt": upload_file(result[1]) if include_srt else None,
                "segments": upload_file(result[2]) if include_segments else None,
            }

            # Clean up transcription result files
            if include_text and result[0]:
                os.remove(result[0])
            if include_srt and result[1]:
                os.remove(result[1])
            if include_segments and result[2]:
                os.remove(result[2])
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)

            return cloud_urls, "/v1/media/transcribe", 200

    except Exception as e:
        logger.error(f"Job {job_id}: Error during transcription process - {str(e)}")
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        return str(e), "/v1/media/transcribe", 500
