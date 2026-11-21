// Owner: Teammate 1 (Game, scenes, widgets)
export function drawLandmarks(canvas, video, landmarks) {
  const scale = window.devicePixelRatio || 1;
  const width = Math.round(video.clientWidth * scale);
  const height = Math.round(video.clientHeight * scale);
  if (!width || !height || !video.videoWidth || !video.videoHeight) return;
  if (canvas.width !== width) canvas.width = width;
  if (canvas.height !== height) canvas.height = height;
  const context = canvas.getContext("2d");
  const fit = Math.min(width / video.videoWidth, height / video.videoHeight);
  const imageWidth = video.videoWidth * fit;
  const imageHeight = video.videoHeight * fit;
  const left = (width - imageWidth) / 2;
  const top = (height - imageHeight) / 2;
  context.clearRect(0, 0, width, height);
  context.save();
  context.beginPath();
  context.rect(left, top, imageWidth, imageHeight);
  context.clip();
  const pointX = (point) => left + point.x * imageWidth;
  const pointY = (point) => top + point.y * imageHeight;

  function draw(points, connections, color, radius) {
    if (!points?.length || !connections) return;
    const shown = (point) => point && Number.isFinite(point.x) && Number.isFinite(point.y)
      && (point.visibility == null || point.visibility >= 0.5);
    context.strokeStyle = context.fillStyle = color;
    context.lineWidth = radius * scale;
    context.beginPath();
    const joints = new Set();
    for (const [a, b] of connections) {
      const start = points[a];
      const end = points[b];
      if (!shown(start) || !shown(end)) continue;
      context.moveTo(pointX(start), pointY(start));
      context.lineTo(pointX(end), pointY(end));
      joints.add(a);
      joints.add(b);
    }
    context.stroke();
    for (const index of joints) {
      const point = points[index];
      context.beginPath();
      context.arc(pointX(point), pointY(point), radius * scale, 0, Math.PI * 2);
      context.fill();
    }
  }

  draw(landmarks.faceLandmarks, window.FACEMESH_CONTOURS, "#f3f9ff99", 1);
  draw(landmarks.poseLandmarks, window.POSE_CONNECTIONS, "#80d9ffcc", 2);
  draw(landmarks.leftHandLandmarks, window.HAND_CONNECTIONS, "#6affc3", 2.8);
  draw(landmarks.rightHandLandmarks, window.HAND_CONNECTIONS, "#ffd374", 2.8);
  context.restore();
}
