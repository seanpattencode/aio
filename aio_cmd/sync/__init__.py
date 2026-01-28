"""aio sync - unified sync/storage layer

Simple API:
    from aio_cmd.sync import store

    store.put("ssh", "server1", {"host": "user@1.2.3.4", "pw": "xxx"})
    store.get("ssh", "server1")
    store.delete("ssh", "server1")
    store.list("ssh")
    store.sync()  # push/pull with remote
"""

from .store import put, get, delete, list_all, sync, check_consensus
