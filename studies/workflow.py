
states = [
    'created',
    'submitted',
    'rejected',
    'retracted',
    'approved',
    'active',
    'paused',
    'deactivated'
]

STATE_CHOICES = tuple(
 (x, x.title()) for x in states
)

transitions = [
    {
        'trigger': 'submit',
        'source': 'created',
        'dest': 'submitted',
        'after': 'notify_administrators_of_submission',
    },
    {
        'trigger': 'approve',
        'source': 'submitted',
        'dest': 'approved',
        'after': 'notify_submitter_of_approval',
    },
    {
        'trigger': 'reject',
        'source': ['submitted', 'approved', 'active', 'paused', 'deactivated'],
        'dest': 'rejected',
        'after': 'notify_submitter_of_rejection',
    },
    {
        'trigger': 'retract',
        'source': 'submitted',
        'dest': 'retracted',
        'after': 'notify_administrators_of_retraction',
    },
    {
        'trigger': 'resubmit',
        'source': 'rejected',
        'dest': 'submitted',
        'after': 'notify_administrators_of_submission'
    },
    {
        'trigger': 'activate',
        'source': ['approved','paused'],
        'dest': 'active',
        'after': 'notify_administrators_of_activation'
    },
    {
        'trigger': 'pause',
        'source': 'active',
        'dest': 'paused',
        'after': 'notify_administrators_of_pause',
    },
    {
        'trigger': 'deactivate',
        'source': ['active', 'paused'],
        'dest': 'deactivated',
        'after': 'notify_administrators_of_deactivation'
    },
]
