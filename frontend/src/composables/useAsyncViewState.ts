import { computed, toValue } from 'vue'
import type { MaybeRefOrGetter } from 'vue'

export type AsyncViewState =
  | 'loading'
  | 'empty'
  | 'offline'
  | 'partial-failure'
  | 'blocking'
  | 'success'

export interface UseAsyncViewStateOptions {
  loading?: MaybeRefOrGetter<boolean>
  empty?: MaybeRefOrGetter<boolean>
  offline?: MaybeRefOrGetter<boolean>
  blocking?: MaybeRefOrGetter<boolean>
  partialFailure?: MaybeRefOrGetter<boolean>
}

export function useAsyncViewState(options: UseAsyncViewStateOptions) {
  const currentState = computed<AsyncViewState>(() => {
    if (toValue(options.offline) === true) {
      return 'offline'
    }

    if (toValue(options.blocking) === true) {
      return 'blocking'
    }

    if (toValue(options.loading) === true) {
      return 'loading'
    }

    if (toValue(options.empty) === true) {
      return 'empty'
    }

    if (toValue(options.partialFailure) === true) {
      return 'partial-failure'
    }

    return 'success'
  })

  return {
    currentState,
  }
}