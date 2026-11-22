// Owner: Teammate 1 (Game, scenes, widgets)
export function cameraUnavailable() {
  if (!window.isSecureContext) return "Open the game on HTTPS or localhost to use your camera.";
  if (!navigator.mediaDevices?.getUserMedia) return "Camera access is unavailable in this browser.";
  return "";
}

export function openCamera() {
  return navigator.mediaDevices.getUserMedia({
    audio: false,
    video: { width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 24 } },
  });
}

export function stopCamera(stream) {
  for (const track of stream?.getTracks() ?? []) track.stop();
}

export function cameraError(error) {
  if (error.name === "NotAllowedError") return "Allow camera access in your browser and try again.";
  if (error.name === "NotFoundError") return "Connect a camera and try again.";
  return "Could not open the camera. Check whether another app is using it.";
}
