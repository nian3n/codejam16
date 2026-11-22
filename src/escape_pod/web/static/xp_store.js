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

/** Sign XP from the saved credits plus every saved round. Old credits count, so no player starts at zero. */
export function totalXp(storage, profileId) {
  const credits = `${CREDIT_PREFIX}${profileId}:`;
  const rounds = `${ROUND_XP_PREFIX}${profileId}:`;
  let xp = 0;
  for (const key of keys(storage)) {
    if (key.startsWith(credits)) xp += SIGN_XP;
    else if (key.startsWith(rounds)) xp += Math.max(0, Number(storage.getItem(key)) || 0);
  }
  return xp;
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
export function saveRoundXp(storage, profileId, round) {
  const after = totalXp(storage, profileId);
  const key = `${ROUND_XP_PREFIX}${profileId}:${round.round_id}`;
  const value = Math.max(0, round.total - round.signs_xp);
  if (storage.getItem(key) !== null) return { before: after - value, after, saved: false };
  try {
    storage.setItem(key, String(value));
  } catch {
    return { before: after, after, saved: false };
  }
  return { before: after, after: after + value, saved: true };
}
