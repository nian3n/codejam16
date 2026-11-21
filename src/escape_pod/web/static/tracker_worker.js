// Owner: Teammate 3 (Vision and retrieval)
// MediaPipe Holistic in a Web Worker, so its setup never freezes the page.
//
// The old @mediapipe/holistic library runs on the page's main thread: its first frame
// builds the models and blocked the page for ~6 s (9 s without a GPU). MediaPipe Tasks
// (HolisticLandmarker) runs here instead, with the same face, pose and hand models.
// The page sends ImageBitmaps and gets landmarks back in the old library's shape
// (faceLandmarks 468, poseLandmarks 33, left/rightHandLandmarks 21), which is the
// shape the word model and sequence.js expect.
//
// This is a CLASSIC worker (not a module worker): MediaPipe loads its WASM helper with
// importScripts(), which module workers do not allow. The CommonJS build of the
// library loads into a small exports shim.
self.exports = {};
// From unpkg: jsdelivr serves .cjs as application/node, which importScripts() refuses.
importScripts("https://unpkg.com/@mediapipe/tasks-vision@0.10.21/vision_bundle.cjs");
const { FilesetResolver, HolisticLandmarker } = self.exports;

const WASM = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.21/wasm";
const MODEL = "https://storage.googleapis.com/mediapipe-models/holistic_landmarker/holistic_landmarker/float16/latest/holistic_landmarker.task";
const FACE_POINTS = 468;  // the model wants the 468-point mesh; Tasks adds 10 iris points at the end

let landmarker = null;
let lastT = 0;

async function create(files, delegate) {
  return HolisticLandmarker.createFromOptions(files, {
    baseOptions: { modelAssetPath: MODEL, delegate },
    runningMode: "VIDEO",
  });
}

function points(list, keepVisibility) {
  const one = list?.[0];
  if (!one?.length) return undefined;
  // Tasks reports visibility 0 for hand and face points; only the pose has a real value.
  return one.map((p) => (keepVisibility ? { x: p.x, y: p.y, z: p.z, visibility: p.visibility } : { x: p.x, y: p.y, z: p.z }));
}

function convert(r) {
  return {
    faceLandmarks: points(r.faceLandmarks, false)?.slice(0, FACE_POINTS),
    poseLandmarks: points(r.poseLandmarks, true),
    leftHandLandmarks: points(r.leftHandLandmarks, false),
    rightHandLandmarks: points(r.rightHandLandmarks, false),
  };
}

function detect(image, t) {
  lastT = Math.max(t, lastT + 1);  // VIDEO mode needs strictly increasing timestamps
  return convert(landmarker.detectForVideo(image, lastT));
}

async function init() {
  const files = await FilesetResolver.forVisionTasks(WASM);
  try {
    landmarker = await create(files, "GPU");
  } catch {
    landmarker = await create(files, "CPU");  // no WebGL in workers on this browser
  }
  // The first frame builds the graph: pay for it here, not on the player's first frame.
  detect(new ImageData(64, 64), performance.now());
}

self.onmessage = async ({ data: m }) => {
  if (m.type === "init") {
    try {
      await init();
      self.postMessage({ type: "ready" });
    } catch (error) {
      self.postMessage({ type: "error", text: `The hand tracker could not start: ${error?.message || error}` });
    }
  } else if (m.type === "frame") {
    try {
      self.postMessage({ type: "result", id: m.id, landmarks: detect(m.bitmap, m.t) });
    } catch (error) {
      self.postMessage({ type: "result", id: m.id, error: String(error?.message || error) });
    } finally {
      m.bitmap.close();
    }
  }
};
