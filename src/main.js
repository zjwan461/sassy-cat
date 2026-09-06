import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'
import Dashboard from './views/Dashboard.vue'
import Logs from './views/Logs.vue'
import About from './views/About.vue'
import ChatView from './views/ChatView.vue'
import Settings from './views/Settings.vue'
import './styles.css'

const routes = [
  { path: '/', component: Dashboard },
  { path: '/chat', component: ChatView },
  { path: '/logs', component: Logs },
  { path: '/settings', component: Settings },
  { path: '/about', component: About }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

const app = createApp(App)
app.use(router)
app.mount('#app')
