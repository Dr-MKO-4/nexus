# Image GPU custom pour ComfyUI (pipeline de génération d'images de l'Agent Créatif).
# Base CUDA officielle  nécessite le runtime nvidia côté hôte et Docker configuré
# avec le NVIDIA Container Toolkit.

FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# ComfyUI est cloné à la construction de l'image ; épingler un commit/tag
# précis en production pour la reproductibilité des builds.
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git .

RUN pip3 install --no-cache-dir -r requirements.txt

EXPOSE 8188

CMD ["python3", "main.py", "--listen", "0.0.0.0", "--port", "8188"]
