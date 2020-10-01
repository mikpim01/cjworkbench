import { connect } from 'react-redux'
import File from './File'
import { setStepParamsAction } from '../../workflow-reducer'
import { upload, cancel } from './actions'

const mapStateToProps = (state, ownProps) => {
  const { wfModules } = state
  const wfModule = wfModules[String(ownProps.wfModuleId)]
  return {
    inProgressUpload: wfModule.inProgressUpload || null
  }
}

const mapDispatchToProps = {
  uploadFile: upload,
  cancelUpload: cancel,
  setStepParams: setStepParamsAction
}

export default connect(mapStateToProps, mapDispatchToProps)(File)
