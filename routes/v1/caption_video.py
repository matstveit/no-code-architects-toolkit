from flask import Blueprint, request, jsonify
from app_utils import validate_payload, queue_task_wrapper
import logging
from services.caption_video import process_captioning
from services.authentication import authenticate
from services.cloud_storage import upload_file

import os

# Define the blueprint for versioned captioning endpoint
v1_caption_video = Blueprint('v1_caption_video', __name__)
logger = logging.getLogger(__name__)

# Helper function to convert RGB to BGR
def convert_rgb_to_bgr(rgb_color):
    """
    Converts RGB to BGR format.
    Args:
        rgb_color (str): Color in 'R,G,B' format.
    Returns:
        str: Color in 'B,G,R' format.
    """
    try:
        r, g, b = map(int, rgb_color.split(','))
        return f"{b},{g},{r}"
    except ValueError:
        raise ValueError("Invalid RGB format. Expected 'R,G,B'.")

# Helper function to convert SRT to ASS
def srt_to_ass(srt_content):
    """
    Converts SRT content to ASS format.
    Args:
        srt_content (str): Content of the SRT file.
    Returns:
        str: Formatted ASS content.
    """
    ass_template = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayDepth: 0\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,-1,0,1,1,1,2,10,10,10,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines = srt_content.splitlines()
    events = []
    for line in lines:
        if "-->" in line:
            start, end = line.split(" --> ")
            events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,")
        elif line.isdigit() or line.strip() == "":
            continue
        else:
            events[-1] += line.replace("\n", "\\N")
    return ass_template + "\n".join(events)

# Helper function to process options
def process_options(options):
    """
    Processes and validates options, including color conversion.
    Args:
        options (list): List of option dictionaries.
    Returns:
        dict: Processed options.
    """
    processed_options = {}
    for opt in options:
        if opt["option"] == "color":
            opt["value"] = convert_rgb_to_bgr(opt["value"])
        processed_options[opt["option"]] = opt["value"]
    return processed_options

# API endpoint for caption-video
@v1_caption_video.route('/v1/caption-video', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "video_url": {"type": "string", "format": "uri"},
        "srt_file": {"type": "string"},
        "options": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "option": {"type": "string"},
                    "value": {}  # Allow any type for value
                },
                "required": ["option", "value"]
            }
        },
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"}
    },
    "required": ["video_url"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def caption_video(job_id, data):
    """
    Handles video captioning requests.
    """
    video_url = data.get("video_url")
    srt_file = data.get("srt_file")
    options = data.get("options", [])
    webhook_url = data.get("webhook_url")
    request_id = data.get("id")

    logger.info(f"Job {job_id}: Received captioning request for video URL: {video_url}")

    # Process options
    try:
        processed_options = process_options(options)
    except Exception as e:
        logger.error(f"Job {job_id}: Invalid options format: {e}")
        return str(e), "/v1/caption-video", 400

    # Convert SRT to ASS if SRT file is provided
    ass_content = None
    if srt_file:
        logger.info(f"Job {job_id}: Converting SRT to ASS")
        ass_content = srt_to_ass(srt_file)

    try:
        # Process the captioning
        output_filename = process_captioning(
            video_url=video_url,
            ass_content=ass_content,
            options=processed_options,
            webhook_url=webhook_url,
            request_id=request_id
        )

        # Upload the resulting file
        cloud_url = upload_file(output_filename)
        logger.info(f"Job {job_id}: Captioned video uploaded to cloud storage: {cloud_url}")

        # Remove the temporary output file after upload
        if os.path.exists(output_filename):
            os.remove(output_filename)

        return cloud_url, "/v1/caption-video", 200

    except Exception as e:
        logger.error(f"Job {job_id}: Error during captioning process: {str(e)}", exc_info=True)
        return str(e), "/v1/caption-video", 500
