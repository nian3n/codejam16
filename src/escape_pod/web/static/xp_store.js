// Owner: Teammate 1 (Game, scenes, widgets)
// The XP total in the browser profile (spec 2026-11-21-xp-levels-design). `storage` is
// localStorage in the page, and a fake in tests/test_xp_levels.py: no DOM here.
import { SIGN_XP } from "./xp_levels.js";

const CREDIT_PREFIX = "ep:practice-credit:";
// One key per finished round: its XP minus the sign part, which the credits already count.
const ROUND_XP_PREFIX = "ep:round-xp:";

export const isXpKey = (key) => key.startsWith(CREDIT_PREFIX) || key.startsWith(ROUND_XP_PREFIX);

/** A solo-practice credit is keyed by the word, so approving CAT again gives no more XP. */
export const practiceCredit = (gloss) => `practice:${gloss}`;

function keys(storage) {
  const out = [];
  for (let i = 0; i < storage.length; i++) out.push(storage.key(i));
  return out;
}

/** A saved round: JSON {xp, signs, won, at}, or a bare number from before the history (no time). */
function readRound(raw) {
  if (raw === null) return null;
  const n = Number(raw);
  if (raw.trim() !== "" && Number.isFinite(n)) return { xp: Math.max(0, n), signs: 0, won: false, at: null };
  try {
    const r = JSON.parse(raw);
    const xp = Math.max(0, Number(r.xp) || 0);
    return { xp, signs: Math.max(0, Number(r.signs) || 0), won: !!r.won, at: Number.isFinite(r.at) ? r.at : null };
  } catch {
    return { xp: 0, signs: 0, won: false, at: null };  // a damaged value counts as nothing
  }
}

function savedRounds(storage, profileId) {
  const prefix = `${ROUND_XP_PREFIX}${profileId}:`;
  return keys(storage).filter((key) => key.startsWith(prefix)).map((key) => readRound(storage.getItem(key)));
}

/** Sign XP from the saved credits plus every saved round. Old credits count, so no player starts at zero. */
export function totalXp(storage, profileId) {
  const credits = `${CREDIT_PREFIX}${profileId}:`;
  const signs = keys(storage).filter((key) => key.startsWith(credits)).length * SIGN_XP;
  return signs + savedRounds(storage, profileId).reduce((sum, r) => sum + r.xp, 0);
}

/**
 * The XP total over time: a start point ("earlier progress": rounds without a time, practice
 * credits, rounds past the limit) plus one point per timed round, oldest first. The last point
 * is the current total. A round's gain includes its signs, whose credits are saved separately.
 */
export function history(storage, profileId, limit = 30) {
  const timed = savedRounds(storage, profileId).filter((r) => r.at !== null).sort((a, b) => a.at - b.at).slice(-limit);
  const total = totalXp(storage, profileId);
  let running = Math.max(0, total - timed.reduce((sum, r) => sum + r.xp + r.signs, 0));
  const start = running;
  const rounds = timed.map((r) => {
    running += r.xp + r.signs;
    return { at: r.at, gain: r.xp + r.signs, total: running, won: r.won };
  });
  return { start, rounds };
}

/** Saves credits. Each is its own key, so two tabs never clash, and a replayed credit writes the same key. */
export function saveCredits(storage, profileId, credits) {
  const saved = [];
  for (const credit of credits) {
    try {
      storage.setItem(`${CREDIT_PREFIX}${profileId}:${credit}`, "1");
      saved.push(credit);
    } catch {
      break;
    }
  }
  return saved;
}

/** Saves one round's XP (state.round_xp) once. A reload sends the same round again: same key, no change. */
export function saveRoundXp(storage, profileId, round, now = Date.now()) {
  const after = totalXp(storage, profileId);
  const key = `${ROUND_XP_PREFIX}${profileId}:${round.round_id}`;
  const value = Math.max(0, round.total - round.signs_xp);
  if (storage.getItem(key) !== null) return { before: after - value, after, saved: false };
  const won = (round.parts ?? []).some((p) => p.label === "Bomb defused");
  try {
    storage.setItem(key, JSON.stringify({ xp: value, signs: Math.max(0, round.signs_xp), won, at: now }));
  } catch {
    return { before: after, after, saved: false };
  }
  return { before: after, after: after + value, saved: true };
}
