import { config } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { afterEach, vi } from 'vitest'

const passthrough = (tag: string) => defineComponent({
  inheritAttrs: false,
  setup(_, { attrs, slots }) {
    return () => h(tag, attrs, slots.default ? slots.default() : [])
  },
})

config.global.stubs = {
  teleport: true,
  transition: false,
  'router-link': passthrough('a'),
  'router-view': passthrough('div'),
  'el-button': passthrough('button'),
  'el-alert': passthrough('div'),
  'el-card': passthrough('section'),
  'el-form': passthrough('form'),
  'el-form-item': passthrough('div'),
  'el-input': passthrough('input'),
  'el-select': passthrough('select'),
  'el-option': passthrough('option'),
  'el-divider': passthrough('hr'),
  'el-drawer': passthrough('div'),
  'el-dialog': passthrough('div'),
}

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

class IntersectionObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

vi.stubGlobal('ResizeObserver', ResizeObserverMock)
vi.stubGlobal('IntersectionObserver', IntersectionObserverMock)
vi.stubGlobal('scrollTo', vi.fn())

Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
  configurable: true,
  value: vi.fn(),
})

afterEach(() => {
  vi.clearAllMocks()
})