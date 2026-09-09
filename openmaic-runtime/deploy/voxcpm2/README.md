# VoxCPM2 production deployment for Mira

VoxCPM2 runs as a **private server-side TTS service**. It is not bundled into Student Web, the parent App, a camera, or each child's device. Mira's backend sends reviewed narration text to the service, stores the returned WAV bytes, records their SHA-256, and publishes the lesson only after the existing media and pronunciation gates pass.

## Recommended topology

```text
Mira backend / media worker
  -> private HTTPS or VPC/LAN HTTP
  -> Linux NVIDIA GPU host running vLLM-Omni + openbmb/VoxCPM2
  -> WAV response
  -> Mira controlled media storage
  -> human pronunciation review for pinyin and English
  -> Student Web authenticated asset endpoint
```

Development may use a GPU workstation on the same LAN. Production should use a dedicated GPU node or private cloud GPU service. Do not expose port `8000` to the public internet.

## Install and serve

Use a clean Linux environment and follow the current official vLLM-Omni installation guide for your CUDA/ROCm/XPU/MUSA/NPU platform. The official VoxCPM2 quick start currently uses:

```bash
uv pip install vllm==0.19.0 --torch-backend=auto
git clone https://github.com/vllm-project/vllm-omni.git
cd vllm-omni
uv pip install -e .

vllm serve openbmb/VoxCPM2 \
  --omni \
  --host 0.0.0.0 \
  --port 8000
```

Mira should then use the exact served model name:

```dotenv
LEARNING_VOXCPM_BASE_URL=http://<private-gpu-host>:8000
LEARNING_VOXCPM_BACKEND=vllm-omni
LEARNING_VOXCPM_MODEL=openbmb/VoxCPM2
LEARNING_VOXCPM_TIMEOUT_SECONDS=120
LEARNING_MEDIA_WORKER_ENABLED=1
LEARNING_MEDIA_WORKER_INTERVAL_SECONDS=15
```

The pinned full OpenMAIC container uses the same private endpoint for its
classroom speech actions:

```dotenv
TTS_VOXCPM_BASE_URL=http://<private-gpu-host>:8000/v1
MIRA_VOXCPM_VOICE_PROMPT=warm patient primary school teacher, clear standard pronunciation, medium pace
```

`host.docker.internal` is appropriate for Docker Desktop. Because the Mira
backend already occupies port 8000 on a one-machine development setup, start
VoxCPM2 with `--port 8002` in that case and set
`TTS_VOXCPM_BASE_URL=http://host.docker.internal:8002/v1`. In Linux production,
use the VoxCPM service name on the private Compose/Kubernetes network or a
private VPC hostname. Do not use a public browser-reachable URL.

If an operator deliberately serves the model under an alias, `LEARNING_VOXCPM_MODEL` must match that alias.

## Smoke test

Run from a machine that is allowed to reach the private GPU service:

```bash
VOXCPM_BASE_URL=http://<private-gpu-host>:8000 \
  ./openmaic-runtime/deploy/voxcpm2/smoke.sh
```

The script sends a real `POST /v1/audio/speech` request and keeps the WAV in a temporary file for listening. Passing this smoke test proves only transport and model serving. It does not approve pronunciation quality.

## Product safety rules

- Mira sends only narration text and a fixed server-owned voice design prompt.
- The student browser never receives model credentials or a VoxCPM endpoint.
- Voice-cloning reference audio is disabled in Mira's provider adapter.
- Do not upload a teacher's, child's, celebrity's, or employee's voice as reference material.
- Pinyin and English assets remain `media_pending` until a human reviewer approves pronunciation.
- Generated audio must still pass MIME, byte-size, checksum, scan, moderation and required-variant gates.
- Keep model weights, runtime packages and drivers pinned in the deployment image after the initial benchmark; do not deploy a moving `main` branch directly to production.

## About local Mac deployment

The VoxCPM repository exposes development paths for MPS and `llama.cpp-omni`, but Mira's production adapter currently speaks either the vLLM-Omni OpenAI-compatible endpoint or the existing `/tts/upload` Python service contract. A Mac demo is useful for listening tests; it is not the recommended multi-user production service and is not plug-compatible with Mira unless it exposes one of those HTTP contracts.

Official references:

- <https://github.com/OpenBMB/VoxCPM>
- <https://github.com/vllm-project/vllm-omni/blob/main/docs/user_guide/examples/online_serving/text_to_speech.md>
- <https://github.com/vllm-project/vllm-omni/blob/main/docs/serving/speech_api.md>
