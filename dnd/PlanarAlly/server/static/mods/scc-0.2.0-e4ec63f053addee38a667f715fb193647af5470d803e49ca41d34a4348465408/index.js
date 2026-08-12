import { ref, watch, defineComponent, computed, onMounted, resolveComponent, createElementBlock, openBlock, createElementVNode, createVNode, Fragment, renderList, unref, withDirectives, createCommentVNode, toDisplayString, vModelText, vModelCheckbox, vModelSelect, normalizeClass } from "vue";
const BLOCK_NAME = "presets";
let block;
let pending;
const library = ref({});
const presetLibrary = library;
function ensurePresets() {
  pending ?? (pending = load());
  return pending;
}
async function load() {
  const dataBlock = await api.getOrLoadDataBlock(
    { category: "room", name: BLOCK_NAME },
    { defaultData: () => ({}) }
  );
  if (dataBlock !== void 0) {
    block = dataBlock;
    library.value = dataBlock.reactiveData.value;
    watch(dataBlock.reactiveData, (value) => {
      library.value = value;
    });
  }
  return dataBlock;
}
function detach(stats) {
  return JSON.parse(JSON.stringify(stats));
}
function getPreset(name) {
  const stats = library.value[name];
  return stats === void 0 ? void 0 : detach(stats);
}
async function savePreset(name, stats) {
  const dataBlock = block ?? await ensurePresets();
  if (dataBlock === void 0) return false;
  dataBlock.reactiveData.value[name] = detach(stats);
  dataBlock.sync();
  return true;
}
async function deletePreset(name) {
  const dataBlock = block ?? await ensurePresets();
  if (dataBlock === void 0 || !(name in dataBlock.reactiveData.value)) return false;
  delete dataBlock.reactiveData.value[name];
  dataBlock.sync();
  return true;
}
const _hoisted_1 = { id: "scc" };
const _hoisted_2 = ["for"];
const _hoisted_3 = ["id", "onUpdate:modelValue"];
const _hoisted_4 = ["id", "onUpdate:modelValue"];
const _hoisted_5 = ["id", "onUpdate:modelValue"];
const _hoisted_6 = { class: "row" };
const _hoisted_7 = ["value"];
const _sfc_main = /* @__PURE__ */ defineComponent({
  __name: "CharTab",
  setup(__props) {
    const { data, load: load2, save, write } = api.useShapeDataBlock(
      // The first argument is the name of the data block
      // data is a super generic name, but you can choose anything here
      "data",
      // The second argument contains the regular data block options, but defaultData is mandatory as we need it to init the data to something sensible.
      { defaultData: () => [] }
    );
    watch(
      () => api.systemsState.characters.reactive.activeCharacterId,
      async (charId) => {
        if (charId !== void 0) {
          const shapeId = api.systems.characters.getShapeId(charId);
          if (shapeId) load2(shapeId);
        }
      },
      // We need to set the `immediate` flag, as the code in this component is only executed once the component is loaded.
      // A watcher is lazy by default, which means that the above code will only execute once the watch condition changes
      // In which case we would miss the case where we just mounted the component with a character already selected.
      // We could handle this with a separate `onMounted`, but we're just duplicating code at that point, so `immediate` it is!
      { immediate: true }
    );
    const options = ["Text", "Number", "Checkbox"];
    const selectedOption = ref(options[0]);
    const selectedName = ref("");
    function addOption() {
      const name = selectedName.value;
      if (name.length === 0 || data.value.some((s) => s.name === name)) return;
      let stat;
      if (selectedOption.value === "Checkbox") {
        stat = {
          name,
          type: "check",
          value: false
        };
      } else if (selectedOption.value === "Number") {
        stat = { name, type: "number", value: 0 };
      } else {
        stat = { name, type: "string", value: "" };
      }
      data.value.push(stat);
      save();
    }
    function removeOption(name) {
      write(data.value.filter((s) => s.name !== name));
      save();
    }
    const selectedPreset = ref("");
    const presetName = ref("");
    const presetNames = computed(() => Object.keys(presetLibrary.value).sort());
    onMounted(() => void ensurePresets());
    function applyPreset() {
      const stats = getPreset(selectedPreset.value);
      if (stats === void 0) return;
      write(stats);
      save();
    }
    async function storePreset() {
      const name = presetName.value.trim();
      if (name.length === 0) return;
      if (await savePreset(name, data.value)) {
        selectedPreset.value = name;
        presetName.value = "";
      }
    }
    async function removePreset() {
      if (await deletePreset(selectedPreset.value)) selectedPreset.value = "";
    }
    return (_ctx, _cache) => {
      const _component_font_awesome_icon = resolveComponent("font-awesome-icon");
      return openBlock(), createElementBlock("div", _hoisted_1, [
        (openBlock(true), createElementBlock(Fragment, null, renderList(unref(data), (stat) => {
          return openBlock(), createElementBlock(Fragment, {
            key: stat.name
          }, [
            createElementVNode("label", {
              for: "#scc-" + stat.name
            }, toDisplayString(stat.name), 9, _hoisted_2),
            stat.type === "string" ? withDirectives((openBlock(), createElementBlock("input", {
              key: 0,
              id: "#scc-" + stat.name,
              type: "text",
              "onUpdate:modelValue": ($event) => stat.value = $event,
              onChange: _cache[0] || (_cache[0] = //@ts-ignore
              (...args) => unref(save) && unref(save)(...args))
            }, null, 40, _hoisted_3)), [
              [vModelText, stat.value]
            ]) : createCommentVNode("", true),
            stat.type === "number" ? withDirectives((openBlock(), createElementBlock("input", {
              key: 1,
              id: "#scc-" + stat.name,
              type: "number",
              "onUpdate:modelValue": ($event) => stat.value = $event,
              onChange: _cache[1] || (_cache[1] = //@ts-ignore
              (...args) => unref(save) && unref(save)(...args))
            }, null, 40, _hoisted_4)), [
              [vModelText, stat.value]
            ]) : createCommentVNode("", true),
            stat.type === "check" ? withDirectives((openBlock(), createElementBlock("input", {
              key: 2,
              id: "#scc-" + stat.name,
              type: "checkbox",
              "onUpdate:modelValue": ($event) => stat.value = $event,
              onChange: _cache[2] || (_cache[2] = //@ts-ignore
              (...args) => unref(save) && unref(save)(...args))
            }, null, 40, _hoisted_5)), [
              [vModelCheckbox, stat.value]
            ]) : createCommentVNode("", true),
            createVNode(_component_font_awesome_icon, {
              icon: "trash-alt",
              onClick: ($event) => removeOption(stat.name)
            }, null, 8, ["onClick"])
          ], 64);
        }), 128)),
        _cache[8] || (_cache[8] = createElementVNode("div", { id: "gap" }, null, -1)),
        _cache[9] || (_cache[9] = createElementVNode("div", null, "Add new stat", -1)),
        createElementVNode("div", null, [
          withDirectives(createElementVNode("input", {
            "onUpdate:modelValue": _cache[3] || (_cache[3] = ($event) => selectedName.value = $event),
            type: "text",
            style: { "width": "5rem" },
            placeholder: "name"
          }, null, 512), [
            [vModelText, selectedName.value]
          ]),
          withDirectives(createElementVNode("select", {
            "onUpdate:modelValue": _cache[4] || (_cache[4] = ($event) => selectedOption.value = $event)
          }, [
            (openBlock(), createElementBlock(Fragment, null, renderList(options, (option) => {
              return createElementVNode("option", { key: option }, toDisplayString(option), 1);
            }), 64))
          ], 512), [
            [vModelSelect, selectedOption.value]
          ])
        ]),
        createVNode(_component_font_awesome_icon, {
          icon: "plus-square",
          onClick: addOption,
          disabled: selectedName.value.length === 0 || unref(data).some((s) => s.name === selectedName.value)
        }, null, 8, ["disabled"]),
        _cache[10] || (_cache[10] = createElementVNode("div", { id: "gap" }, null, -1)),
        _cache[11] || (_cache[11] = createElementVNode("div", null, "Preset", -1)),
        createElementVNode("div", _hoisted_6, [
          withDirectives(createElementVNode("select", {
            "onUpdate:modelValue": _cache[5] || (_cache[5] = ($event) => selectedPreset.value = $event),
            style: { "width": "5rem" }
          }, [
            _cache[7] || (_cache[7] = createElementVNode("option", { value: "" }, "-", -1)),
            (openBlock(true), createElementBlock(Fragment, null, renderList(presetNames.value, (name) => {
              return openBlock(), createElementBlock("option", {
                key: name,
                value: name
              }, toDisplayString(name), 9, _hoisted_7);
            }), 128))
          ], 512), [
            [vModelSelect, selectedPreset.value]
          ]),
          createVNode(_component_font_awesome_icon, {
            icon: "download",
            title: "Replace this sheet with the preset",
            class: normalizeClass({ disabled: selectedPreset.value.length === 0 }),
            onClick: applyPreset
          }, null, 8, ["class"]),
          createVNode(_component_font_awesome_icon, {
            icon: "trash-alt",
            title: "Delete this preset",
            class: normalizeClass({ disabled: selectedPreset.value.length === 0 }),
            onClick: removePreset
          }, null, 8, ["class"])
        ]),
        _cache[12] || (_cache[12] = createElementVNode("div", null, null, -1)),
        _cache[13] || (_cache[13] = createElementVNode("div", null, "Save as", -1)),
        createElementVNode("div", null, [
          withDirectives(createElementVNode("input", {
            "onUpdate:modelValue": _cache[6] || (_cache[6] = ($event) => presetName.value = $event),
            type: "text",
            style: { "width": "5rem" },
            placeholder: "preset name"
          }, null, 512), [
            [vModelText, presetName.value]
          ])
        ]),
        createVNode(_component_font_awesome_icon, {
          icon: "floppy-disk",
          title: "Save this sheet as a preset for the whole campaign",
          class: normalizeClass({ disabled: presetName.value.trim().length === 0 }),
          onClick: storePreset
        }, null, 8, ["class"])
      ]);
    };
  }
});
const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};
const CharTab = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-0d950e0c"]]);
let api;
async function init(meta) {
  console.log(`Loading ${meta.name} v${meta.version}`);
}
async function initGame(gameApi) {
  api = gameApi;
  api.ui.shape.registerTab(
    { component: CharTab, id: "SCS", label: "Char Sheet" },
    (shape) => {
      var _a;
      return ((_a = api.getShape(shape)) == null ? void 0 : _a.character) !== void 0;
    }
  );
}
async function loadLocation() {
}
const events = {
  init,
  initGame,
  loadLocation
};
export {
  api,
  events
};
