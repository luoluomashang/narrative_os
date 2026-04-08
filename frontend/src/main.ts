import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import './styles/global.css'
import './styles/element-overrides.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
// JS-invoked Element Plus services need explicit CSS imports (auto-import can't detect them)
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import App from './App.vue'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')

