import { type DxSegment, DxSegmentType } from "@planarally/dice/systems/dx";
import { ref, watch } from "vue";

import { diceState } from "./state";

import { diceSystem } from ".";

const addOptions = ["d4", "d6", "d8", "d10", "d12", "d20", "d100"] as const;
const symbolOptions = ["+", "-"] as const; // , "*", "/", "(", ")"] as const;

const parts = ref<DxSegment[]>([]);

watch(
    () => diceState.reactive.textInput,
    (text) => {
        parts.value = diceState.raw.systems!["2d"].parse(text);
    },
);

// We don't want to do this on every change, as that can remove pending text changes
// which will update parts using the watcher above
function syncToState(): void {
    diceSystem.setInput(stringifySegments());
}

function addSegment(segment: DxSegment): void {
    if (parts.value.length > 0 && parts.value.at(-1)?.type !== DxSegmentType.Operator) {
        parts.value.push({ type: DxSegmentType.Operator, input: "+" });
    }
    parts.value.push(segment);
    syncToState();
}

function addDie(die: (typeof addOptions)[number]): void {
    const seg = parts.value.at(-1);
    if (seg?.type === DxSegmentType.Die && seg.die === die) {
        seg.amount += 1;
        seg.input = `${seg.amount}${die}`;
    } else if (seg?.type === DxSegmentType.Literal) {
        parts.value.pop();
        addSegment({
            type: DxSegmentType.Die,
            amount: seg.value,
            die,
            input: `${seg.value}${die}`,
        });
    } else {
        addSegment({ type: DxSegmentType.Die, amount: 1, die, input: `1${die}` });
    }
    syncToState();
}

function addLiteral(value: number): void {
    const seg = parts.value.at(-1);
    if (seg?.type === DxSegmentType.Die && seg.operator !== undefined) {
        if (seg.selectorValue === undefined) seg.selectorValue = value;
        else seg.selectorValue = seg.selectorValue * 10 + value;
    } else if (seg?.type === DxSegmentType.Literal) {
        seg.value = seg.value * 10 + value;
    } else {
        addSegment({ type: DxSegmentType.Literal, input: value.toString(), value });
    }
    syncToState();
}

function addOperator(input: (typeof symbolOptions)[number]): void {
    addSegment({ type: DxSegmentType.Operator, input });
    syncToState();
}

export type RollBias = "normal" | "advantage" | "disadvantage";

// Advantage and disadvantage are just `2d20kh1` / `2d20kl1`, which this builder
// could already express -- but only by opening Advanced, clicking "keep", then
// "highest", then typing 1. Six steps, and nothing anywhere says the words
// "advantage" or "disadvantage". They're the two most common modifiers in 5e,
// so they get a control of their own.

function findD20(): DxSegment | undefined {
    return parts.value.find((seg) => seg.type === DxSegmentType.Die && seg.die === "d20");
}

export function getRollBias(): RollBias {
    const seg = findD20();
    if (seg === undefined || seg.type !== DxSegmentType.Die) return "normal";
    // Only the exact 2-keep-1 shape counts. Someone who hand-built `4d20kh2`
    // meant something else, and silently calling that "advantage" would be a
    // lie the UI then acts on.
    if (seg.amount !== 2 || seg.operator !== "keep" || seg.selectorValue !== 1) return "normal";
    if (seg.selector === "highest") return "advantage";
    if (seg.selector === "lowest") return "disadvantage";
    return "normal";
}

export function setRollBias(bias: RollBias): void {
    let seg = findD20();
    if (seg === undefined) {
        // Asking for advantage with no d20 in the expression is a clear enough
        // request; add one rather than doing nothing.
        addDie("d20");
        seg = findD20();
        if (seg === undefined) return;
    }
    if (seg.type !== DxSegmentType.Die) return;

    if (bias === "normal") {
        seg.amount = 1;
        seg.operator = undefined;
        seg.selector = undefined;
        seg.selectorValue = undefined;
    } else {
        seg.amount = 2;
        seg.operator = "keep";
        seg.selector = bias === "advantage" ? "highest" : "lowest";
        seg.selectorValue = 1;
    }
    seg.input = `${seg.amount}${seg.die}`;
    syncToState();
}

function stringifySegments(): string {
    let text = "";
    for (const seg of parts.value) {
        if (seg.type === DxSegmentType.Die) {
            text += `${seg.amount}${seg.die}`;
            if (seg.operator === "keep") text += "k";
            else if (seg.operator === "drop") text += "p";
            else if (seg.operator === "explode") text += "e";
            else if (seg.operator === "min") text += "mi";
            else if (seg.operator === "max") text += "ma";
            else if (seg.operator === "inf") text += "rr";
            else if (seg.operator === "add") text += "ra";
            else if (seg.operator === "once") text += "ro";

            if (seg.selector === "highest") text += "h";
            else if (seg.selector === "lowest") text += "l";
            else if (seg.selector !== undefined) text += seg.selector;
            if (seg.selectorValue !== undefined) text += seg.selectorValue;
        }
        if (seg.type === DxSegmentType.Operator) text += ` ${seg.input} `;
        if (seg.type === DxSegmentType.Literal) text += seg.value;
    }
    return text;
}

export const DxHelper = {
    addDie,
    addLiteral,
    addOperator,
    getRollBias,
    setRollBias,
    parts,
};
