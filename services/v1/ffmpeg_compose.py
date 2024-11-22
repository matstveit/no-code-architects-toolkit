import os
import subprocess
import logging
from google.cloud import storage
from services.file_management import download_file

# Initialize Logger
logger = logging.getLogger(__name__)

# Define temporary storage path
STORAGE_PATH = os.environ.get("TEMP_DIR", "/tmp/")
if not os.path.exists(STORAGE_PATH):
    os.makedirs(STORAGE_PATH)

# Bucket name for uploads
GCP_BUCKET_NAME = os.environ.get("GCP_BUCKET_NAME")
if not GCP_BUCKET_NAME:
    logger.error("GCP_BUCKET_NAME environment variable is not set.")
    raise ValueError("GCP_BUCKET_NAME environment variable is required.")

def upload_file_to_gcs(local_path, destination_path):
    """
    Upload a file to Google Cloud Storage.
    """
    client = storage.Client()
    bucket = client.bucket(GCP_BUCKET_NAME)
    blob = bucket.blob(destination_path)
    blob.upload_from_filename(local_path)
    blob.make_public()  # Optional: Make public for external access
    return blob.public_url

def process_ffmpeg_compose(data, job_id):
    """
    Process FFmpeg jobs: handle inputs, filters, and outputs.
    """
    output_files = []
    command = ["ffmpeg"]

    # Process global options
    for option in data.get("global_options", []):
        command.append(option["option"])
        if "argument" in option and option["argument"]:
            command.append(str(option["argument"]))

    # Add inputs
    for input_item in data["inputs"]:
        file_url = input_item["file_url"]
        input_path = download_file(file_url, STORAGE_PATH)
        if not os.path.exists(input_path):
            logger.error(f"Input file {input_path} could not be downloaded or does not exist.")
            raise FileNotFoundError(f"Input file {input_path} not found.")
        command.extend(["-i", input_path])

    # Add filters
    if "filters" in data:
        filter_complex = ";".join(filter_obj["filter"] for filter_obj in data["filters"])
        command.extend(["-filter_complex", filter_complex])

    # Add outputs
    for i, output in enumerate(data["outputs"]):
        format_option = next((opt for opt in output["options"] if opt["option"] == "-f"), None)
        format_name = format_option["argument"] if format_option else "mp4"
        file_extension = format_name if format_name != "image2" else "png"

        # Image sequences need a pattern
        if format_name == "image2":
            output_path = os.path.join(STORAGE_PATH, f"{job_id}_output_{i}_%03d.{file_extension}")
        else:
            output_path = os.path.join(STORAGE_PATH, f"{job_id}_output_{i}.{file_extension}")
        output_files.append(output_path)

        # Add output options
        for opt in output["options"]:
            command.append(opt["option"])
            if "argument" in opt and opt["argument"]:
                command.append(str(opt["argument"]))
        command.append(output_path)

    # Execute FFmpeg command
    try:
        logger.info(f"Executing FFmpeg command: {' '.join(command)}")
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        logger.info(f"FFmpeg output: {result.stdout}")
        if result.stderr:
            logger.error(f"FFmpeg stderr: {result.stderr}")
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg failed with error: {e.stderr}")
        raise RuntimeError(f"FFmpeg failed: {e.stderr}")

    # Validate and upload outputs
    uploaded_files = []
    for local_path in output_files:
        if not os.path.exists(local_path):
            logger.error(f"Expected output file {local_path} does not exist.")
            raise FileNotFoundError(f"Expected output file {local_path} does not exist.")
        gcs_path = upload_file_to_gcs(local_path, os.path.basename(local_path))
        uploaded_files.append(gcs_path)
        os.remove(local_path)

    return uploaded_files
