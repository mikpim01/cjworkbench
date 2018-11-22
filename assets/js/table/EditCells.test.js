import { updateTableActionModule } from './UpdateTableAction'

jest.mock('../workflow-reducer')
import { store, addModuleAction, setWfModuleParamsAction, setSelectedWfModuleAction } from '../workflow-reducer'

describe('Edit Cell actions', () => {
  const Edit1 = { row: 3, col: 'foo', value: 'bar' }
  const Edit2 = { row: 10, col: 'bar', value: 'yippee!' }
  const Edit3 = { row: 3, col: 'foo', value: 'new!' }

  // mocked data from api.addModule call, looks like a just-added edit cells module
  const addModuleResponse = {
    data: {
      wfModule: {
        id: 99,
        module_version: { module: 77 },
        parameter_vals: [
          {
            parameter_spec: { id_name: 'celledits' },
            value: ''
          }
        ]
      }
    }
  }

  const initialState = {
    workflow: {
      wf_modules: [ 10, 20, 30, 40 ]
    },
    modules: {
      77: { id_name: 'editcells' },
      1: { id_name: 'loadurl' },
      2: { id_name: 'filter' }
    },
    wfModules: {
      10: { id: 10, module_version: { module: 1 } },
      20: {
        // Existing Edit Cells module with existing edits
        id: 20,
        module_version: { module: 77 },
        parameter_vals: [
          {
            parameter_spec: { id_name: 'celledits' },
            value: JSON.stringify([ Edit1 ]),
          }
        ]
      },
      30: { id: 30, module_version: { module: 2 } },
      40: { id: 40, module_version: { module: 2 } }
    }
  }

  beforeEach(() => {
    store.getState.mockImplementation(() => initialState)
    // Our shim Redux API:
    // 1) actions are functions; dispatch returns their retvals in a Promise.
    //    This is useful when we care about retvals.
    // 2) actions are _not_ functions; dispatch does nothing. This is useful when
    //    we care about arguments.
    store.dispatch.mockReset()
    store.dispatch.mockImplementation(action => {
      if (typeof action === 'function') {
        return Promise.resolve({ value: action() })
      }
    })

    setWfModuleParamsAction.mockReset()
    setWfModuleParamsAction.mockImplementation((...args) => [ 'setWfModuleParamsAction', ...args ])
    setSelectedWfModuleAction.mockReset()
    setSelectedWfModuleAction.mockImplementation((...args) => [ 'setSelectedWfModuleAction', ...args ])
  })

  it('adds edit to existing Edit Cell module', () => {
    updateTableActionModule(20, 'editcells', false, Edit2)
    expect(store.dispatch).toHaveBeenCalledWith([ 'setWfModuleParamsAction', 20, { celledits: JSON.stringify([ Edit1, Edit2 ]) }])
  })

  it('replaces edit in an existing Edit Cell module', () => {
    // Replace the previous edit of the same cell
    updateTableActionModule(20, 'editcells', false, Edit3)
    expect(store.dispatch).toHaveBeenCalledWith([ 'setWfModuleParamsAction', 20, { celledits: JSON.stringify([ Edit3 ]) }])
  })

  it('selects the Edit Cell module it is editing', () => {
    updateTableActionModule(20, 'editcells', false, Edit2)
    expect(store.dispatch).toHaveBeenCalledWith([ 'setSelectedWfModuleAction', 1 ])
  })

  it('adds edit to immediately-following Edit Cell module', () => {
    updateTableActionModule(10, 'editcells', false, Edit2)
    expect(store.dispatch).toHaveBeenCalledWith([ 'setWfModuleParamsAction', 20, { celledits: JSON.stringify([ Edit1, Edit2 ]) }])
  })

  it('adds new Edit Cells module before end of stack', (done) => {
    addModuleAction.mockImplementation(() => () => addModuleResponse) // id: 99
    updateTableActionModule(30, 'editcells', false, Edit2)

    expect(addModuleAction).toHaveBeenCalledWith('editcells', 3)

    // let addModule promise resolve
    setImmediate(() => {
      expect(store.dispatch).toHaveBeenCalledWith([ 'setWfModuleParamsAction', 99, { celledits: JSON.stringify([ Edit2 ]) }])
      done()
    })
  })

  it('add new Edit Cells module to end of stack', () => {
    addModuleAction.mockImplementation(() => () => addModuleResponse)
    updateTableActionModule(40, 'editcells', false, { row: 10, col: 'bar', value: 'yippee!' })
    expect(addModuleAction).toHaveBeenCalledWith('editcells', 4)
  })
})
