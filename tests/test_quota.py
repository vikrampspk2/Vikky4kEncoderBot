import sqlite3
from config.weekly_quota import ensure_schema, can_consume, consume, get_usage

def test_quota():
    c=sqlite3.connect(':memory:')
    ensure_schema(c)
    assert can_consume(c, 1, 100, 100, 10)
    consume(c, 1, 40, 10)
    u=get_usage(c,1,10)
    assert u['used_bytes']==40 and u['used_tasks']==1
