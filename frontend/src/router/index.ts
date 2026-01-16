import { createRouter, createWebHistory } from "vue-router";
import ChatPage from "../views/ChatPage.vue";
import CasePage from "../views/CasePage.vue";
import SettingsPage from "../views/SettingsPage.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/chat" },
    { path: "/chat", component: ChatPage },
    { path: "/case", component: CasePage },
    { path: "/settings", component: SettingsPage },
  ],
});

export default router;
