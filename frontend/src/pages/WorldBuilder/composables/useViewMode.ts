import { ref, reactive } from 'vue'

export type ViewMode = 'graph' | 'map' | 'layer' | 'space'

export interface ViewState {
  zoom: number
  x: number
  y: number
}

export function useViewMode() {
  const activeView = ref<ViewMode>('graph')

  // 每个视图保存独立的相机状态
  const viewStates = reactive<Record<ViewMode, ViewState>>({
    graph: { zoom: 1, x: 0, y: 0 },
    map:   { zoom: 1, x: 0, y: 0 },
    layer: { zoom: 1, x: 0, y: 0 },
    space: { zoom: 1, x: 0, y: 0 },
  })

  function switchView(mode: ViewMode) {
    activeView.value = mode
  }

  function saveViewState(mode: ViewMode, state: ViewState) {
    viewStates[mode] = { ...state }
  }

  function getViewState(mode: ViewMode): ViewState {
    return viewStates[mode]
  }

  return { activeView, viewStates, switchView, saveViewState, getViewState }
}
