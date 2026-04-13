import { mount } from '@vue/test-utils'

import TraceInspector from '../TraceInspector.vue'

describe('TraceInspector', () => {
  it('shows empty state for run without steps', () => {
    const wrapper = mount(TraceInspector, {
      props: {
        data: { run_id: 'run-1', status: 'running', steps: [] },
      },
    })

    expect(wrapper.text()).toContain('暂无步骤数据')
    expect(wrapper.text()).toContain('选择左侧步骤查看详情')
  })

  it('renders root cause and correlation metadata', () => {
    const wrapper = mount(TraceInspector, {
      props: {
        data: {
          run_id: 'run-1',
          status: 'failed',
          correlation_id: 'corr-run',
          root_cause: {
            type: 'persistence_error',
            message: 'sqlite commit failed',
            step_id: 'step-2',
            correlation_id: 'corr-step',
          },
          steps: [
            { step_id: 'step-2', step_index: 2, agent_name: 'writer', status: 'failed' },
          ],
        },
      },
    })

    expect(wrapper.text()).toContain('根因诊断')
    expect(wrapper.text()).toContain('持久化错误')
    expect(wrapper.text()).toContain('sqlite commit failed')
    expect(wrapper.text()).toContain('corr-step')
  })

  it('renders step diagnostics for failed step', () => {
    const wrapper = mount(TraceInspector, {
      props: {
        data: {
          run_id: 'run-1',
          status: 'failed',
          steps: [
            {
              step_id: 'step-1',
              step_index: 1,
              agent_name: 'planner',
              status: 'failed',
              correlation_id: 'corr-1',
              failure_type: 'rule_blocked',
              failure_message: 'world rule rejected',
              artifact: {
                artifact_id: 'artifact-1',
                agent_name: 'planner',
                correlation_id: 'corr-1',
                input_summary: 'summary',
                output_content: 'content',
                quality_scores: {},
                token_in: 1,
                token_out: 2,
                latency_ms: 3,
                retry_count: 0,
              },
            },
          ],
        },
      },
    })

    expect(wrapper.text()).toContain('步骤诊断')
    expect(wrapper.text()).toContain('rule_blocked')
    expect(wrapper.text()).toContain('world rule rejected')
    expect(wrapper.text()).toContain('corr-1')
  })

  it('emits approval actions from paused banner', async () => {
    const wrapper = mount(TraceInspector, {
      props: {
        data: {
          run_id: 'run-1',
          status: 'paused',
          steps: [{ step_id: 'step-1', step_index: 1, agent_name: 'planner', status: 'paused' }],
          approval_checkpoint: { reason: 'need hitl' },
        },
      },
    })

    await wrapper.get('.approval-btn.approve').trigger('click')
    await wrapper.get('.approval-btn.retry').trigger('click')
    await wrapper.get('.approval-btn.reject').trigger('click')

    expect(wrapper.emitted('approve')).toHaveLength(1)
    expect(wrapper.emitted('retry')).toHaveLength(1)
    expect(wrapper.emitted('reject')).toHaveLength(1)
  })

  it('renders tree trace note for non-run payload', () => {
    const wrapper = mount(TraceInspector, {
      props: {
        data: { note: 'not yet available' },
      },
    })

    expect(wrapper.text()).toContain('当前章节暂无可视化执行链路')
  })
})