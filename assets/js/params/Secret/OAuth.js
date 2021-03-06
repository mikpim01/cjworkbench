import React from 'react'
import PropTypes from 'prop-types'
import { Trans } from '@lingui/macro'

export default class OAuth extends React.PureComponent {
  static propTypes = {
    isOwner: PropTypes.bool.isRequired,
    name: PropTypes.string.isRequired,
    secretMetadata: PropTypes.shape({
      name: PropTypes.string.isRequired
    }), // null if not set
    startCreateSecret: PropTypes.func.isRequired, // func(name) => undefined
    deleteSecret: PropTypes.func.isRequired, // func(name) => undefined
    secretLogic: PropTypes.shape({
      provider: PropTypes.oneOf(['oauth1a', 'oauth2']),
      service: PropTypes.oneOf(['google', 'intercom', 'twitter'])
    })
  }

  handleClickConnect = () => {
    const { name, startCreateSecret } = this.props
    startCreateSecret(name)
  }

  handleClickDisconnect = () => {
    const { name, deleteSecret } = this.props
    deleteSecret(name)
  }

  render () {
    const { secretMetadata, isOwner } = this.props

    let contents
    if (secretMetadata) {
      contents = (
        <>
          <p className='secret-name'>{secretMetadata.name}</p>
          {isOwner ? (
            <button type='button' className='disconnect' onClick={this.handleClickDisconnect}><Trans id='js.params.Secret.OAuth.signOut.button'>Sign out</Trans></button>
          ) : null}
        </>
      )
    } else if (isOwner) {
      contents = (
        <button type='button' className='connect' onClick={this.handleClickConnect}><Trans id='js.params.Secret.OAuth.connectAccount.button'>Connect account</Trans></button>
      )
    } else {
      contents = (
        <p className='not-owner'>
          <Trans id='js.params.Secret.OAuth.onlyOwnerCanConnect'>Not authenticated. Only the workflow owner may authenticate.</Trans>
        </p>
      )
    }

    return (
      <div className='oauth-connect-parameter'>
        {contents}
      </div>
    )
  }
}
