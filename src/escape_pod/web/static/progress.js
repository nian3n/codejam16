// Owner: Teammate 1 (Game, scenes, widgets)
import { $, el } from "./core.js";

const PRACTICE_TARGET_POINTS = 50;
const PROFILE_PREFIX = "ep:profile:";
const SELECTED_PROFILE_KEY = "ep:selected-profile";
const CREDIT_PREFIX = "ep:practice-credit:";
const LEGACY_WORDS_KEY = "ep:approved-words";
const picker = $("#profile");
const nameInput = $("#name");
const panel = $("#practice-progress");
let activeProfile = null;

export function newPracticeId() {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function getProfile(id) {
  const name = id && localStorage.getItem(PROFILE_PREFIX + id);
  return name ? { id, name } : null;
}

function renderPicker() {
  const profiles = Object.keys(localStorage).filter((key) => key.startsWith(PROFILE_PREFIX))
    .map((key) => getProfile(key.slice(PROFILE_PREFIX.length)));
  picker.replaceChildren(...profiles.map(({ id, name }) => el("option", { value: id, text: name })),
    el("option", { value: "", text: "New profile…" }));
  picker.value = activeProfile?.id ?? "";
}

function selectProfile(profile) {
  activeProfile = profile;
  sessionStorage.setItem(SELECTED_PROFILE_KEY, profile?.id ?? "");
  if (profile) localStorage.setItem(SELECTED_PROFILE_KEY, profile.id);
  nameInput.value = "";
  $("#profile-name").classList.toggle("hidden", !!profile);
  renderProgress();
}

function createProfile(name) {
  const profile = { id: newPracticeId(), name };
  const legacyWords = localStorage.getItem(LEGACY_WORDS_KEY);
  if (legacyWords !== null) {
    localStorage.setItem(approvedWordsKey(profile), legacyWords);
    localStorage.removeItem(LEGACY_WORDS_KEY);
  }
  localStorage.setItem(PROFILE_PREFIX + profile.id, name);
  selectProfile(profile);
  renderPicker();
  return profile;
}

export function bindProfiles() {
  const selected = sessionStorage.getItem(SELECTED_PROFILE_KEY) ?? localStorage.getItem(SELECTED_PROFILE_KEY);
  selectProfile(getProfile(selected));
  renderPicker();
  const legacyName = localStorage.getItem("ep:name");
  const legacyProfile = picker.options.length === 1 && legacyName ? createProfile(legacyName) : null;
  if (legacyProfile) localStorage.removeItem("ep:name");
  picker.onchange = () => {
    selectProfile(getProfile(picker.value));
    $("#home-error").textContent = "";
    if (!activeProfile) nameInput.focus();
  };
  window.addEventListener("storage", ({ key }) => {
    if (!key || key.startsWith(PROFILE_PREFIX)) renderPicker();
    if (!key || key.startsWith(CREDIT_PREFIX)) renderProgress();
  });
  return legacyProfile;
}

export function currentProfile() {
  return activeProfile;
}

export function saveProfile() {
  const name = nameInput.value.trim();
  return activeProfile ?? (name ? createProfile(name) : null);
}

export function approvedWordsKey(profile) {
  return `${LEGACY_WORDS_KEY}:${profile.id}`;
}

export function moveProgress(screen) {
  switch (screen) {
    case "game": $("#signing-progress").append(panel); break;
    case "practice": $("#practice-title").after(panel); break;
    case "lobby": $(".lobby-top").after(panel); break;
    default: $("#profile-picker").append(panel);
  }
}

export function practiceSummary(points) {
  const percent = Math.min(100, points * 100 / PRACTICE_TARGET_POINTS);
  const level = percent < 20 ? "Beginner" : percent < 40 ? "Developing"
    : percent < 60 ? "Practiced" : percent < 80 ? "Skilled" : "Accomplished";
  return { percent, label: `${Math.floor(percent)}% · ${level}` };
}

function creditPrefix(profile) {
  return `${CREDIT_PREFIX}${profile.id}:`;
}

function renderProgress() {
  panel.classList.toggle("hidden", !activeProfile);
  if (!activeProfile) return;
  const points = Object.keys(localStorage).filter((key) => key.startsWith(creditPrefix(activeProfile))).length;
  const { percent, label } = practiceSummary(points);
  $("#practice-progress-bar").value = percent;
  const text = $("#practice-progress-text");
  if (text.textContent !== label) text.textContent = label;
}

export function savePracticeCredits(profile, credits) {
  const saved = [];
  for (const credit of credits) {
    try {
      // Independent keys let two tabs save different clues, and replaying a clue writes the same key.
      localStorage.setItem(creditPrefix(profile) + credit, "1");
      saved.push(credit);
    } catch {
      break;
    }
  }
  if (saved.length && profile.id === activeProfile?.id) renderProgress();
  return saved;
}
