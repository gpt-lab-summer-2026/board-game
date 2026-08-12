import tinycolor from "tinycolor2";
import { reactive, watch } from "vue";

import { g2l, getUnitDistance, l2g, toRadians } from "../../../core/conversions";
import { toGP, toLP } from "../../../core/geometry";
import type { LocalPoint } from "../../../core/geometry";
import { DEFAULT_HEX_RADIUS, GridType } from "../../../core/grid";
import { InvalidationMode, NO_SYNC, SyncMode, UI_SYNC } from "../../../core/models/types";
import { i18n } from "../../../i18n";
import { sendShapePositionUpdate } from "../../api/emits/shape/core";
import { getShape } from "../../id";
import type { IShape } from "../../interfaces/shape";
import type { ICircle } from "../../interfaces/shapes/circle";
import { ToolName } from "../../models/tools";
import type { ITool, ToolPermission } from "../../models/tools";
import { Circle } from "../../shapes/variants/circle";
import { createHexPolygon } from "../../shapes/variants/hex";
import { Rect } from "../../shapes/variants/rect";
import { accessSystem } from "../../systems/access";
import { floorState } from "../../systems/floors/state";
import { playerSystem } from "../../systems/players";
import { propertiesSystem } from "../../systems/properties";
import { selectedSystem } from "../../systems/selected";
import { selectedState } from "../../systems/selected/state";
import { locationSettingsState } from "../../systems/settings/location/state";
import { SelectFeatures } from "../models/select";
import { Tool } from "../tool";
import { activateTool, toolMap } from "../tools";
import { spellTargets, type SpellTarget } from "./spellTargets";
import { eventBus } from "../../../core/eventBus";

export enum SpellShape {
    Square = "square",
    // oxlint-disable-next-line no-shadow
    Circle = "circle",
    Cone = "cone",
    Hex = "hex",
    // A bolt: a long thin rectangle aimed from the caster, like 5e's
    // "100 foot line that is 5 feet wide".
    Line = "line",
}

class SpellTool extends Tool implements ITool {
    readonly toolName = ToolName.Spell;
    readonly toolTranslation = i18n.global.t("tool.Spell");

    shape?: IShape;

    /** Cone and Line both originate at a token rather than at the cursor. */
    get needsCaster(): boolean {
        return (
            this.state.selectedSpellShape === SpellShape.Cone ||
            this.state.selectedSpellShape === SpellShape.Line
        );
    }

    state = reactive({
        selectedSpellShape: SpellShape.Square,
        showPublic: true,
        oddHexOrientation: false,

        colour: "rgb(63, 127, 191)",
        size: 5,
        /** Condition id to inflict on everything caught, or "" for none. */
        condition: "",
        /** Restrict the effect to what the caster can actually see. */
        requireLineOfSight: true,
        /** Populated after a cast so the UI can report who was hit. */
        lastTargets: [] as SpellTarget[],
        // Width of a Line template, in the campaign's units. 5ft is the
        // standard bolt; the length comes from `size` like every other shape.
        lineWidth: 5,
    });

    get permittedTools(): ToolPermission[] {
        return [
            {
                name: ToolName.Select,
                features: { disabled: [SelectFeatures.Resize, SelectFeatures.Rotate] },
            },
        ];
    }

    constructor() {
        super();
        watch(
            () => this.state.size,
            async () => {
                if (this.shape !== undefined) await this.drawShape();
            },
        );
        watch(
            () => this.state.oddHexOrientation,
            async () => {
                if (this.shape !== undefined) await this.drawShape();
            },
        );
        watch(
            () => this.state.selectedSpellShape,
            async () => {
                if (selectedState.reactive.focus === undefined && this.state.selectedSpellShape === SpellShape.Cone) {
                    this.state.selectedSpellShape = SpellShape.Circle;
                }
                if (this.shape !== undefined) await this.drawShape();
            },
        );
        watch(
            () => this.state.colour,
            async () => {
                if (this.shape !== undefined) await this.drawShape();
            },
        );
        watch(
            () => this.state.showPublic,
            async () => {
                if (this.shape !== undefined) await this.drawShape(true);
            },
        );
    }

    async drawShape(syncChanged = false): Promise<void> {
        if (!selectedSystem.hasSelection && this.needsCaster) return;
        if (this.state.size <= 0) return;

        const layer = floorState.currentLayer.value!;

        const ogPoint = toGP(0, 0);
        let startPosition = ogPoint;
        let shapeCenter = ogPoint;

        if (this.shape !== undefined) {
            startPosition = this.shape.refPoint;
            shapeCenter = this.shape.center;
            const syncMode = this.state.showPublic !== syncChanged ? SyncMode.TEMP_SYNC : SyncMode.NO_SYNC;
            layer.removeShape(this.shape, { sync: syncMode, recalculate: false, dropShapeId: true });
        }

        switch (this.state.selectedSpellShape) {
            case SpellShape.Circle:
                this.shape = new Circle(startPosition, getUnitDistance(this.state.size), {
                    isSnappable: false,
                });
                break;
            case SpellShape.Square:
                {
                    this.shape = new Rect(
                        startPosition,
                        getUnitDistance(this.state.size),
                        getUnitDistance(this.state.size),
                        { isSnappable: false },
                    );
                }
                break;
            case SpellShape.Cone:
                this.shape = new Circle(startPosition, getUnitDistance(this.state.size), {
                    viewingAngle: toRadians(60),
                    isSnappable: false,
                });
                break;
            case SpellShape.Line:
                // Anchored on its left edge so it grows away from the caster;
                // onMove then rotates it to follow the cursor.
                this.shape = new Rect(
                    startPosition,
                    getUnitDistance(this.state.size),
                    getUnitDistance(this.state.lineWidth),
                    { isSnappable: false },
                );
                break;
            case SpellShape.Hex:
                {
                    const gridType = locationSettingsState.raw.gridType.value;
                    this.shape = createHexPolygon(
                        shapeCenter,
                        this.state.size,
                        {
                            type: gridType,
                            oddHexOrientation: this.state.oddHexOrientation,
                            radius: DEFAULT_HEX_RADIUS,
                        },
                        { isSnappable: false },
                    );
                }
                break;
        }

        const c = tinycolor(this.state.colour);
        c.setAlpha(c.getAlpha() * 0.7);
        propertiesSystem.setFillColour(this.shape.id, c.toRgbString(), NO_SYNC);
        propertiesSystem.setStrokeColour(this.shape.id, this.state.colour, NO_SYNC);

        accessSystem.addAccess(
            this.shape.id,
            playerSystem.getCurrentPlayer()!.name,
            { edit: true, movement: true, vision: false },
            UI_SYNC,
        );

        layer.addShape(
            this.shape,
            this.state.showPublic ? SyncMode.TEMP_SYNC : SyncMode.NO_SYNC,
            InvalidationMode.NORMAL,
        );

        if (this.needsCaster) {
            const selection = selectedState.raw.focus;
            if (selection === undefined) {
                console.error("SpellTool: No selection found.");
            } else {
                const selectionShape = getShape(selection);
                if (selectionShape === undefined) {
                    console.error("SpellTool: Selected shape does not exist.");
                } else {
                    this.shape.center = selectionShape.center;
                }
            }
        }

        await this.drawRangeShape();
    }

    async drawRangeShape(): Promise<void> {
        const focus = selectedState.raw.focus;

        if (focus === undefined || this.shape === undefined) return;

        const focusShape = getShape(focus);
        if (focusShape === undefined) return;

        const ruler = toolMap[ToolName.Ruler];
        await ruler.onDown(g2l(focusShape.center), undefined, {});
    }

    async onSelect(): Promise<void> {
        if (!selectedSystem.hasSelection && this.needsCaster) {
            this.state.selectedSpellShape = SpellShape.Circle;
        }
        // Only coerce where the choice is actually impossible: a hex-aligned
        // template means nothing on a square grid. The reverse was also being
        // forced -- every non-square grid was snapped to Hex on each select,
        // which is what made cone and circle unusable on a hex board.
        if (
            locationSettingsState.raw.gridType.value === GridType.Square &&
            this.state.selectedSpellShape === SpellShape.Hex
        ) {
            this.state.selectedSpellShape = SpellShape.Square;
        }
        await this.drawShape();
    }

    async onDeselect(): Promise<void> {
        await this.close({ dropShapeId: true, deselectTool: false });
    }

    async onDown(): Promise<void> {
        // Work out who is caught *before* the template is torn down.
        this.resolveTargets();
        await this.close({ dropShapeId: false, deselectTool: true });
    }

    /**
     * Announce who the template caught.
     *
     * The tool deliberately does not apply the condition itself: conditions
     * are the character sheet mod's concept, and duplicating its rules here
     * is how the two end up disagreeing. It publishes the event; whoever
     * owns conditions decides what a condition means.
     */
    private resolveTargets(): void {
        if (this.shape === undefined) return;

        const focus = selectedState.raw.focus;
        const caster = focus === undefined ? undefined : getShape(focus)?.center;
        const all = spellTargets(this.shape, this.state.requireLineOfSight ? caster : undefined);
        const caught = this.state.requireLineOfSight ? all.filter((t) => t.visible) : all;

        this.state.lastTargets = all;
        if (caught.length === 0) return;

        eventBus.emit("spell:cast", {
            shapes: caught.map((t) => t.id),
            condition: this.state.condition === "" ? undefined : this.state.condition,
        });
    }

    async onMove(lp: LocalPoint): Promise<void> {
        if (this.shape === undefined) return Promise.resolve();

        const endPoint = l2g(lp);
        const layer = floorState.currentLayer.value!;

        if (this.needsCaster) {
            const center = g2l(this.shape.center);
            const angle = -Math.atan2(lp.y - center.y, center.x - lp.x) + Math.PI;
            if (this.state.selectedSpellShape === SpellShape.Cone) {
                (this.shape as ICircle).angle = angle;
            } else {
                // A Rect rotates about its refPoint, which is the middle of
                // the edge nearest the caster -- so the bolt pivots around
                // the caster instead of swinging its far end through them.
                this.shape.angle = angle;
            }
            if (this.state.showPublic) sendShapePositionUpdate([this.shape], true);
            layer.invalidate(true);
        } else {
            this.shape.center = endPoint;
            if (this.state.showPublic) sendShapePositionUpdate([this.shape], true);

            const focus = selectedState.raw.focus;

            if (focus !== undefined) {
                const ruler = toolMap[ToolName.Ruler];
                await ruler.onMove(g2l(this.shape.center), undefined, {});
            }

            layer.invalidate(true);
        }
    }

    async onContextMenu(): Promise<boolean> {
        await this.close({ dropShapeId: true, deselectTool: true });
        return false;
    }

    async close(options: { dropShapeId: boolean; deselectTool: boolean }): Promise<void> {
        if (this.shape !== undefined) {
            const layer = floorState.currentLayer.value;
            if (layer === undefined) return;

            const { dropShapeId } = options;

            layer.removeShape(this.shape, {
                sync: this.state.showPublic ? SyncMode.TEMP_SYNC : SyncMode.NO_SYNC,
                recalculate: false,
                dropShapeId,
            });

            if (!dropShapeId) {
                propertiesSystem.setIsInvisible(this.shape.id, !this.state.showPublic, NO_SYNC);
                layer.addShape(this.shape, SyncMode.FULL_SYNC, InvalidationMode.NORMAL);
            }
            this.shape = undefined;

            const ruler = toolMap[ToolName.Ruler];
            await ruler.onUp(toLP(0, 0), undefined, {});
        }
        if (options.deselectTool) activateTool(ToolName.Select);
    }
}

export const spellTool = new SpellTool();
