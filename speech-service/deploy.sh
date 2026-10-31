#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
: "${SOURCE_REVISION:?Set the full application source revision}"
: "${SPEECH_IMAGE_DIGEST:?Set the actual registry sha256 digest}"
: "${PLUGIN_SOURCE_REVISION:?Set the reviewed device plugin source revision}"
: "${PLUGIN_IMAGE_DIGEST:?Set the actual built plugin sha256 digest}"
STAGE="$(mktemp -d)"
trap 'rm -rf -- "$STAGE"' EXIT

"${PYTHON}" "${SCRIPT_DIR}/scripts/render_k8s.py" --component app \
  --source-revision "${SOURCE_REVISION}" --image-digest "${SPEECH_IMAGE_DIGEST}" > "${STAGE}/app.json"
"${PYTHON}" "${SCRIPT_DIR}/scripts/render_k8s.py" --component plugin \
  --source-revision "${PLUGIN_SOURCE_REVISION}" --image-digest "${PLUGIN_IMAGE_DIGEST}" > "${STAGE}/plugin.json"

kubectl create namespace speech-service --dry-run=client -o json | kubectl apply -f -
if ! kubectl get secret speech-service-token -n speech-service >/dev/null 2>&1; then
  "${PYTHON}" -c 'import secrets,sys; print(secrets.token_urlsafe(48),file=open(sys.argv[1],"w"))' "${STAGE}/token"
  kubectl create secret generic speech-service-token -n speech-service \
    --from-file="token=${STAGE}/token" >/dev/null
fi

kubectl apply --dry-run=server -f "${STAGE}/plugin.json"
kubectl apply -f "${STAGE}/plugin.json"
kubectl rollout status daemonset/rknpu-device-plugin -n speech-service --timeout=180s
kubectl get pods -n speech-service -l app=rknpu-device-plugin -o json | \
  "${PYTHON}" "${SCRIPT_DIR}/scripts/verify_running_image.py" --container device-plugin \
    --source-revision "${PLUGIN_SOURCE_REVISION}" --image-digest "${PLUGIN_IMAGE_DIGEST}"
kubectl wait node/orangepi5-max-server1 --for=jsonpath='{.status.allocatable.panghuer\.top/rknpu}'=1 --timeout=60s
kubectl apply --dry-run=server -f "${STAGE}/app.json"
kubectl apply -f "${STAGE}/app.json"
kubectl rollout status deployment/speech-service -n speech-service --timeout=300s
kubectl get pods -n speech-service -l app=speech-service -o json | \
  "${PYTHON}" "${SCRIPT_DIR}/scripts/verify_running_image.py" --container speech-service \
    --source-revision "${SOURCE_REVISION}" --image-digest "${SPEECH_IMAGE_DIGEST}"
echo 'Internal API: http://speech-service.speech-service.svc.cluster.local/v1'
echo 'Clients need speech-client=true and the mounted Bearer credential.'
