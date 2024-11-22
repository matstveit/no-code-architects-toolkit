import logging
from flask import Blueprint, request, jsonify
from app_utils import validate_payload
from services.v1.ffmpeg_compose import process_ffmpeg_compose
from services.authentication import authenticate

# Initialize Blueprint
v1_ffmpeg_compose_bp = Blueprint("v1_ffmpeg_compose", __name__)
logger = logging.getLogger(__name__)

@v1_ffmpeg_compose_bp.route("/v1/ffmpeg/compose", methods=["POST"])
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
        }
    },
    "required": ["inputs", "outputs"],
    "additionalProperties": False
})
def ffmpeg_api():
    """
    API endpoint for FFmpeg composition jobs.
    """
    try:
        data = request.get_json()
        job_id = request.headers.get("X-Job-ID", "default-job-id")
        logger.info(f"Job {job_id}: Received FFmpeg request.")
        outputs = process_ffmpeg_compose(data, job_id)
        return jsonify({"job_id": job_id, "outputs": outputs}), 200
    except Exception as e:
        logger.error(f"Error processing FFmpeg request: {str(e)}")
        return jsonify({"error": str(e)}), 500
