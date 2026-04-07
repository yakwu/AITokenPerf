import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'

import './styles/variables.css'
import './styles/base.css'
import './styles/components.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')

// Floating tooltip (position: fixed)
const tooltipEl = document.createElement('div')
tooltipEl.id = 'tooltip-float'
document.body.appendChild(tooltipEl)

document.addEventListener('mouseover', (e) => {
  const tip = e.target.closest('.info-tip')
  if (!tip || !tip.dataset.tip) return
  tooltipEl.textContent = tip.dataset.tip
  tooltipEl.style.display = 'block'
  const rect = tip.getBoundingClientRect()
  const left = Math.min(Math.max(8, rect.left), window.innerWidth - tooltipEl.offsetWidth - 8)
  tooltipEl.style.left = left + 'px'
  tooltipEl.style.top = (rect.top - tooltipEl.offsetHeight - 8) + 'px'
})

document.addEventListener('mouseout', (e) => {
  if (e.target.closest('.info-tip')) tooltipEl.style.display = 'none'
})
