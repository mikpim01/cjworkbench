import React from 'react'
import PropTypes from 'prop-types'
import { Trans, t } from '@lingui/macro'
import { Dropdown, DropdownToggle, DropdownMenu, DropdownItem } from '../../components/Dropdown'
import IconChart from '../../../icons/chart.svg'

export default function AddChartBlockPrompt ({ tabs, isMenuOpen, onOpenMenu, onCloseMenu, onSubmit }) {
  const handleToggleMenu = isMenuOpen ? onCloseMenu : onOpenMenu
  const handleClick = React.useCallback(ev => {
    onSubmit({ stepSlug: ev.target.getAttribute('data-step-slug') })
  }, [onSubmit])

  return (
    <Dropdown isOpen={isMenuOpen} toggle={handleToggleMenu}>
      <DropdownToggle
        name='add-chart-block'
        title={t({
          id: 'js.WorkflowEditor.Report.AddChartBlockPrompt.hoverText',
          message: 'Add chart'
        })}
      >
        <IconChart />
      </DropdownToggle>
      <DropdownMenu>
        {tabs.map(({ slug: tabSlug, name: tabName, chartSteps }) => (
          <React.Fragment key={tabSlug}>
            {chartSteps.map(({ slug: stepSlug, moduleName }) => (
              <DropdownItem
                key={stepSlug}
                data-step-slug={stepSlug}
                onClick={handleClick}
              >
                <Trans id='js.WorkflowEditor.Report.AddChartBlockPrompt.tabAndChartName'>{tabName} – {moduleName}</Trans>
              </DropdownItem>
            ))}
          </React.Fragment>
        ))}
      </DropdownMenu>
    </Dropdown>
  )
}
AddChartBlockPrompt.propTypes = {
  tabs: PropTypes.arrayOf(PropTypes.shape({
    slug: PropTypes.string.isRequired,
    name: PropTypes.string.isRequired,
    chartSteps: PropTypes.arrayOf(PropTypes.shape({
      slug: PropTypes.string.isRequired,
      moduleName: PropTypes.string.isRequired
    }).isRequired).isRequired
  }).isRequired).isRequired,
  isMenuOpen: PropTypes.bool.isRequired,
  onOpenMenu: PropTypes.func.isRequired,
  onCloseMenu: PropTypes.func.isRequired,
  onSubmit: PropTypes.func.isRequired // func({ tabSlug }) => undefined
}