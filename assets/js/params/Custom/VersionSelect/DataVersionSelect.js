import React from 'react'
import PropTypes from 'prop-types'
import DataVersionModal from '../../../WorkflowEditor/DataVersionModal'
import { connect } from 'react-redux'
import { t, Trans } from '@lingui/macro'

export class DataVersionSelect extends React.PureComponent {
  static propTypes = {
    stepId: PropTypes.number.isRequired,
    currentVersionIndex: PropTypes.number, // or null for no selected version
    nVersions: PropTypes.number.isRequired, // may be 0
    isReadOnly: PropTypes.bool.isRequired
  }

  state = {
    isDataVersionModalOpen: false
  }

  handleClickOpenModal = () => this.setState({ isDataVersionModalOpen: true })
  handleCloseModal = () => this.setState({ isDataVersionModalOpen: false })

  render () {
    const { stepId, currentVersionIndex, nVersions, isReadOnly } = this.props
    const { isDataVersionModalOpen } = this.state

    let inner

    if (nVersions === 0) {
      inner = (
        <>
          <div className='label'>
            <Trans id='js.params.Custom.VersionSelect.DataVersionSelect.noVersions.label'>
                Version
            </Trans>
          </div>
          <div className='no-versions'>–</div>
        </>
      )
    } else if (isReadOnly) {
      inner = (
        <div className='read-only'>
          <Trans id='js.params.Custom.VersionSelect.DataVersionSelect.readOnly.label' comment='The parameter {0} will be the current version and {nVersions} will be the number of versions'>
            Version {nVersions - currentVersionIndex} of {nVersions}
          </Trans>
        </div>
      )
    } else {
      inner = (
        <>
          <div className='label'>
            <Trans id='js.params.Custom.VersionSelect.DataVersionSelect.selectVersion.label'>
                Version
            </Trans>
          </div>
          <button
            type='button'
            title={t({ id: 'js.params.Custom.VersionSelect.DataVersionSelect.selectVersion.hoverText', message: 'Select version' })}
            onClick={this.handleClickOpenModal}
          >
            <Trans
              id='js.params.Custom.VersionSelect.DataVersionSelect.versionCount'
              comment='The parameter {0} will be the current version and {nVersions} will be the number of versions'
            >
              {nVersions - currentVersionIndex} of {nVersions}
            </Trans>
          </button>
          {isDataVersionModalOpen ? (
            <DataVersionModal
              stepId={stepId}
              onClose={this.handleCloseModal}
            />
          ) : null}
        </>
      )
    }

    return (
      <div className='version-item'>
        {inner}
      </div>
    )
  }
}

function mapStateToProps (state, { stepId }) {
  const isReadOnly = state.workflow.read_only

  const step = state.steps[String(stepId)]
  if (!step || !step.versions || !step.versions.selected) {
    return {
      currentVersionIndex: null,
      nVersions: 0,
      isReadOnly
    }
  }

  const { versions, selected } = step.versions
  const index = versions.findIndex(arr => arr[0] === selected) || null

  return {
    currentVersionIndex: index,
    nVersions: versions.length,
    isReadOnly
  }
}

export default connect(
  mapStateToProps
)(DataVersionSelect)
