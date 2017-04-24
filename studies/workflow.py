#from transitions import Machine
from transitions.extensions import GraphMachine as Machine


class Model(object):
    pass


m = Model()

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
        'source': 'retracted',
        'dest': 'submitted',
        'after': 'notify_administrators_of_submission',
    },
    {
        'trigger': 'resubmit',
        'source': 'rejected',
        'dest': 'submitted',
        'after': 'notify_administrators_of_submission'
    },
    {
        'trigger': 'activate',
        'source': 'approved',
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
        'trigger': 'activate',
        'source': 'paused',
        'dest': 'active',
        'after': 'notify_administrators_of_activation',
    },
    {
        'trigger': 'deactivate',
        'source': 'active',
        'dest': 'deactivated',
        'after': 'notify_administrators_of_deactivation'
    },
    {
        'trigger': 'deactivate',
        'source': 'paused',
        'dest': 'deactivated',
        'after': 'notify_administrators_of_deactivation'
    },
]

machine = Machine(model=m, states=states, transitions=transitions, initial='created')

m.get_graph().draw('workflow.png', prog='dot')
