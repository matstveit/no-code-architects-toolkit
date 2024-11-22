import os
import subprocess
import json
import logging
from glob import glob
from google.cloud import storage
from services.file_management import download_file

logger = logging.getLogger(__name__)

# Define storage path
STORAGE_PATH = os.environ.get("TEMP_DIR", "/tmp/")
if not os.path.exists(STORAGE_PATH):
    os.makedirs(STORAGE_PATH)

# Get the bucket name from the environment variable
GCP_BUCKET_NAME = os.environ.get("GCP_BUCKET_NAME")
if not GCP_BUCKET_NAME:
    logger.error("GCP_BUCKET_NAME environment variable is not set.")
    raise Exception("GCP_BUCKET_NAME environment variable is required.")


def get_extension_from_format(format_name):
    """
    Map format names to file extensions.
    """
    format_to_extension = {
        'mp4': 'mp4',
        'mov': 'mov',
        'avi': 'avi',
        'mkv': 'mkv',
        'webm': 'webm',
        'gif': 'gif',
        'apng': 'apng',
        'jpg': 'jpg',
        'jpeg': 'jpg',
        'png': 'png',
        'image2': 'png',
        'rawvideo': 'raw',
        'mp3': 'mp3',
        'wav': 'wav',
        'aac': 'aac',
        'flac': 'flac',
        'ogg': 'ogg'
    }
    return format_to_extension.get(format_name.lower(), 'mp4')


def get_metadata(filename, metadata_requests):
    """
    Retrieve metadata from a media file using FFmpeg and FFprobe.
    """
    metadata = {}
    if metadata_requests.get('filesize'):
        metadata['filesize'] = os.path.getsize(filename)

    if metadata_requests.get('duration') or metadata_requests.get('bitrate'):
        ffprobe_command = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            filename
        ]
        result = subprocess.run(ffprobe_command, capture_output=True, text=True)
        probe_data = json.loads(result.stdout)

        if metadata_requests.get('duration'):
            metadata['duration'] = float(probe_data['format']['duration'])
        if metadata_requests.get('bitrate'):
            metadata['bitrate'] = int(probe_data['format']['bit_rate'])

    return metadata


def upload_file_to_gcs(local_path, destination_path):
    """
    Upload a file to Google Cloud Storage.
    """
    client = storage.Client()
    bucket = client.bucket(GCP_BUCKET_NAME)
    blob = bucket.blob(destination_path)
    blob.upload_from_filename(local_path)
    blob.make_public()  # Ensure the file is publicly accessible
    return blob.public_url


def process_ffmpeg_compose(data, job_id):
    """
    Process FFmpeg composition requests, handling inputs, filters, and outputs.
    """
    output_filenames = []
    command = ["ffmpeg"]

    # Add global options
    for option in data.get("global_options", []):
        command.append(option["option"])
        if "argument" in option and option["argument"] is not None:
            command.append(str(option["argument"]))

    # Add inputs
    for input_data in data["inputs"]:
        if "options" in input_data:
            for option in input_data["options"]:
                command.append(option["option"])
                if "argument" in option and option["argument"] is not None:
                    command.append(str(option["argument"]))
        input_path = download_file(input_data["file_url"], STORAGE_PATH)
        if not os.path.exists(input_path):
            raise Exception(f"Input file not found: {input_path}")
        command.extend(["-i", input_path])

    # Add filters
    if data.get("filters"):
        filter_complex = ";".join(filter_obj["filter"] for filter_obj in data["filters"])
        command.extend(["-filter_complex", filter_complex])

    # Add outputs
    for i, output in enumerate(data["outputs"]):
        format_name = None
        for option in output["options"]:
            if option["option"] == "-f":
                format_name = option.get("argument")
                break

        extension = get_extension_from_format(format_name) if format_name else 'mp4'

        if format_name == "image2":
            pattern = os.path.join(STORAGE_PATH, f"{job_id}_output_{i}_%03d.{extension}")
            output_filename = pattern
        else:
            output_filename = os.path.join(STORAGE_PATH, f"{job_id}_output_{i}.{extension}")

        output_filenames.append(output_filename)

        for option in output["options"]:
            command.append(option["option"])
            if "argument" in option and option["argument"] is not None:
                command.append(str(option["argument"]))
        command.append(output_filename)

    # Log and execute FFmpeg command
    logger.info(f"Executing FFmpeg command: {' '.join(command)}")
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg command failed: {e.stderr}")
        raise Exception(f"FFmpeg command failed: {e.stderr}")

    # Collect and validate outputs
    generated_files = []
    for file in output_filenames:
        if "%03d" in file:
            pattern = file.replace("%03d", "*")
            generated_files.extend(glob(pattern))
        elif os.path.exists(file):
            generated_files.append(file)

    if not generated_files:
        logger.error(f"No output files generated.")
        raise Exception("No output files created.")

    # Upload files to GCS
    uploaded_files = []
    for file in generated_files:
        destination_path = f"{job_id}/{os.path.basename(file)}"
        uploaded_url = upload_file_to_gcs(file, destination_path)
        uploaded_files.append(uploaded_url)
        os.remove(file)  # Clean up local file after upload

    return uploaded_files
