// Owner: Teammate 1 (Game, scenes, widgets)
// Skeleton lines. The old MediaPipe library put these on window; the worker tracker
// (tracker_worker.js) does not, so they live here.
const path = (ids) => ids.slice(1).map((id, i) => [ids[i], id]);
const HAND = [[0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8], [5, 9], [9, 10], [10, 11], [11, 12],
  [9, 13], [13, 14], [14, 15], [15, 16], [13, 17], [0, 17], [17, 18], [18, 19], [19, 20]];
const POSE = [[11, 12], [11, 13], [13, 15], [12, 14], [14, 16], [11, 23], [12, 24], [23, 24],
  [15, 17], [15, 19], [17, 19], [16, 18], [16, 20], [18, 20]];
const FACE = [
  ...path([10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152,
    148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109, 10]),            // face oval
  ...path([61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185, 61]),  // lips
  ...path([33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246, 33]),             // eye
  ...path([263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466, 263]),         // eye
];

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

  draw(landmarks.faceLandmarks, FACE, "#f3f9ff99", 1);
  draw(landmarks.poseLandmarks, POSE, "#80d9ffcc", 2);
  draw(landmarks.leftHandLandmarks, HAND, "#6affc3", 2.8);
  draw(landmarks.rightHandLandmarks, HAND, "#ffd374", 2.8);
  context.restore();
}
