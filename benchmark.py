"""
Utility to compare the different Backends performance.

Below the elapsed time running the tests using:

- Mac OS X 10.10
- Redis 2.8.17, standalone mode, default configuration

    python benchmark.py
        03.25  # (seconds) using MemoryBackEnd
        29.07  # (seconds) Using RedisBackEnd
        05.28  # (seconds) Using RedisHighPerfBackEnd
"""

import hanoi
import redis
import time

_redis = redis.Redis('localhost', 6379)

rolloutM = hanoi.Rollout(hanoi.MemoryBackEnd())

rollout = hanoi.Rollout(hanoi.RedisBackEnd(_redis))

rolloutHP = hanoi.Rollout(hanoi.RedisHighPerfBackEnd(_redis))

FN = 'FOO'

USER = "USER-{0}"

LOOP = 10000

for client in (rolloutM, rollout, rolloutHP):

    t0 = time.time()

    client.add_func(FN)

    for i in xrange(0, LOOP):
        client.register(FN, USER.format(str(i)))

    for i in xrange(0, LOOP):
        client.is_enabled(FN, USER.format(str(i)))
        client.is_enabled(FN, USER.format('a'))

    t1 = time.time()

    print "%.2f" % round(t1-t0, 2)

    _redis.flushdb()
