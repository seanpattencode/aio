#
#  The MIT License (MIT)
#
#  Copyright (c) 2019 Peter Wang
#
#  Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to deal
#  in the Software without restriction, including without limitation the rights
#  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#  copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in all
#  copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#  SOFTWARE.
#
import os
import sqlite3
import threading
import time
from collections import namedtuple
from enum import IntEnum

from persistqueue import common
from persistqueue.exceptions import Empty, NotSupportedError
from persistqueue.serializers import pickle

# pqid is a unique id for a item in the queue
# it is also the primary key of the table
# item is the data stored in the queue
# status is the status of the item
# 0 for ready
# 1 for unack
# 2 for acked
# 3 for ack_failed
# timestamp is the time when the item is created
# update_time is the time when the item is updated
# ack_time is the time when the item is acked
# nack_time is the time when the item is nacked
# ack_failed_time is the time when the item is ack_failed
# consumer_id is the id of the consumer who is processing the item
# item is a tuple of (pqid, item, status, timestamp, update_time, ack_time,
# nack_time, ack_failed_time, consumer_id)
# This is the raw item from the queue
RawItem = namedtuple(
    "RawItem",
    [
        "pqid",
        "item",
        "status",
        "timestamp",
        "update_time",
        "ack_time",
        "nack_time",
        "ack_failed_time",
        "consumer_id",
    ],
)


class AckStatus(IntEnum):
    # The item is ready to be processed
    READY = 0
    # The item is being processed
    UNACK = 1
    # The item has been processed successfully
    ACKED = 2
    # The item has failed to be processed
    FAILED = 3


class SQLiteAckQueue(object):
    """
    A thread-safe, disk-based, persistent queue with acknowledgment.
    """

    def __init__(
        self,
        path,
        name="default",
        multithreading=False,
        timeout=10.0,
        serializer=pickle,
        db_file_name=None,
    ):
        """
        Initialize a persistent queue.

        :param path: directory where the queue is stored
        :param name: name of the queue
        :param multithreading: if True, the queue is thread-safe
        :param timeout: timeout for database connection
        :param serializer: serializer to use for storing data
        :param db_file_name: name of the database file, default is queue.db
        """
        self.path = path
        if not os.path.exists(self.path):
            os.makedirs(self.path)
        self.name = name
        self.multithreading = multithreading
        self.timeout = timeout
        self.serializer = serializer
        if db_file_name is None:
            db_file_name = "queue.db"
        self.db_path = os.path.join(self.path, db_file_name)
        self._conn = self._new_db_connection(self.db_path, self.multithreading, self.timeout)
        self._cursor = self._conn.cursor()
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._init_table()
        self.task_done_condition = threading.Condition(threading.Lock())
        self._unacked_count = self._count_by_status(AckStatus.UNACK)
        self._total = self._count_total()
        self._acked_count = self._count_by_status(AckStatus.ACKED)
        self._failed_count = self._count_by_status(AckStatus.FAILED)
        self._ready_count = self._count_by_status(AckStatus.READY)

    def _new_db_connection(self, path, multithreading, timeout):
        conn = None
        if multithreading:
            common.check_sqlite_threading()
            conn = sqlite3.connect(path, timeout=timeout, check_same_thread=False)
        else:
            conn = sqlite3.connect(path, timeout=timeout)
        return conn

    def _init_table(self):
        """
        Initialize the table in the database.
        """
        self._cursor.execute(
            "CREATE TABLE IF NOT EXISTS `{}` "
            "(pqid INTEGER PRIMARY KEY AUTOINCREMENT, "
            "item BLOB, "
            "status INTEGER DEFAULT 0, "
            "timestamp REAL DEFAULT (CAST(strftime('%s','now') AS REAL)), "
            "update_time REAL, "
            "ack_time REAL, "
            "nack_time REAL, "
            "ack_failed_time REAL, "
            "consumer_id TEXT)".format(self.name)
        )
        self._cursor.execute(
            "CREATE INDEX IF NOT EXISTS status_index ON `{}` (status)".format(self.name)
        )
        self.commit()

    def _get_item_from_row(self, row):
        """
        Get item from a row.
        """
        if row:
            return RawItem(*row)
        return None

    def _get_raw_item(self, item):
        """
        Get raw item from item.
        """
        if isinstance(item, RawItem):
            return item
        else:
            # This is a bit of a hack to get the raw item
            # We assume that the item is the data part of the raw item
            # We need to find the raw item with the same data
            # This is not efficient, but it is the only way to do it
            # without changing the API
            sql = "SELECT * FROM `{}` WHERE item =?".format(self.name)
            self._cursor.execute(sql, (self.serializer.dumps(item),))
            row = self._cursor.fetchone()
            return self._get_item_from_row(row)

    def _get_pqid(self, item):
        """
        Get pqid from item.
        """
        if isinstance(item, RawItem):
            return item.pqid
        else:
            raw_item = self._get_raw_item(item)
            if raw_item:
                return raw_item.pqid
            return None

    def _count_by_status(self, status):
        """
        Count items by status.
        """
        sql = "SELECT COUNT(pqid) FROM `{}` WHERE status =?".format(self.name)
        self._cursor.execute(sql, (status,))
        row = self._cursor.fetchone()
        return row if row else 0

    def _count_total(self):
        """
        Count total items.
        """
        sql = "SELECT COUNT(pqid) FROM `{}`".format(self.name)
        self._cursor.execute(sql)
        row = self._cursor.fetchone()
        return row if row else 0

    def _update_status(self, pqid, status, consumer_id=None):
        """
        Update status of an item.
        """
        now = time.time()
        sql = "UPDATE `{}` SET status =?, update_time =?".format(self.name)
        params = [status, now]
        if status == AckStatus.ACKED:
            sql += ", ack_time =?"
            params.append(now)
        elif status == AckStatus.FAILED:
            sql += ", ack_failed_time =?"
            params.append(now)
        elif status == AckStatus.READY:
            sql += ", nack_time =?"
            params.append(now)
        elif status == AckStatus.UNACK:
            sql += ", consumer_id =?"
            params.append(consumer_id)
        sql += " WHERE pqid =?"
        params.append(pqid)
        self._cursor.execute(sql, tuple(params))
        self.commit()

    def put(self, item):
        """
        Put an item into the queue.
        """
        obj = self.serializer.dumps(item)
        sql = "INSERT INTO `{}` (item) VALUES (?)".format(self.name)
        self._cursor.execute(sql, (obj,))
        self.commit()
        with self.task_done_condition:
            self._total += 1
            self._ready_count += 1
            self.task_done_condition.notify()
        return self._cursor.lastrowid

    def get(self, block=True, timeout=None, consumer_id=None):
        """
        Get an item from the queue.
        """
        if not block:
            return self._get(consumer_id)
        else:
            start_time = time.time()
            while True:
                try:
                    return self._get(consumer_id)
                except Empty:
                    if timeout:
                        remaining = timeout - (time.time() - start_time)
                        if remaining <= 0.0:
                            raise Empty
                        with self.task_done_condition:
                            self.task_done_condition.wait(remaining)
                    else:
                        with self.task_done_condition:
                            self.task_done_condition.wait()

    def _get(self, consumer_id=None):
        """
        Get an item from the queue.
        """
        sql = "SELECT * FROM `{}` WHERE status =? ORDER BY pqid LIMIT 1".format(self.name)
        self._cursor.execute(sql, (AckStatus.READY,))
        row = self._cursor.fetchone()
        if row:
            item = self._get_item_from_row(row)
            self._update_status(item.pqid, AckStatus.UNACK, consumer_id)
            with self.task_done_condition:
                self._unacked_count += 1
                self._ready_count -= 1
            return item
        else:
            raise Empty

    def ack(self, item):
        """
        Acknowledge an item.
        """
        pqid = self._get_pqid(item)
        if pqid:
            self._update_status(pqid, AckStatus.ACKED)
            with self.task_done_condition:
                self._unacked_count -= 1
                self._acked_count += 1
                self.task_done_condition.notify_all()

    def nack(self, item):
        """
        Negative acknowledge an item.
        """
        pqid = self._get_pqid(item)
        if pqid:
            self._update_status(pqid, AckStatus.READY)
            with self.task_done_condition:
                self._unacked_count -= 1
                self._ready_count += 1
                self.task_done_condition.notify_all()

    def ack_failed(self, item):
        """
        Acknowledge an item as failed.
        """
        pqid = self._get_pqid(item)
        if pqid:
            self._update_status(pqid, AckStatus.FAILED)
            with self.task_done_condition:
                self._unacked_count -= 1
                self._failed_count += 1
                self.task_done_condition.notify_all()

    def task_done(self):
        """
        This method is deprecated and does nothing.
        """
        pass

    def qsize(self):
        """
        Return the approximate size of the queue.
        """
        return self._ready_count

    def empty(self):
        """
        Return True if the queue is empty, False otherwise.
        """
        return self._ready_count == 0

    def unacked_size(self):
        """
        Return the approximate number of unacked items.
        """
        return self._unacked_count

    def acked_size(self):
        """
        Return the approximate number of acked items.
        """
        return self._acked_count

    def failed_size(self):
        """
        Return the approximate number of failed items.
        """
        return self._failed_count

    def total_size(self):
        """
        Return the approximate total number of items.
        """
        return self._total

    def clear(self):
        """
        Clear the queue.
        """
        sql = "DELETE FROM `{}`".format(self.name)
        self._cursor.execute(sql)
        self.commit()
        with self.task_done_condition:
            self._unacked_count = 0
            self._total = 0
            self._acked_count = 0
            self._failed_count = 0
            self._ready_count = 0
            self.task_done_condition.notify_all()

    def join(self):
        """
        Blocks until all items in the queue have been gotten and processed.
        """
        with self.task_done_condition:
            while self._unacked_count > 0 or self._ready_count > 0:
                self.task_done_condition.wait()

    def commit(self):
        """
        Commit the current transaction.
        """
        self._conn.commit()

    def close(self):
        """
        Close the queue.
        """
        self._conn.close()

    def __del__(self):
        """
        Destructor.
        """
        self.close()

    def __enter__(self):
        """
        Context manager enter.
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Context manager exit.
        """
        self.close()

    def __len__(self):
        """
        Return the number of items in the queue.
        """
        return self.qsize()

    def __repr__(self):
        """
        Return the representation of the queue.
        """
        return "SQLiteAckQueue(path={}, name={}, multithreading={})".format(
            self.path, self.name, self.multithreading
        )