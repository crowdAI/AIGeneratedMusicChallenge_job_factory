#!/usr/bin/env python

from config import Config as config
from job_states import JobStates
from utils import *

import redis
from rq import Queue

import threading
import signal
import sys
import json

import os

dir_path = os.path.dirname(os.path.realpath(__file__))
sys.path.append(dir_path)

def signal_handler(signal, frame):
        sys.exit(0)
signal.signal(signal.SIGINT, signal_handler)

import json

from workers import job_execution_wrapper

POOL = redis.ConnectionPool(host=config.redis_host, port=config.redis_port, db=config.redis_db)
r = redis.Redis(connection_pool=POOL)
JOB_QUEUE = Queue(connection=r)
#Listen to BRPOP events
enqueue_channel = config.redis_namespace+'::enqueue_job'
redis_conn = redis.Redis(connection_pool=POOL)
while True:
    channel, data = redis_conn.brpop(enqueue_channel)
    data = json.loads(data)
    job = JOB_QUEUE.enqueue(job_execution_wrapper, data)
    # TODO: Validate the data before working on it
    print "Enqueueing Job : ", data
    redis_conn.rpush(data["broker_response_channel"], json.dumps(job_enqueud_template(data["data_sequence_no"], job.id)))
