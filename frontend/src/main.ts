import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import './styles/global.css'
import './styles/element-overrides.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import App from './App.vue'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')

