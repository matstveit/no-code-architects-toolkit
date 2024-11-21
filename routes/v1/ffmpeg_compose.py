import os
import logging
from flask import Blueprint
from services.v1.ffmpeg_compose import process_ffmpeg_compose, upload_file_to_gcs
from services.authentication import authenticate
from app_utils import validate_payload, queue_task_wrapper

v1_ffmpeg_compose_bp = Blueprint('v1_ffmpeg_compose', __name__)
logger = logging.getLogger(__name__)

@v1_ffmpeg_compose_bp.route('/v1/ffmpeg/compose', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "inputs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file_url": {"type": "string", "format": "uri"},
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "option": {"type": "string"},
                                "argument": {"type": ["string", "number", "null"]}
                            },
                            "required": ["option"]
                        }
                    }
                },
                "required": ["file_url"]
            },
            "minItems": 1
        },
        "filters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "filter": {"type": "string"}
                },
                "required": ["filter"]
            }
        },
        "outputs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "option": {"type": "string"},
                                "argument": {"type": ["string", "number", "null"]}
                            },
                            "required": ["option"]
                        }
                    }
                },
                "required": ["options"]
            },
            "minItems": 1
        },
        "global_options": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "option": {"type": "string"},
                    "argument": {"type": ["string", "number", "null"]}
                },
                "required": ["option"]
            }
        },
        "metadata": {
            "type": "object",
            "properties": {
                "filesize": {"type": "boolean"},
                "duration": {"type": "boolean"}
            }
        },
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"}
    },
    "required": ["inputs", "outputs"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def ffmpeg_compose_api(job_id, data):
    logger.info(f"Job {job_id}: Received FFmpeg request")

    try:
        output_filenames = process_ffmpeg_compose(data, job_id)
        uploaded_files = [
            upload_file_to_gcs(file, f"{job_id}/{os.path.basename(file)}")
            for file in output_filenames
        ]

        return {"uploaded_files": uploaded_files}, "/v1/ffmpeg/compose", 200
    except Exception as e:
        logger.error(f"Job {job_id}: Error processing FFmpeg request - {str(e)}")
        return str(e), "/v1/ffmpeg/compose", 500
