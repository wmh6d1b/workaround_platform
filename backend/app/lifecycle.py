from .models import WkdStatus

RULES = {
    'submit_verify': (WkdStatus.NEW_WKD, WkdStatus.VERIFY, 'wkd.submit', False),
    'submit_review': (WkdStatus.VERIFY, WkdStatus.REVIEW, 'wkd.submit', False),
    'approve': (WkdStatus.REVIEW, WkdStatus.APPROVED, 'wkd.review', True),
    'reject': (WkdStatus.REVIEW, WkdStatus.VERIFY, 'wkd.review', True),
    'request_disable': (WkdStatus.APPROVED, WkdStatus.DISABLE_CONFIRM, 'wkd.disable', True),
    'confirm_disable': (WkdStatus.DISABLE_CONFIRM, WkdStatus.DISABLED, 'wkd.review', True),
    'reject_disable': (WkdStatus.DISABLE_CONFIRM, WkdStatus.APPROVED, 'wkd.review', True),
    'disable': (None, WkdStatus.DISABLED, 'wkd.disable', True),
}

def transition_rule(action: str, current: WkdStatus):
    rule = RULES.get(action)
    if not rule:
        return None
    source, target, permission, note_required = rule
    allowed = (WkdStatus.NEW_WKD, WkdStatus.VERIFY) if action == 'disable' else (source,)
    if current not in allowed:
        return None
    return target, permission, note_required
