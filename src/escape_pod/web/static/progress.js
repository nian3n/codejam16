// Owner: Teammate 1 (Game, scenes, widgets)
import { $, el } from "./core.js";
import { levelFor } from "./xp_levels.js";
import * as xpStore from "./xp_store.js";

const PROFILE_PREFIX = "ep:profile:";
const SELECTED_PROFILE_KEY = "ep:selected-profile";
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
    if (!key || xpStore.isXpKey(key)) renderProgress();
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

/** This profile's XP total (xp_store.js). */
export function totalXp(profile) {
  return xpStore.totalXp(localStorage, profile.id);
}

export function saveRoundXp(profile, round) {
  const result = xpStore.saveRoundXp(localStorage, profile.id, round);
  if (result.saved && profile.id === activeProfile?.id) renderProgress();
  return result;
}

function renderProgress() {
  panel.classList.toggle("hidden", !activeProfile);
  if (!activeProfile) return;
  const { level, title, into, need } = levelFor(totalXp(activeProfile));
  const label = `Level ${level} · ${title} · ${into} / ${need} XP`;
  $("#practice-progress-bar").max = need;
  $("#practice-progress-bar").value = into;
  const text = $("#practice-progress-text");
  if (text.textContent !== label) text.textContent = label;
}

export function savePracticeCredits(profile, credits) {
  const saved = xpStore.saveCredits(localStorage, profile.id, credits);
  if (saved.length && profile.id === activeProfile?.id) renderProgress();
  return saved;
}
