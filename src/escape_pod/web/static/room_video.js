// Owner: Teammate 1 (Game, scenes, widgets)
// Each camera has its own send-only connection so either player can start or
// stop sharing independently, even if both click Share at the same time.
import { $, send, store } from "./core.js";
import { cameraError, cameraUnavailable, openCamera, stopCamera } from "./camera.js";

const CONNECT_TIMEOUT = 15_000;
const DROP_TIMEOUT = 5_000;
const outgoing = { session: null, status: $("#local-camera-status"), video: $("#local-camera") };
const incoming = { session: null, status: $("#peer-camera-status"), video: $("#peer-camera") };
const toggle = $("#toggle-camera");
const share = $("#share-preview");
const supported = typeof RTCPeerConnection === "function";
let available = false;
let unavailableReason = "";
let guided = false;

function showVideo(direction, stream) {
  direction.video.srcObject = stream;
  direction.video.classList.toggle("hidden", !stream);
}

function signal(session, kind, sdp) {
  send({ type: "video", session: session.id, signal: kind, sdp });
}

function defaultStatus(direction) {
  if (direction === outgoing) return unavailableReason || "Camera off";
  return available ? "Waiting for the other player to share" : unavailableReason;
}

function end(direction, message, notify = false) {
  const session = direction.session;
  direction.session = null;
  if (session) {
    if (notify && session.signaled) signal(session, "stop");
    clearTimeout(session.timer);
    session.abort.abort();
    session.pc?.close();
    stopCamera(session.stream);
    showVideo(direction, null);
  }
  direction.status.textContent = message || defaultStatus(direction);
  if (direction === outgoing) {
    toggle.textContent = guided ? "Preview camera" : "Share camera";
    toggle.disabled = !available || !!cameraUnavailable();
    share.classList.add("hidden");
  }
}

function begin(direction, id, signaled = false) {
  const session = { id, signaled, abort: new AbortController(), pc: null, stream: null, timer: null };
  direction.session = session;
  return session;
}

function connectPeer(direction, session) {
  const pc = new RTCPeerConnection();
  session.pc = pc;
  const failed = () => end(direction, "Video connection lost. Try sharing again.", true);
  session.timer = setTimeout(failed, CONNECT_TIMEOUT);
  pc.onconnectionstatechange = () => {
    if (direction.session !== session) return;
    if (pc.connectionState === "connected") {
      clearTimeout(session.timer);
      direction.status.textContent = direction === outgoing ? "Your camera is live" : "Other player is live";
    } else if (pc.connectionState === "disconnected") {
      clearTimeout(session.timer);
      direction.status.textContent = "Reconnecting video…";
      session.timer = setTimeout(failed, DROP_TIMEOUT);
    } else if (pc.connectionState === "failed") {
      failed();
    }
  };
  return pc;
}

async function sendDescription(direction, session, kind) {
  const { pc, abort } = session;
  await pc.setLocalDescription();
  // Wait for the local candidates so each direction needs just one offer and answer.
  if (pc.iceGatheringState !== "complete" && !abort.signal.aborted) {
    await new Promise((resolve) => {
      const check = () => { if (pc.iceGatheringState === "complete") resolve(); };
      pc.addEventListener("icegatheringstatechange", check, { signal: abort.signal });
      abort.signal.addEventListener("abort", resolve, { once: true });
      check();
    });
  }
  if (direction.session !== session) return;
  signal(session, kind, pc.localDescription.sdp);
  session.signaled = true;
}

async function shareCamera(session) {
  share.classList.add("hidden");
  toggle.textContent = "Stop sharing";
  outgoing.status.textContent = "Connecting your camera…";
  try {
    const pc = connectPeer(outgoing, session);
    pc.addTransceiver(session.stream.getVideoTracks()[0], { direction: "sendonly", streams: [session.stream] });
    await sendDescription(outgoing, session, "offer");
  } catch {
    if (outgoing.session === session) end(outgoing, "Could not share video. Try again.", true);
  }
}

async function startCamera() {
  if (!available || cameraUnavailable()) return;
  const session = begin(outgoing, crypto.randomUUID());
  toggle.textContent = guided ? "Turn off camera" : "Stop sharing";
  outgoing.status.textContent = "Waiting for camera permission…";
  try {
    const stream = await openCamera();
    if (outgoing.session !== session) {
      stopCamera(stream);
      return;
    }
    session.stream = stream;
    const [track] = stream.getVideoTracks();
    track.onended = () => {
      if (outgoing.session === session) end(outgoing, "Camera disconnected.", true);
    };
    showVideo(outgoing, stream);
    if (guided) {
      outgoing.status.textContent = "Private preview. Keep your face and both hands in the frame.";
      share.classList.remove("hidden");
    } else {
      await shareCamera(session);
    }
  } catch (error) {
    if (outgoing.session !== session) return;
    end(outgoing, cameraError(error), true);
  }
}

async function receiveOffer(message) {
  end(incoming);
  const session = begin(incoming, message.session, true);
  incoming.status.textContent = "Connecting the other player's camera…";
  try {
    const pc = connectPeer(incoming, session);
    pc.ontrack = ({ track }) => {
      if (incoming.session === session && track.kind === "video") {
        showVideo(incoming, new MediaStream([track]));
      }
    };
    await pc.setRemoteDescription({ type: "offer", sdp: message.sdp });
    if (incoming.session === session) await sendDescription(incoming, session, "answer");
  } catch {
    if (incoming.session === session) end(incoming, "Could not receive video. Ask the other player to try again.", true);
  }
}

export async function receiveVideo(message) {
  if (!available) return;
  if (message.signal === "offer") {
    await receiveOffer(message);
  } else if (message.signal === "stop") {
    if (incoming.session?.id === message.session) end(incoming);
    if (outgoing.session?.id === message.session) end(outgoing, "The other player could not receive video.");
  } else if (message.signal === "answer") {
    const session = outgoing.session;
    if (session?.id !== message.session || session.pc?.signalingState !== "have-local-offer") return;
    try {
      await session.pc.setRemoteDescription({ type: "answer", sdp: message.sdp });
    } catch {
      if (outgoing.session === session) end(outgoing, "Could not connect video. Try sharing again.", true);
    }
  }
}

export function syncVideo(state) {
  const playing = state?.phase === "playing";
  guided = !!state?.guided;
  $("#room-video").classList.toggle("hidden", !playing);
  const peerOnline = playing && state.players.some((player) => player.role && player.role !== state.me.role && player.online);
  const wasAvailable = available;
  available = !!peerOnline && supported;
  unavailableReason = supported ? "Waiting for the other player to connect" : "Live video is unavailable in this browser.";
  if (!available || !wasAvailable) {
    end(outgoing, available ? cameraUnavailable() : "");
    end(incoming);
  }
}

toggle.onclick = () => {
  if (outgoing.session) end(outgoing, "", true);
  else void startCamera();
};
share.onclick = () => {
  const session = outgoing.session;
  if (session?.stream && !session.pc) void shareCamera(session);
};

window.addEventListener("pagehide", () => {
  end(outgoing, "", true);
  end(incoming);
});
