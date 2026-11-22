// Owner: Teammate 1 (Game, scenes, widgets)
// Widget registry. Each widget is render(module, index, ctx) -> DOM node, where
// ctx = { sendAct(index, verb, target), rerender() }. The names match the
// "widget" field in puzzles/data/*.json and the widget classes in puzzles/engine.py.
import { wires } from "./wires.js";
import { keypad } from "./keypad.js";
import { icons } from "./icons.js";
import { dial } from "./dial.js";
import { switches } from "./switches.js";
import { big_button } from "./big_button.js";
import { sorter } from "./sorter.js";

export const WIDGETS = { wires, keypad, icons, dial, switches, big_button, sorter };
