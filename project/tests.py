"""Project-level configuration regression tests."""

from django.test import SimpleTestCase

# kombu's (and Celery's) default broker connection pool size. A pool is first
# built at this size, so any configured limit below it makes kombu take
# Resource.resize()'s *shrink* path.
KOMBU_DEFAULT_POOL_LIMIT = 10


class CeleryBrokerPoolLimitTests(SimpleTestCase):
    """Guard against reintroducing the kombu shrink-to-zero crash.

    Setting CELERY_BROKER_POOL_LIMIT to 0 or None (or any value
    below kombu's default pool size of 10) makes kombu take Resource.resize()'s
    shrink path the first time a broker pool is built. That path calls
    resource.queue.popleft(). In our gevent web/worker processes
    (manage.py, uwsgi run gevent.monkey.patch_all()) that queue is a
    plain list with no popleft, so it raises AttributeError:
    'list' object has no attribute 'popleft'. That kills the
    first .delay() in a new process and rolls back any enclosing
    transaction.

    monkey.patch_all() replaces stdlib queue.LifoQueue with gevent's C
    LifoQueue, whose __init__ never calls the Python-level _init
    hook, so kombu's _init (which would back the queue with a deque) is
    bypassed, and the queue stays a list. In a plain (non-gevent)
    interpreter the queue is a deque and the crash is invisible, which is
    why it never reproduced locally or in bare python on the pod.

    Other options for fixing this are:
    - update gevent to >= 25.9.1
    - exclude queue from monkey patching: patch_all(queue=False).
    If we do either of these things, we could reset the pool limit to 0
    and/or remove these tests.
    """

    def test_broker_pool_limit_is_not_a_shrinking_value(self):
        from project.celery import app

        # The value Celery will actually hand to kombu.pools.set_limit().
        limit = app.conf.broker_pool_limit

        self.assertNotIn(
            limit,
            (0, None),
            "CELERY_BROKER_POOL_LIMIT must not be 0 or None -- both take kombu's "
            "crashing pool-shrink path. Leave the setting unset so Celery's "
            "default applies.",
        )
        self.assertGreaterEqual(
            limit,
            KOMBU_DEFAULT_POOL_LIMIT,
            "CELERY_BROKER_POOL_LIMIT must not be smaller than kombu's default "
            "pool size, or the first pool build takes the crashing shrink path. ",
        )
