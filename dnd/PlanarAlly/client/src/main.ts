import "../style.css";
// Design tokens and the global focus ring. Imported after style.css so it can
// override the vendored directory-listing stylesheet that lives there.
import "./styles/tokens.css";
import "./styles/modals.css";
import { FontAwesomeIcon } from "@fortawesome/vue-fontawesome";
import { createApp } from "vue";
import Toast, { POSITION } from "vue-toastification";
import type { PluginOptions } from "vue-toastification";

// eslint-disable-next-line import/default
import App from "./App.vue";
import { PlanarAllyModalsPlugin } from "./core/plugins/modals/plugin";
import { loadFontAwesome } from "./fa";
import { i18n } from "./i18n";
import { router } from "./router";
import { bootstrapRouter } from "./router/bootstrap";

bootstrapRouter();

loadFontAwesome();

const toastOptions: PluginOptions = {
    position: POSITION.BOTTOM_RIGHT,
    shareAppContext: true,
};

const app = createApp(App);
app.use(router)
    .use(i18n)
    .use(Toast, toastOptions)
    .use(PlanarAllyModalsPlugin)
    .component("font-awesome-icon", FontAwesomeIcon)
    .mount("body");
