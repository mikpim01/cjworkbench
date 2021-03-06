import React from 'react'
import PropTypes from 'prop-types'
import { connect } from 'react-redux'
import { Trans, t } from '@lingui/macro'
import { Modal, ModalHeader, ModalBody, ModalFooter } from './components/Modal'
import { setStepParamsAction } from './workflow-reducer'
import { setWorkflowPublicAction } from './ShareModal/actions'
import { escapeHtml } from './utils'
import EmbedIcon from '../icons/embed.svg'

export class OutputIframe extends React.PureComponent {
  static propTypes = {
    deltaId: PropTypes.number, // null if added to empty workflow
    stepId: PropTypes.number, // null if no step
    isPublic: PropTypes.bool.isRequired,
    workflowId: PropTypes.number.isRequired
  }

  state = {
    heightFromIframe: null, // if set, the iframe told us how tall it wants to be
    isModalOpen: false
  }

  componentDidUpdate (prevProps, prevState) {
    if (prevProps.stepId !== this.props.stepId) {
      this.setState({
        heightFromIframe: null
      })
    }

    if (prevState.heightFromIframe !== this.state.heightFromIframe) {
      const resizeEvent = document.createEvent('Event')
      resizeEvent.initEvent('resize', true, true)
      window.dispatchEvent(resizeEvent)
    }
  }

  componentDidMount () {
    window.addEventListener('message', this.handleMessage)
  }

  componentWillUnmount () {
    window.removeEventListener('message', this.handleMessage)
  }

  handleMessage = (ev) => {
    const data = ev.data
    if (data && data.from === 'outputIframe') {
      if (data.stepId !== this.props.stepId) {
        // This message isn't from the iframe we created.
        //
        // This check works around a race:
        //
        // 1. Show an iframe
        //    ... it sends a 'resize' event
        //    ... it keeps sending 'resize' events whenever its size changes
        // 2. Switch to a different iframe src
        //    ... this resets size and sets new iframe src; BUT before the new
        //        iframe can load, the _old_ iframe's JS sends a 'resize' event
        //
        // By forcing the iframe to send its identity, we can make sure this
        // message isn't spurious.
        return
      }

      switch (data.type) {
        case 'resize':
          this.setState({ heightFromIframe: data.height })
          break
        case 'set-params':
          this.props.setStepParams(data.stepId, data.params)
          break
        default:
          console.error('Unhandled message from iframe', data)
      }
    }
  }

  handleClickOpenEmbedModal = () => {
    this.setState({ isModalOpen: true })
  }

  closeModal = () => {
    this.setState({ isModalOpen: false })
  }

  handleClickModalClose = this.closeModal

  handleClickSetWorkflowPublic = () => { this.props.setWorkflowPublic() }

  isModalOpen (name) {
    if (!this.state.isModalOpen) return false
    if (this.props.isPublic) {
      return name === 'embed'
    } else {
      return name === 'public'
    }
  }

  renderPublicModal () {
    return (
      <Modal isOpen={this.isModalOpen('public')} toggle={this.closeModal}>
        <ModalHeader toggle={this.closeModal}>
          <div className='modal-title'>
            <Trans id='js.OutputIframe.private.header.title' comment='This should be all-caps for styling reasons'>
              SHARE THIS WORKFLOW
            </Trans>
          </div>
        </ModalHeader>
        <ModalBody>
          <div className='title-3 mb-3'>
            <Trans id='js.OutputIframe.private.workflowIsPrivate'>This workflow is currently private</Trans>
          </div>
          <div className='info-3 t-d-gray'>
            <Trans id='js.OutputIframe.private.setToPublic'>
              Set this workflow to Public in order to share it? Anyone with the URL will be able to access and duplicate it.
            </Trans>
          </div>
        </ModalBody>
        <ModalFooter>
          <div onClick={this.handleClickModalClose} className='button-gray action-button mr-4'>
            <Trans id='js.OutputIframe.footer.cancelButton'>Cancel</Trans>
          </div>
          <div onClick={this.handleClickSetWorkflowPublic} className='button-blue action-button test-public-button'>
            <Trans id='js.OutputIframe.footer.setPublicButton'>Set public</Trans>
          </div>
        </ModalFooter>
      </Modal>
    )
  }

  renderEmbedModal () {
    const iframeCode = escapeHtml('<iframe src="' + window.location.protocol + '//' + window.location.host + '/embed/' + this.props.stepId + '" width="560" height="315" frameborder="0"></iframe>')

    return (
      <Modal isOpen={this.isModalOpen('embed')} toggle={this.closeModal}>
        <ModalHeader toggle={this.closeModal}>
          <div className='modal-title'>
            <Trans id='js.OutputIframe.embed.header.title' comment='This should be all-caps for styling reasons'>
              EMBED THIS CHART
            </Trans>
          </div>
        </ModalHeader>
        <ModalBody>
          <p className='info'>
            <Trans id='js.OutputIframe.embed.embedCode'>Paste this code into any webpage HTML</Trans>
          </p>
          <div className='code-snippet'>
            <code className='chart-embed'>
              {iframeCode}
            </code>
          </div>
        </ModalBody>
        <div className='modal-footer'>
          <div onClick={this.handleClickModalClose} className='button-gray action-button'>
            <Trans id='js.OutputIframe.footer.OKButton'>OK</Trans>
          </div>
        </div>
      </Modal>
    )
  }

  render () {
    const { stepId, deltaId } = this.props
    const { heightFromIframe } = this.state
    const src = `/api/wfmodules/${stepId}/output#revision=${deltaId}`

    const classNames = ['outputpane-iframe']
    let style
    if (heightFromIframe !== null) {
      classNames.push('has-height-from-iframe')
      if (heightFromIframe === 0) {
        classNames.push('height-0')
      }
      style = { height: Math.ceil(heightFromIframe) }
    } else {
      style = null
    }

    return (
      <div className={classNames.join(' ')} style={style}>
        <iframe src={src} />
        <button
          name='embed'
          title={t({ id: 'js.OutputIframe.getEmbeddableUrl.hoverText', message: 'Get an embeddable URL' })}
          onClick={this.handleClickOpenEmbedModal}
        >
          <EmbedIcon />
        </button>
        {this.renderPublicModal()}
        {this.renderEmbedModal()}
      </div>
    )
  }
}

const mapStateToProps = (state) => ({})

const mapDispatchToProps = (dispatch, ownProps) => {
  return {
    setWorkflowPublic: () => {
      dispatch(setWorkflowPublicAction(true))
    },
    setStepParams: (stepId, params) => {
      dispatch(setStepParamsAction(stepId, params))
    }
  }
}

export default connect(
  mapStateToProps,
  mapDispatchToProps
)(OutputIframe)
