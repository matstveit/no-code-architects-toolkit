from flask import Blueprint, request, jsonify
from app_utils import *
import requests
import logging
from services.authentication import authenticate
from app_utils import validate_payload

v1_media_proxy_bp = Blueprint('v1_media_proxy', __name__)
logger = logging.getLogger(__name__)

@v1_media_proxy_bp.route('/v1/media/proxy', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "url": {"type": "string", "format": "uri"},  # API endpoint to call
        "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"], "default": "GET"},  # HTTP method
        "headers": {"type": "object"},  # Custom headers
        "params": {"type": "object"},  # Query parameters
        "body": {"type": "object"},  # Request body for POST/PUT
        "id": {"type": "string"}  # Optional job identifier
    },
    "required": ["url"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def proxy_request(job_id, data):
    """
    Proxy API endpoint for making dynamic requests to third-party APIs.
    """
    url = data["url"]
    method = data.get("method", "GET").upper()
    headers = data.get("headers", {})
    params = data.get("params", {})
    body = data.get("body", None)  # Body for POST/PUT

    logger.info(f"Job {job_id}: Sending {method} request to {url} with params: {params}, headers: {headers}")

    try:
        # Dynamically make the request using `requests` library
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=body  # Automatically serializes Python dict to JSON
        )

        # Return the response as-is with status code
        logger.info(f"Job {job_id}: Received response with status code {response.status_code}")
        response_body = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": response.json() if response.headers.get("Content-Type", "").startswith("application/json") else response.text
        }

        return response_body, "/v1/media/proxy", response.status_code

    except Exception as e:
        logger.error(f"Job {job_id}: Error - {str(e)}")
        return str(e), "/v1/media/proxy", 500
