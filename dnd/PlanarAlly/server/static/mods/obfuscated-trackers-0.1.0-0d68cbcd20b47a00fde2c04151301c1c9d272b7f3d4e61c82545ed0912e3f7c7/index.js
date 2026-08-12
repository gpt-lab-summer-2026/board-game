import { defineComponent as _, watch as x, computed as O, createElementBlock as f, openBlock as m, createElementVNode as i, createCommentVNode as w, Fragment as g, renderList as D, toDisplayString as C } from "vue";
const k = {
  serialize: (s) => [...s.entries()],
  deserialize: (s) => new Map(s)
};
function y(s) {
  return { category: "shape", shape: s, name: "obfuscated-trackers" };
}
function M(s) {
  const l = o.getGlobalId(s);
  if (l !== void 0)
    return o.getDataBlock(y(l));
}
const S = { id: "obfuscated-tracker-settings" }, B = ["checked", "onChange"], T = ["value", "disabled", "onChange"], N = ["value", "disabled", "onChange"], z = ["value", "disabled", "onChange"], E = { key: 0 }, I = /* @__PURE__ */ _({
  __name: "TrackerSettings",
  setup(s) {
    const { data: l, load: u } = o.useShapeDataBlock("obfuscated-trackers", {
      defaultData: () => /* @__PURE__ */ new Map(),
      serializer: k
    });
    let d;
    x(
      () => o.systemsState.selected.reactive.focus,
      async (e) => {
        d = e, e && u(e);
      },
      { immediate: !0 }
    );
    const c = O(() => o.systems.trackers.state.trackers.filter((e) => !e.temporary).map((e) => ({
      uuid: e.uuid,
      name: e.name,
      value: e.value,
      maxValue: e.maxvalue ?? e.value,
      ...l.value.get(e.uuid)
    })));
    function r(e, t, a) {
      const n = {
        useObfuscation: !0,
        realValue: t,
        parts: 4,
        realMaxValue: a
      };
      return l.value.set(e, n), n;
    }
    function p(e, t) {
      const a = c.value.find((V) => V.uuid === e);
      if (a === void 0)
        throw new Error(`Tracker ${e} not found during obfuscation.`);
      let n, b = { value: a.value, maxvalue: a.maxValue };
      if (a.useObfuscation === void 0)
        if (t)
          n = r(e, a.value, a.maxValue);
        else
          return;
      else {
        if (n = l.value.get(e), n === void 0)
          throw new Error(`Tracker ${e} not found during obfuscation.`);
        n.useObfuscation = t, t || (b = { value: n.realValue, maxvalue: n.realMaxValue });
      }
      v(e, b);
    }
    function v(e, t) {
      !d || t.value === void 0 && t.maxvalue === void 0 || o.systems.trackers.update(d, e, t, { server: !0, ui: !0 });
    }
    async function h(e, t) {
      t < 2 && (t = 2);
      const a = l.value.get(e);
      a !== void 0 && (a.parts = t, v(e, { value: a.realValue }));
    }
    return (e, t) => (m(), f("div", S, [
      t[0] || (t[0] = i("div", null, "Name", -1)),
      t[1] || (t[1] = i("div", null, "Obf. enabled", -1)),
      t[2] || (t[2] = i("div", null, "Real Value", -1)),
      t[3] || (t[3] = i("div", null, "Real Max Value", -1)),
      t[4] || (t[4] = i("div", null, "# Segments", -1)),
      (m(!0), f(g, null, D(c.value, (a) => (m(), f(g, {
        key: a.uuid
      }, [
        i("label", null, C(a.name), 1),
        i("input", {
          type: "checkbox",
          checked: a.useObfuscation,
          onChange: (n) => p(a.uuid, n.target.checked)
        }, null, 40, B),
        i("input", {
          type: "number",
          value: a.realValue,
          disabled: !a.useObfuscation,
          onChange: (n) => v(a.uuid, {
            value: n.target.valueAsNumber
          })
        }, null, 40, T),
        i("input", {
          type: "number",
          value: a.realMaxValue,
          disabled: !a.useObfuscation,
          onChange: (n) => v(a.uuid, {
            maxvalue: n.target.valueAsNumber
          })
        }, null, 40, N),
        i("input", {
          type: "number",
          min: "2",
          value: a.parts,
          disabled: !a.useObfuscation,
          onChange: (n) => h(a.uuid, n.target.valueAsNumber)
        }, null, 40, z)
      ], 64))), 128)),
      c.value.length === 0 ? (m(), f("p", E, "First make a tracker in the trackers tab!")) : w("", !0)
    ]));
  }
}), A = (s, l) => {
  const u = s.__vccOpts || s;
  for (const [d, c] of l)
    u[d] = c;
  return u;
}, G = /* @__PURE__ */ A(I, [["__scopeId", "data-v-7f8371bc"]]);
function R(s, l, u, d) {
  if (d.server && (u.value !== void 0 || u.maxvalue !== void 0)) {
    const c = M(s);
    if (c) {
      const r = c.data.get(l.uuid);
      if (r != null && r.useObfuscation) {
        u.value !== void 0 && (r.realValue = u.value), u.maxvalue !== void 0 && (r.realMaxValue = u.maxvalue), c.sync();
        const p = r.realMaxValue / r.parts;
        u.value = Math.ceil(r.realValue / p), u.maxvalue = r.parts;
      }
    }
  }
  return u;
}
let o;
async function F(s) {
  o = s, o.ui.shape.registerTab(
    {
      id: "obfuscated-trackers",
      label: "Obfuscated",
      component: G
    },
    // We only want to show the tab if the user has edit access to the shape
    (l, u) => u
  ), x(
    () => o.systemsState.selected.reactive.focus,
    async (l) => {
      if (l) {
        const u = o.getGlobalId(l);
        if (u === void 0) return;
        await o.getOrLoadDataBlock(y(u), {
          defaultData: () => /* @__PURE__ */ new Map(),
          serializer: k
        });
      }
    }
  );
}
const $ = {
  initGame: F,
  preTrackerUpdate: R
};
export {
  o as api,
  $ as events
};
