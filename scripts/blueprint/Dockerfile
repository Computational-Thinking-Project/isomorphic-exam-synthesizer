# python:3-slim tracks the newest stable Python release, excluding prereleases.
ARG PYTHON_IMAGE=python:3-slim
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    GEMINI_MODEL=gemini-3.5-flash-lite \
    BLUEPRINT_MODEL=gemini-3.5-flash-lite

WORKDIR /opt/blueprint
COPY scripts/blueprint/requirements.txt scripts/blueprint/requirements-dev.txt ./

# Fail on dependency conflicts. Version changes require the user's decision.
RUN python -m pip install --upgrade --no-cache-dir pip \
    && python -m pip install --upgrade --no-cache-dir -r requirements-dev.txt \
    && python -m pip check \
    && python -m pip freeze > /opt/blueprint/requirements-resolved.txt

WORKDIR /workspace
COPY backend/app/services/blueprint /workspace/backend/app/services/blueprint
COPY scripts/blueprint /workspace/scripts/blueprint
COPY docs/blueprints /workspace/docs/blueprints

# Verify the environment without calling an AI API or requiring credentials.
CMD ["python", "-c", "import json, platform; from importlib.metadata import version; from google.genai import types; from jsonschema import Draft202012Validator; types.GenerateContentConfig(response_mime_type='application/json', response_json_schema={'type': 'object', 'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok']}); print(json.dumps({'python': platform.python_version(), 'packages': {name: version(name) for name in ['google-genai', 'jsonschema', 'pytest', 'ruff']}, 'structured_output_config': 'supported'}, ensure_ascii=False))"]
