from flask import Blueprint
from app_utils import *
import logging
import os
import base64
import yt_dlp
import subprocess  # For ffprobe
from services.authentication import authenticate
from services.cloud_storage import upload_file

v1_media_download_bp = Blueprint('v1_media_download', __name__)
logger = logging.getLogger(__name__)

def get_duration(file_path):
    """
    Uses ffprobe to extract the duration of a media file.
    """
    try:
        result = subprocess.run(
            ['ffprobe', '-i', file_path, '-show_entries', 'format=duration', '-v', 'quiet', '-of', 'csv=p=0'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        duration = float(result.stdout.strip())
        return duration
    except Exception as e:
        logger.error(f"Error getting duration for file {file_path}: {e}")
        return None

@v1_media_download_bp.route('/v1/media/download', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "audio_data_list": {
            "type": "array",
            "items": {"type": "string"}
        },
        "media_url_list": {
            "type": "array",
            "items": {"type": "string", "format": "uri"}
        },
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"}
    },
    "required": [],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def download(job_id, data):
    """
    Handles uploading multiple audio files (Base64) or downloading multiple video files from media URLs.
    Returns the uploaded file URLs and durations.
    """
    audio_data_list = data.get('audio_data_list')  # Optional list of Base64-encoded audio data
    media_url_list = data.get('media_url_list')  # Optional list of media URLs
    webhook_url = data.get('webhook_url')  # Optional webhook for updates
    id = data.get('id')  # Optional job ID

    uploaded_audio_results = []
    uploaded_video_results = []

    try:
        # Process audio data list
        if audio_data_list:
            for index, audio_data in enumerate(audio_data_list):
                temp_audio_file_path = f"/tmp/{job_id}_audio_{index}.mp3"
                try:
                    logger.info(f"Job {job_id}: Decoding Base64 audio data {index + 1}/{len(audio_data_list)}")
                    decoded_audio_data = base64.b64decode(audio_data)

                    # Save as an MP3 file
                    with open(temp_audio_file_path, "wb") as audio_file:
                        audio_file.write(decoded_audio_data)

                    logger.info(f"Job {job_id}: Audio data saved as {temp_audio_file_path}")

                    # Get duration of the audio file
                    duration = get_duration(temp_audio_file_path)

                    # Upload the audio file to cloud storage
                    uploaded_audio_url = upload_file(temp_audio_file_path)
                    uploaded_audio_results.append({
                        "url": uploaded_audio_url,
                        "duration": duration
                    })
                    logger.info(f"Job {job_id}: Uploaded audio file {index + 1}/{len(audio_data_list)}: {uploaded_audio_url}, Duration: {duration} seconds")

                finally:
                    # Cleanup temporary audio file
                    if os.path.exists(temp_audio_file_path):
                        os.remove(temp_audio_file_path)

        # Process media URL list
        if media_url_list:
            for index, media_url in enumerate(media_url_list):
                temp_video_file_path = f"/tmp/{job_id}_video_{index}.mp4"
                try:
                    logger.info(f"Job {job_id}: Downloading media from {media_url} ({index + 1}/{len(media_url_list)})")
                    ydl_opts = {
                        'outtmpl': temp_video_file_path,  # Output file path
                        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4',  # Force MP4 format
                        'postprocessors': [
                            {   # Ensure remux to MP4 if original format is different
                                'key': 'FFmpegVideoConvertor',
                                'preferedformat': 'mp4'
                            }
                        ]
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([media_url])

                    # Get duration of the video file
                    duration = get_duration(temp_video_file_path)

                    # Upload the video file to cloud storage
                    uploaded_video_url = upload_file(temp_video_file_path)
                    uploaded_video_results.append({
                        "url": uploaded_video_url,
                        "duration": duration
                    })
                    logger.info(f"Job {job_id}: Uploaded video file {index + 1}/{len(media_url_list)}: {uploaded_video_url}, Duration: {duration} seconds")

                finally:
                    # Cleanup temporary video file
                    if os.path.exists(temp_video_file_path):
                        os.remove(temp_video_file_path)

        # Return response
        return {
            "message": "Media files processed successfully.",
            "uploaded_audio_results": uploaded_audio_results,
            "uploaded_video_results": uploaded_video_results
        }, "/v1/media/download", 200

    except Exception as e:
        logger.error(f"Job {job_id}: Error during processing - {str(e)}")
        return {
            "message": f"An error occurred during processing: {str(e)}"
        }, "/v1/media/download", 500
