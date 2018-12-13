
from django.utils.translation import ugettext as _

from model_utils import Choices

states = [
    'created',
    'submitted',
    'rejected',
    'retracted',
    'approved',
    'active',
    'paused',
    'deactivated',
    'archived',
]
state_tuples = tuple((x, _(x.title())) for x in states)

STATE_CHOICES = Choices(*state_tuples)

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
        'source': ['submitted', 'active', 'paused', 'deactivated'],
        'dest': 'rejected',
        'after': 'notify_submitter_of_rejection',
    },
    {
        'trigger': 'reject',
        'source': 'approved',
        'dest': 'rejected',
        'after': 'notify_submitter_of_recission',
    },
    {
        'trigger': 'archive',
        'source': ['created', 'rejected', 'retracted', 'submitted', 'approved', 'active', 'paused', 'deactivated'],
        'dest': 'archived',
    },
    {
        'trigger': 'retract',
        'source': 'submitted',
        'dest': 'retracted',
        'after': 'notify_administrators_of_retraction',
    },
    {
        'trigger': 'resubmit',
        'source': ['rejected', 'retracted'],
        'dest': 'submitted',
        'after': 'notify_administrators_of_submission'
    },
    {
        'trigger': 'activate',
        'source': ['approved', 'paused'],
        'dest': 'active',
        'before': ['check_if_built'],
        'after': ['notify_administrators_of_activation']
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
