// Owner: Teammate 1 (Game, scenes, widgets)
// Levels from an XP total (spec 2026-11-21-xp-levels-design). No DOM here, so Node can
// test it (tests/test_xp_levels.py). The XP values themselves come from the server (web/xp.py).

export const SIGN_XP = 5;  // web/xp.py SIGN_XP: each saved practice credit

/** XP needed to go from `level` to the next one: 250, 350, 450, ... with no cap. */
export function xpForNext(level) {
  return 250 + 100 * (level - 1);
}

export function titleFor(level) {
  return level <= 2 ? "Beginner" : level <= 4 ? "Developing" : level <= 6 ? "Practiced"
    : level <= 9 ? "Skilled" : "Accomplished";
}

/** The level for a total, with the XP inside it (`into`) and the size of the level (`need`). */
export function levelFor(xp) {
  let level = 1;
  let into = Math.max(0, Math.floor(xp));
  while (into >= xpForNext(level)) {
    into -= xpForNext(level);
    level += 1;
  }
  return { level, title: titleFor(level), into, need: xpForNext(level) };
}
