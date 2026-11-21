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
import { el, send, store } from "./core.js";
import { cameraError, cameraUnavailable, openCamera, stopCamera } from "./camera.js";

const mySid = Math.random().toString(36).slice(2) + Date.now().toString(36);
let pc = null;
let localStream = null;
let remoteSid = null;
let makingOffer = false;
let ignoreOffer = false;
let wanted = false;          // true once two players are in the room
let otherOnline = false;     // from the server state: is the other player's tab connected?
let solo = false;            // a solo room: the camera feeds the sign recognizer only, no peer
let cameraIssue = "";
let cameraStarting = null;
let videoSession = 0;

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
const camBtn = el("button", { class: "btn small", text: "Camera on", onclick: toggleCamera });
const retryBtn = el("button", { class: "btn small hidden", text: "Try the camera again", onclick: startCamera });
const cameraStatus = el("p", { class: "camera-status hidden", role: "status" });
remoteVideo.muted = true;   // no audio track anyway; muted lets autoplay start without a click
localVideo.muted = true;
const dock = el("div", { class: "video-dock" },
  el("div", { class: "remote-wrap" }, remoteVideo, status, remoteName, liveTag, localVideo),
  el("div", { class: "vbar" }, camBtn, retryBtn), cameraStatus);

/** The player's own camera <video>, or null while the camera is off or not open.
 *  The sign recognizer (game_signs.js) reads frames from it: one camera, two uses. */
export function localCameraVideo() {
  const track = localStream?.getVideoTracks()[0];
  return track && track.enabled && track.readyState === "live" ? localVideo : null;
}

/** Put the dock at the top of `parent` (the lobby card or the game side panel). */
export function placeDock(parent) {
  if (!parent || dock.parentElement === parent) return;
  parent.prepend(dock);
  // Moving a <video> in the DOM can pause it.
  for (const v of [remoteVideo, localVideo]) if (v.srcObject) v.play().catch(() => {});
}

// ---------------------------------------------------------------- state from the server
export function onRoomState(s, autoCamera) {
  solo = !!s.solo;
  dock.classList.toggle("solo", solo);
  if (solo) {
    setStatus("");
    wanted = true;
    if (autoCamera && !cameraIssue) startCamera();
    renderCamera();
    return;
  }
  const other = s.players.find((p) => !p.you) || null;
  otherOnline = !!other?.online;
  if (!other && wanted) {
    // The other player left the room. Drop the old connection; when someone new joins,
    // the block below starts a fresh one.
    dropPeer();
    releaseCamera();
    wanted = false;
  }
  const label = { defuser: "agent", expert: "handler" }[other?.role] || "";
  remoteName.textContent = other ? `${other.name}${label ? " · " + label : ""}` : "";
  liveLabel.textContent = other?.role === "expert" ? "HANDLER LINK" : "AGENT CAM";
  showLive();
  if (!other) {
    setStatus("Waiting for the other player...");
  } else if (!other.online) {
    setStatus(`${other.name} is offline. Waiting...`);
  } else if (!remoteVideo.srcObject) {
    setStatus("Connecting video...");
  }
  wanted = !!other;
  if (wanted && autoCamera && !cameraIssue) startCamera();
  renderCamera();
}

// LIVE only when frames can really arrive: a track, a connected peer connection and the other
// player online. srcObject alone stays set after a drop, and ontrack fires before ICE connects.
function showLive() {
  const live = !!remoteVideo.srcObject && otherOnline && pc?.connectionState === "connected";
  liveTag.classList.toggle("hidden", !live);
}
remoteVideo.addEventListener("playing", showLive);

function setStatus(text) {
  status.textContent = text;
  status.classList.toggle("hidden", !text);
}

// ---------------------------------------------------------------- camera
function renderCamera() {
  const track = localStream?.getVideoTracks()[0];
  const enabled = !!track?.enabled;
  camBtn.textContent = enabled ? "Camera off" : "Camera on";
  camBtn.classList.toggle("hidden", !wanted || !!cameraIssue || !!cameraStarting);
  retryBtn.classList.toggle("hidden", !wanted || !cameraIssue || !!cameraStarting);
  localVideo.classList.toggle("hidden", !track);
  localVideo.classList.toggle("off", !!track && !enabled);
  cameraStatus.textContent = cameraStarting ? "Opening the camera…" : cameraIssue;
  cameraStatus.classList.toggle("hidden", !cameraStatus.textContent);
}

function startCamera() {
  if (!wanted || cameraStarting || localStream) return;
  const session = videoSession;
  cameraStarting = acquireCamera(session).then(async () => {
    if (session !== videoSession) return;
    cameraStarting = null;
    renderCamera();
    if (solo) return;
    await iceReady;
    if (session !== videoSession || !wanted) return;
    // A peer may already be receiving only after a denied camera request.
    if (localStream && pc && !pc.getSenders().some((sender) => sender.track)) resetPc();
    else ensurePc();
  });
  renderCamera();
}

async function acquireCamera(session) {
  cameraIssue = cameraUnavailable();
  if (cameraIssue) return;
  try {
    const stream = await openCamera();
    if (session !== videoSession) {
      stopCamera(stream);
      return;
    }
    localStream = stream;
    localVideo.srcObject = stream;
    stream.getVideoTracks()[0].addEventListener("ended", () => {
      if (localStream !== stream) return;
      stopCamera(stream);
      localStream = localVideo.srcObject = null;
      dropPeer();
      cameraIssue = "The camera disconnected. Reconnect it and try again.";
      renderCamera();
    });
    // placeDock also resumes playback if the video moved while permission was pending.
    localVideo.play().catch(() => {});
  } catch (error) {
    if (session === videoSession) cameraIssue = cameraError(error);
  }
}

function releaseCamera() {
  videoSession++;
  cameraStarting = null;
  cameraIssue = "";
  stopCamera(localStream);
  localStream = localVideo.srcObject = null;
  renderCamera();
}

function toggleCamera() {
  const track = localStream?.getVideoTracks()[0];
  if (!track) { startCamera(); return; }
  track.enabled = !track.enabled;  // the other side sees black; no renegotiation needed
  renderCamera();
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
    const conn = pc;
    try {
      makingOffer = true;
      await conn.setLocalDescription();
      if (pc === conn) sendRtc({ description: conn.localDescription.toJSON() });
    } catch (e) {
      console.warn("rtc offer failed", e);
    } finally {
      if (pc === conn) makingOffer = false;
    }
  };
  pc.onconnectionstatechange = () => {
    const st = pc?.connectionState;
    if (st === "failed") { setStatus("Video connection failed. Retrying..."); pc.restartIce(); }
    else if (st === "disconnected") setStatus("Video connection lost. Waiting...");
    else if (st === "connected" && remoteVideo.srcObject) setStatus("");
    showLive();
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
  releaseCamera();
  setStatus("Waiting for the other player...");
  dock.remove();
}

/** A set-up message from the other player, relayed by the server. */
export async function onRtc(data) {
  if (!wanted || solo || !data || typeof data !== "object") return;
  const session = videoSession;
  await iceReady;
  await cameraStarting;
  if (session !== videoSession || !wanted || !store.state) return;
  if (data.sid !== remoteSid) {
    // The other player has a new page (first contact or a reload): start over.
    const fresh = remoteSid !== null;
    remoteSid = data.sid;
    if (fresh) resetPc();
  }
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
        if (pc === conn) sendRtc({ description: conn.localDescription.toJSON() });
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
