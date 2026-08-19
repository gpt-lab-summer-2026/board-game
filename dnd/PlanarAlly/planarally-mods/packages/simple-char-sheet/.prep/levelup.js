// The right-click "Level up" entry.
//
// A mod's only UI surfaces are a shape tab and a shape context-menu entry, and
// levelling is exactly the kind of thing you want without opening a dialog:
// one click, on the token, mid-session.
//
// The catch is that a context-menu callback is synchronous and the sheet lives
// behind an async DataBlock load. So the entry reads whatever is already
// cached, shows the level it knows about, and does the load-modify-save in the
// background when clicked. Worst case on a never-opened sheet is one click that
// warms the cache and a second that levels -- which is why the label says so.
import { findClass } from "./catalogue.js";
import { SHEET_BLOCK } from "./data.js";
import { api } from "./main.js";
import { MAX_LEVEL, abilityMod } from "./rules.js";
function cachedSheet(shape) {
    const globalId = api.getGlobalId(shape);
    if (globalId === undefined)
        return undefined;
    return api.getDataBlock({
        category: "shape",
        shape: globalId,
        name: SHEET_BLOCK,
    })?.data;
}
async function applyLevelUp(shape) {
    const globalId = api.getGlobalId(shape);
    if (globalId === undefined)
        return false;
    const block = await api.getOrLoadDataBlock({
        category: "shape",
        shape: globalId,
        name: SHEET_BLOCK,
    });
    if (block === undefined)
        return false;
    const sheet = block.reactiveData.value;
    if (sheet.classId === null || sheet.level >= MAX_LEVEL)
        return false;
    sheet.level += 1;
    // Same hit point gain the sheet's own button applies -- levelling in two
    // places must not produce two different characters.
    const klass = findClass(sheet.classId);
    if (klass) {
        const gain = Math.max(1, Math.ceil(klass.hitDie / 2) + 1 + abilityMod(sheet.abilities.con));
        sheet.hp.max += gain;
        sheet.hp.current += gain;
    }
    block.sync();
    return true;
}
export function levelUpEntry(shape) {
    if (api.getShape(shape)?.character === undefined)
        return [];
    const sheet = cachedSheet(shape);
    const klass = sheet ? findClass(sheet.classId) : undefined;
    if (sheet === undefined) {
        return [
            {
                title: "Level up (open the Character tab first)",
                disabled: true,
                action: () => true,
            },
        ];
    }
    if (sheet.classId === null) {
        return [{ title: "Level up — pick a class first", disabled: true, action: () => true }];
    }
    if (sheet.level >= MAX_LEVEL) {
        return [
            {
                title: `Level ${sheet.level} ${klass?.name ?? ""} — max for this campaign`.trim(),
                disabled: true,
                action: () => true,
            },
        ];
    }
    const next = klass?.level2;
    return [
        {
            title: `▲ Level up to ${sheet.level + 1} ${klass?.name ?? ""}${next ? ` — ${next.name}` : ""}`,
            action: async () => applyLevelUp(shape),
        },
    ];
}
