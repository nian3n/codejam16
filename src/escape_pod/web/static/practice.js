// Owner: Teammate 1 (Game, scenes, widgets)
import { $, el, wordOf } from "./core.js";
import { cameraError, cameraUnavailable, openCamera, stopCamera } from "./camera.js";
import { drawLandmarks } from "./landmark_overlay.js";

const HOLISTIC_URL = "https://cdn.jsdelivr.net/npm/@mediapipe/holistic@0.5.1675471629/";
const FRAME_LAYOUT = [
  ["faceLandmarks", 468],
  ["leftHandLandmarks", 21],
  ["poseLandmarks", 33],
  ["rightHandLandmarks", 21],
];
const CAPTURE_MS = 2_500;
const MAX_FRAMES = 75;
const word = $("#practice-word");
const preview = $("#practice-preview");
const video = $("#practice-camera");
const overlay = $("#practice-landmarks");
const cameraButton = $("#practice-camera-toggle");
const captureButton = $("#capture-sign");
const status = $("#practice-status");
const result = $("#practice-result");
const reset = $("#reset-practice");
const progressKey = "ep:approved-words";
let visit = null;
let camera = null;
let holisticScript = null;
let words = [];
let approved = new Set();

// Hooks for the sequence mode (practice_sequence.js): it gets every landmark frame
// and hears when the camera stops, without owning the camera itself.
const frameListeners = new Set();
const stopListeners = new Set();
export function onPracticeFrame(fn) { frameListeners.add(fn); }
export function onPracticeStop(fn) { stopListeners.add(fn); }
export function practiceCameraReady() { return !!camera?.ready; }
export function practiceWords() { return words; }

function loadProgress() {
  try {
    const saved = JSON.parse(localStorage.getItem(progressKey) || "[]");
    return new Set(Array.isArray(saved) ? saved.filter((value) => typeof value === "string") : []);
  } catch {
    return new Set();
  }
}

function saveProgress() {
  try {
    localStorage.setItem(progressKey, JSON.stringify([...approved]));
  } catch {
    // Progress still works for this visit when browser storage is unavailable.
  }
}

// The glossary's PopSign clip of the chosen word, so the player can watch the sign first.
let clips = null;
async function showDemo() {
  const demo = $("#practice-demo");
  const clipVideo = $("#practice-clip");
  if (!clips) {
    clips = await fetch("/signs/index.json").then((r) => (r.ok ? r.json() : { clips: {} })).catch(() => ({ clips: {} }));
  }
  const entry = clips.clips?.[word.value];
  demo.classList.toggle("hidden", !entry);
  if (!entry) { clipVideo.removeAttribute("src"); return; }
  const src = `/signs/${entry.file}`;
  if (!clipVideo.src.endsWith(src)) clipVideo.src = src;
  $("#practice-credit").textContent = clips.credit || "";
  clipVideo.play().catch(() => {});
}

function renderWords(preferredIndex = 0) {
  const remaining = words.filter((gloss) => !approved.has(gloss));
  word.replaceChildren(...remaining.map((gloss) => el("option", { value: gloss, text: wordOf(gloss).toUpperCase() })));
  if (remaining.length) word.selectedIndex = preferredIndex % remaining.length;
  word.disabled = !remaining.length;
  reset.classList.toggle("hidden", !!remaining.length);
  void showDemo();
  return remaining.length;
}

function loadHolistic() {
  if (!holisticScript) {
    holisticScript = new Promise((resolve, reject) => {
      const script = el("script", { src: HOLISTIC_URL + "holistic.js", crossorigin: "anonymous" });
      script.onload = () => resolve(window.Holistic);
      script.onerror = () => {
        script.remove();
        reject(new Error("MediaPipe could not load. Check your internet connection and try again."));
      };
      document.head.append(script);
    }).catch((error) => {
      holisticScript = null;
      throw error;
    });
  }
  return holisticScript;
}

// One MediaPipe instance for the whole visit. Building one compiles the WASM and loads
// the models (seconds), so it is made once, ahead of time (preloadMediaPipe), and kept
// when the camera turns off. Results go to whichever camera session is current.
// One frame at a time through the shared instance: a frame from the previous camera
// session may still be in flight when a new session starts.
let inflight = Promise.resolve();
let holisticReady = null;
let holisticLoaded = false;
let resultsHandler = null;

function getHolistic() {
  if (!holisticReady) {
    holisticReady = (async () => {
      const Holistic = await loadHolistic();
      const holistic = new Holistic({ locateFile: (file) => HOLISTIC_URL + file });
      holistic.setOptions({ modelComplexity: 1, refineFaceLandmarks: false, selfieMode: false });
      holistic.onResults((landmarks) => resultsHandler?.(landmarks));
      await holistic.initialize();
      // initialize() does not load the pose, face and hand models: the first frame does.
      // Send one blank frame now, so that cost is paid in the background too.
      const blank = el("canvas", { width: 64, height: 64 });
      blank.getContext("2d").fillRect(0, 0, 64, 64);
      inflight = inflight.catch(() => {}).then(() => holistic.send({ image: blank }));
      await inflight;
      holisticLoaded = true;
      return holistic;
    })().catch((error) => {
      holisticReady = null;
      throw error;
    });
  }
  return holisticReady;
}

function sendFrame(holistic) {
  inflight = inflight.catch(() => {}).then(() => holistic.send({ image: video }));
  return inflight;
}

/** Start loading MediaPipe in the background. Safe to call many times. */
export function preloadMediaPipe() {
  void getHolistic().catch(() => {});  // a failure shows later, when the camera turns on
}

async function json(response) {
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Practice is unavailable.");
  return body;
}

export async function enterPractice() {
  preloadMediaPipe();  // load it while the player reads the page, not after the camera click
  const controller = new AbortController();
  visit = controller;
  word.disabled = cameraButton.disabled = captureButton.disabled = true;
  word.replaceChildren();
  reset.classList.add("hidden");
  result.classList.add("hidden");
  status.textContent = "Loading practice words…";
  try {
    const options = await json(await fetch("/api/practice", { signal: controller.signal }));
    if (visit !== controller) return;
    const threshold = new Intl.NumberFormat(undefined, { style: "percent" }).format(options.threshold);
    $("#practice-instructions").textContent = `Choose one word and sign it after the countdown. The model approves a matching sign at ${threshold} confidence or higher.`;
    words = options.words;
    approved = new Set([...approved, ...loadProgress()]);
    const remaining = renderWords();
    const error = cameraUnavailable();
    status.textContent = remaining ? error || "Turn on your camera when you’re ready." : "You approved every word.";
    cameraButton.disabled = !remaining || !!error;
  } catch (error) {
    if (visit === controller) status.textContent = error.message;
  }
}

function stopPracticeCamera(message = "Camera off.") {
  const session = camera;
  camera = null;
  if (!session) return;
  session.abort.abort();
  stopCamera(session.stream);
  // MediaPipe stays alive for the next camera session. Only this session stops listening.
  if (resultsHandler === session.onResults) resultsHandler = null;
  for (const fn of stopListeners) fn();
  video.srcObject = null;
  preview.classList.add("hidden");
  overlay.width = 0;
  cameraButton.textContent = "Turn on camera";
  captureButton.disabled = true;
  word.disabled = !word.options.length;
  cameraButton.disabled = !word.options.length;
  status.textContent = message;
}

export function leavePractice() {
  visit?.abort();
  visit = null;
  stopPracticeCamera();
}

function packedLandmarks(landmarks) {
  // Missing points stay NaN, matching the Python extractor's input contract.
  const buffer = new ArrayBuffer(543 * 3 * 4);
  const view = new DataView(buffer);
  let offset = 0;
  for (const [key, count] of FRAME_LAYOUT) {
    for (let i = 0; i < count; i++) {
      const point = landmarks[key]?.[i];
      for (const coordinate of [point?.x, point?.y, point?.z]) {
        view.setFloat32(offset, coordinate ?? NaN, true);
        offset += 4;
      }
    }
  }
  return buffer;
}

async function startPracticeCamera() {
  const session = { stream: null, holistic: null, processing: null, abort: new AbortController() };
  camera = session;
  cameraButton.textContent = "Turn off camera";
  status.textContent = "Waiting for camera permission…";
  try {
    const stream = await openCamera();
    if (camera !== session) {
      stopCamera(stream);
      return;
    }
    session.stream = stream;
    stream.getVideoTracks()[0].onended = () => {
      if (camera === session) stopPracticeCamera("Camera disconnected.");
    };
    video.srcObject = stream;
    preview.classList.remove("hidden");
    await video.play();
    if (camera !== session) return;
    if (!holisticLoaded) status.textContent = "Loading MediaPipe (only the first time)…";
    const holistic = await getHolistic();
    if (camera !== session) return;
    session.holistic = holistic;
    session.onResults = (landmarks) => {
      if (camera !== session) return;
      drawLandmarks(overlay, video, landmarks);
      if (session.frames && session.frames.length < MAX_FRAMES) session.frames.push(packedLandmarks(landmarks));
      for (const fn of frameListeners) fn(landmarks, packedLandmarks);
    };
    resultsHandler = session.onResults;
    // Prime the graph before starting the timed clip. Its first frame can load model assets.
    session.processing = sendFrame(holistic);
    await session.processing;
    if (camera !== session) return;
    captureButton.disabled = false;
    session.ready = true;
    for (const fn of frameListeners) fn(null);  // tell the sequence mode that the camera is ready
    status.textContent = "Keep your hands and upper body in view.";
    void trackPreview(session);
  } catch (error) {
    if (camera !== session) return;
    stopPracticeCamera(session.stream ? "MediaPipe camera setup failed. Check your internet connection and try again." : cameraError(error));
  }
}

async function trackPreview(session) {
  let lastTime = video.currentTime;
  try {
    while (camera === session) {
      await new Promise(requestAnimationFrame);
      if (camera !== session) break;
      if (video.currentTime === lastTime || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) continue;
      lastTime = video.currentTime;
      session.processing = sendFrame(session.holistic);
      await session.processing;
    }
  } catch {
    if (camera === session) stopPracticeCamera("Landmark tracking stopped. Turn your camera back on to try again.");
  }
}

async function captureSign() {
  const session = camera;
  const target = word.value;
  const { abort } = session;
  const targetIndex = word.selectedIndex;
  const frames = [];
  captureButton.disabled = word.disabled = true;
  result.classList.add("hidden");
  try {
    for (let count = 3; count > 0; count--) {
      if (camera !== session) return;
      status.textContent = `Get ready… ${count}`;
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    if (camera !== session) return;
    status.textContent = "Sign now.";
    session.frames = frames;
    await new Promise((resolve) => setTimeout(resolve, CAPTURE_MS));
    session.frames = null;
    if (camera !== session) return;
    if (frames.length < 3) {
      status.textContent = "Too few frames captured. Keep the practice window in view and try again.";
      return;
    }
    status.textContent = "Scoring your sign…";
    const score = await json(await fetch(`/api/practice/score?target=${encodeURIComponent(target)}`, {
      method: "POST",
      body: new Blob(frames, { type: "application/octet-stream" }),
      signal: abort.signal,
    }));
    if (camera !== session) return;
    const label = score.approved ? "Approved" : "Try again";
    const percentage = (Math.floor(score.confidence * 1000) / 10).toFixed(1);
    result.textContent = `${label} · ${wordOf(target).toUpperCase()} confidence ${percentage}% · Top guess: ${wordOf(score.best_guess).toUpperCase()}`;
    result.classList.toggle("approved", score.approved);
    result.classList.remove("hidden");
    if (score.approved) {
      approved.add(target);
      saveProgress();
      const remaining = renderWords(targetIndex);
      if (!remaining) {
        stopPracticeCamera("You approved every word.");
      } else {
        status.textContent = `${remaining} words left. The next word is ready.`;
      }
    } else {
      status.textContent = "Capture again or choose another word.";
    }
  } catch (error) {
    if (camera === session) status.textContent = error.message || "Could not score this sign. Try again.";
  } finally {
    if (camera === session) captureButton.disabled = word.disabled = !word.options.length;
  }
}

cameraButton.onclick = () => {
  if (camera) stopPracticeCamera();
  else void startPracticeCamera();
};
captureButton.onclick = () => void captureSign();
word.onchange = () => { result.classList.add("hidden"); void showDemo(); };
reset.onclick = () => {
  approved.clear();
  saveProgress();
  renderWords();
  result.classList.add("hidden");
  const error = cameraUnavailable();
  cameraButton.disabled = !!error;
  status.textContent = error || "Turn on your camera when you’re ready.";
};
window.addEventListener("pagehide", leavePractice);
window.addEventListener("pageshow", (event) => {
  if (event.persisted && !$("#practice").classList.contains("hidden")) void enterPractice();
});
