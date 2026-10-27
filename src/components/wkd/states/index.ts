import type { Component } from 'vue'
import type { WkdStatus } from '../../../types'
import NewWkdStatePanel from './NewWkdStatePanel.vue'
import VerifyStatePanel from './VerifyStatePanel.vue'
import ReviewStatePanel from './ReviewStatePanel.vue'
import ApprovedStatePanel from './ApprovedStatePanel.vue'
import DisableConfirmStatePanel from './DisableConfirmStatePanel.vue'
import DisabledStatePanel from './DisabledStatePanel.vue'

export const statePanels: Record<WkdStatus, Component> = {
  NEW_WKD: NewWkdStatePanel,
  VERIFY: VerifyStatePanel,
  REVIEW: ReviewStatePanel,
  APPROVED: ApprovedStatePanel,
  DISABLE_CONFIRM: DisableConfirmStatePanel,
  DISABLED: DisabledStatePanel,
}
