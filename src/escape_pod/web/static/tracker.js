// Owner: Teammate 3 (Vision and retrieval)
// The page side of the hand tracker (tracker_worker.js). One worker for the whole visit.
//
//   startTracker()  -> Promise: resolves when the models are loaded and warm. Safe to
//                      call many times; call it early to preload.
//   track(video)    -> Promise of landmarks for the current video frame
//                      ({faceLandmarks, poseLandmarks, leftHandLandmarks, rightHandLandmarks}).
let worker = null;
let ready = null;
let loaded = false;
let nextId = 1;
const pending = new Map();

export function trackerLoaded() { return loaded; }

export function startTracker() {
  if (!ready) {
    ready = new Promise((resolve, reject) => {
      worker = new Worker(new URL("./tracker_worker.js", import.meta.url));  // classic: see tracker_worker.js
      worker.onmessage = ({ data: m }) => {
        if (m.type === "ready") { loaded = true; resolve(); }
        else if (m.type === "error") reject(new Error(m.text));
        else if (m.type === "result") {
          const p = pending.get(m.id);
          pending.delete(m.id);
          if (m.error) p?.reject(new Error(m.error)); else p?.resolve(m.landmarks);
        }
      };
      worker.onerror = (e) => reject(new Error(e.message || "The hand tracker could not start. Check your internet connection."));
      worker.postMessage({ type: "init" });
    });
    ready.catch(() => {
      // Let the next call try again from scratch (for example after a network error).
      worker?.terminate();
      worker = null;
      ready = null;
      for (const p of pending.values()) p.reject(new Error("The hand tracker stopped."));
      pending.clear();
    });
  }
  return ready;
}

export async function track(video) {
  await startTracker();
  const bitmap = await createImageBitmap(video);
  const id = nextId++;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    worker.postMessage({ type: "frame", id, bitmap, t: performance.now() }, [bitmap]);
  });
}
