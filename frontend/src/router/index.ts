import { createRouter, createWebHistory } from "vue-router";
import HomePage from "../views/HomePage.vue";
import ChatPage from "../views/ChatPage.vue";
import CasePage from "../views/CasePage.vue";
import SettingsPage from "../views/SettingsPage.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: HomePage },
    { path: "/chat", component: ChatPage },
    { path: "/case", component: CasePage },
    { path: "/settings", component: SettingsPage },
  ],
});

export default router;
