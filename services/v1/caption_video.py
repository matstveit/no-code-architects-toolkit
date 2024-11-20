import os
import subprocess
import logging
from tempfile import NamedTemporaryFile

logger = logging.getLogger(__name__)

# Define storage path for temporary files
STORAGE_PATH = "/tmp/"

def convert_rgb_to_bgr(color):
    """
    Converts an RGB color to BGR format.
    Args:
        color (str): The color in "R,G,B" format.
    Returns:
        str: The color in "B,G,R" format.
    """
    try:
        r, g, b = map(int, color.split(','))
        return f"{b},{g},{r}"
    except ValueError:
        raise ValueError("Invalid RGB format. Expected 'R,G,B'.")

def srt_to_ass(srt_content):
    """
    Converts SRT content to ASS format.
    Args:
        srt_content (str): The SRT file content.
    Returns:
        str: ASS file content.
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

def process_captioning(video_url, ass_content=None, options=None, webhook_url=None, request_id=None):
    """
    Processes captioning for a video, applying ASS subtitles.
    Args:
        video_url (str): URL of the input video.
        ass_content (str): ASS content to overlay (optional).
        options (dict): Additional options for the video processing (optional).
        webhook_url (str): URL for webhook callback (optional).
        request_id (str): Unique request identifier (optional).
    Returns:
        str: Path to the processed video file.
    """
    logger.info(f"Starting captioning process for video: {video_url}")
    options = options or {}

    # Download the video
    video_filename = download_video(video_url)
    logger.info(f"Downloaded video to: {video_filename}")

    # Handle ASS file creation if ASS content is provided
    ass_filename = None
    if ass_content:
        ass_filename = create_ass_file(ass_content)
        logger.info(f"Generated ASS file at: {ass_filename}")

    # Prepare the FFmpeg command
    output_filename = os.path.join(STORAGE_PATH, f"{request_id or 'output'}_captioned.mp4")
    ffmpeg_command = [
        "ffmpeg", "-i", video_filename
    ]

    # Add subtitles if provided
    if ass_filename:
        ffmpeg_command.extend(["-vf", f"subtitles={ass_filename}"])

    # Handle additional options
    for option, value in options.items():
        if option == "color":
            # Convert RGB to BGR for FFmpeg compatibility
            value = convert_rgb_to_bgr(value)
        ffmpeg_command.extend([f"-{option}", str(value)])

    # Output file
    ffmpeg_command.append(output_filename)

    # Execute the FFmpeg command
    try:
        logger.info(f"Running FFmpeg command: {' '.join(ffmpeg_command)}")
        subprocess.run(ffmpeg_command, check=True)
        logger.info(f"Captioned video created: {output_filename}")
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg command failed: {e.stderr}")
        raise RuntimeError("FFmpeg command failed")

    # Cleanup
    cleanup_temp_files([video_filename, ass_filename])

    return output_filename

def create_ass_file(ass_content):
    """
    Creates a temporary ASS file with the given content.
    Args:
        ass_content (str): ASS file content.
    Returns:
        str: Path to the temporary ASS file.
    """
    with NamedTemporaryFile(delete=False, suffix=".ass", dir=STORAGE_PATH) as temp_file:
        temp_file.write(ass_content.encode("utf-8"))
        return temp_file.name

def download_video(video_url):
    """
    Downloads the video from the given URL.
    Args:
        video_url (str): The URL of the video.
    Returns:
        str: The path to the downloaded video.
    """
    local_filename = os.path.join(STORAGE_PATH, os.path.basename(video_url))
    logger.info(f"Downloading video from {video_url}")
    try:
        # Simulated download; replace with actual download logic
        with open(local_filename, "wb") as f:
            f.write(b"Simulated video content")
    except Exception as e:
        logger.error(f"Error downloading video: {e}")
        raise
    return local_filename

def cleanup_temp_files(files):
    """
    Cleans up temporary files created during processing.
    Args:
        files (list): List of file paths to remove.
    """
    for file_path in files:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Deleted temporary file: {file_path}")
            except Exception as e:
                logger.error(f"Failed to delete temporary file {file_path}: {e}")
