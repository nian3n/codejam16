// Owner: Teammate 1 (Game, scenes, widgets)
// Live video between the two players (WebRTC, peer to peer).
//
// The video goes browser to browser. Only the small set-up messages (offer, answer,
// ICE candidates) pass through the game server, as {"type": "rtc"} on the room's
// WebSocket; the server forwards them and never sees a frame.
//
// Negotiation follows the "perfect negotiation" pattern: both sides may send an offer
// at any time, and when offers collide the polite peer gives way. The server tells
// each browser whether it is polite (state.me.polite), so no extra round trip.
//
// Each page load has its own session id (sid). When the other player reloads, their
// messages carry a new sid, and we throw our old connection away and start fresh.
import { $, el, send, store } from "./core.js";

const mySid = Math.random().toString(36).slice(2) + Date.now().toString(36);
let pc = null;
let localStream = null;
let remoteSid = null;
let makingOffer = false;
let ignoreOffer = false;
let wanted = false;          // true once two players are in the room
let cameraError = "";
// Resolves when the camera request has finished (granted or not). onRtc waits for it:
// otherwise an offer from a player whose camera is already on makes us build the
// connection before our camera is ready, and we would only receive, never send.
let cameraStarting = Promise.resolve();

// STUN/TURN servers come from /api/ice: the server holds the TURN API key and hands
// out only short-lived logins. Fetched once per page load, before the first connection.
let iceServers = [];
const iceReady = fetch("/api/ice").then((r) => r.json()).then((s) => { iceServers = Array.isArray(s) ? s : []; })
  .catch(() => { iceServers = [{ urls: "stun:stun.l.google.com:19302" }]; });

// ---------------------------------------------------------------- the dock (built once)
const remoteVideo = el("video", { class: "remote-video", autoplay: "", playsinline: "", muted: "" });
const localVideo = el("video", { class: "local-video", autoplay: "", playsinline: "", muted: "" });
const status = el("div", { class: "vstatus", text: "Waiting for the other player..." });
const remoteName = el("span", { class: "vname" });
// "● LIVE" shows only while the other player's video actually plays; the label names the channel in the story.
const liveLabel = el("span", { text: "AGENT CAM" });
const liveTag = el("span", { class: "live-tag hidden" }, el("span", { class: "live-dot", text: "● " }), "LIVE · ", liveLabel);
const camBtn = el("button", { class: "btn small", text: "Camera off", onclick: toggleCamera });
const retryBtn = el("button", { class: "btn small hidden", text: "Try the camera again", onclick: () => { cameraError = ""; startCamera(true); } });
remoteVideo.muted = true;   // no audio track anyway; muted lets autoplay start without a click
localVideo.muted = true;
const dock = el("div", { class: "video-dock" },
  el("div", { class: "remote-wrap" }, remoteVideo, status, remoteName, liveTag, localVideo),
  el("div", { class: "vbar" }, camBtn, retryBtn));

/** Put the dock at the top of `parent` (the lobby card or the game side panel). */
export function placeDock(parent) {
  if (!parent || dock.parentElement === parent) return;
  parent.prepend(dock);
  // Moving a <video> in the DOM can pause it.
  for (const v of [remoteVideo, localVideo]) if (v.srcObject) v.play().catch(() => {});
}

// ---------------------------------------------------------------- state from the server
export function onRoomState(s) {
  const other = s.players.find((p) => !p.you) || null;
  if (!other && wanted) {
    // The other player left the room. Drop the old connection; when someone new joins,
    // the block below starts a fresh one.
    dropPeer();
    wanted = false;
  }
  const label = { defuser: "agent", expert: "HQ" }[other?.role] || "";
  remoteName.textContent = other ? `${other.name}${label ? " · " + label : ""}` : "";
  liveLabel.textContent = other?.role === "expert" ? "HQ LINK" : "AGENT CAM";
  showLive();
  if (!other) {
    setStatus("Waiting for the other player...");
  } else if (!other.online) {
    setStatus(`${other.name} is offline. Waiting...`);
  } else if (!remoteVideo.srcObject) {
    setStatus(cameraError || "Connecting video...");
  }
  if (s.players.length === 2 && !wanted) {
    wanted = true;
    startCamera(false);
  }
}

function showLive() {
  liveTag.classList.toggle("hidden", !remoteVideo.srcObject);
}

function setStatus(text) {
  status.textContent = text;
  status.classList.toggle("hidden", !text);
}

// ---------------------------------------------------------------- camera
async function startCamera(retry) {
  let done;
  cameraStarting = new Promise((r) => (done = r));
  try {
    await iceReady;
    await openCamera();
  } finally {
    done();
  }
  retryBtn.classList.toggle("hidden", !cameraError);
  camBtn.classList.toggle("hidden", !localStream);
  localVideo.classList.toggle("hidden", !localStream);
  if (cameraError) setStatus(cameraError);
  // Without a camera we still connect, to receive the other player's video.
  if (retry && pc) resetPc();
  else ensurePc();
}

async function openCamera() {
  if (!localStream) {
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      cameraError = "This page is not secure, so the browser blocks the camera. Ask the host to start the server with --https.";
    } else {
      try {
        localStream = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 24 } },
          audio: false,  // ASL is visual; no audio also means no echo with two tabs on one laptop
        });
        localVideo.srcObject = localStream;
        localVideo.play().catch(() => {});
        cameraError = "";
      } catch (e) {
        cameraError = e.name === "NotAllowedError" ? "Camera permission was denied. Allow it in the address bar."
          : e.name === "NotFoundError" ? "No camera found." : `Camera error: ${e.name}`;
      }
    }
  }
}

function toggleCamera() {
  const track = localStream?.getVideoTracks()[0];
  if (!track) return;
  track.enabled = !track.enabled;  // the other side sees black; no renegotiation needed
  camBtn.textContent = track.enabled ? "Camera off" : "Camera on";
  localVideo.classList.toggle("off", !track.enabled);
}

// ---------------------------------------------------------------- peer connection
function sendRtc(payload) {
  send({ type: "rtc", data: { sid: mySid, ...payload } });
}

function ensurePc() {
  if (pc || !wanted) return pc;
  pc = new RTCPeerConnection({ iceServers });
  if (localStream) for (const t of localStream.getTracks()) pc.addTrack(t, localStream);
  else pc.addTransceiver("video", { direction: "recvonly" });
  pc.ontrack = (e) => {
    remoteVideo.srcObject = e.streams[0] || new MediaStream([e.track]);
    remoteVideo.play().catch(() => {});
    setStatus("");
    showLive();
  };
  pc.onicecandidate = (e) => { if (e.candidate) sendRtc({ candidate: e.candidate.toJSON() }); };
  pc.onnegotiationneeded = async () => {
    try {
      makingOffer = true;
      await pc.setLocalDescription();
      sendRtc({ description: pc.localDescription.toJSON() });
    } catch (e) {
      console.warn("rtc offer failed", e);
    } finally {
      makingOffer = false;
    }
  };
  pc.onconnectionstatechange = () => {
    const st = pc?.connectionState;
    if (st === "failed") { setStatus("Video connection failed. Retrying..."); pc.restartIce(); }
    else if (st === "disconnected") setStatus("Video connection lost. Waiting...");
    else if (st === "connected" && remoteVideo.srcObject) setStatus("");
  };
  return pc;
}

function dropPeer() {
  if (pc) { pc.ontrack = pc.onicecandidate = pc.onnegotiationneeded = pc.onconnectionstatechange = null; pc.close(); }
  pc = null;
  remoteSid = null;
  remoteVideo.srcObject = null;
  makingOffer = ignoreOffer = false;
  showLive();
}

function resetPc() {
  const sid = remoteSid;  // keep it: resetPc runs because this sid is new
  dropPeer();
  remoteSid = sid;
  ensurePc();
}

/** We left the room: close the connection, turn the camera off and hide the dock. */
export function stopVideo() {
  dropPeer();
  wanted = false;
  cameraError = "";
  for (const t of localStream?.getTracks() || []) t.stop();  // turns the camera light off
  localStream = null;
  localVideo.srcObject = null;
  localVideo.classList.remove("off");
  camBtn.textContent = "Camera off";
  setStatus("Waiting for the other player...");
  dock.remove();
}

/** A set-up message from the other player, relayed by the server. */
export async function onRtc(data) {
  if (!data || typeof data !== "object") return;
  await iceReady;
  await cameraStarting;
  if (data.sid !== remoteSid) {
    // The other player has a new page (first contact or a reload): start over.
    const fresh = remoteSid !== null;
    remoteSid = data.sid;
    if (fresh) resetPc();
  }
  wanted = true;
  const conn = ensurePc();
  if (!conn) return;
  try {
    if (data.description) {
      const d = data.description;
      const collision = d.type === "offer" && (makingOffer || conn.signalingState !== "stable");
      ignoreOffer = !store.state.me.polite && collision;
      if (ignoreOffer) return;
      await conn.setRemoteDescription(d);  // a polite peer rolls back its own offer here
      if (d.type === "offer") {
        await conn.setLocalDescription();
        sendRtc({ description: conn.localDescription.toJSON() });
      }
    } else if (data.candidate) {
      try {
        await conn.addIceCandidate(data.candidate);
      } catch (e) {
        if (!ignoreOffer) console.warn("rtc candidate failed", e);
      }
    }
  } catch (e) {
    console.warn("rtc message failed", e);
  }
}
