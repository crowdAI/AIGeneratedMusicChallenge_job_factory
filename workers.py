from config import Config as config
from utils import job_info_template, job_complete_template
from utils import job_error_template, job_running_template

import redis
from rq import get_current_job
import json
import requests
from midi_helpers import post_process_midi

POOL = redis.ConnectionPool(
    host=config.redis_host, port=config.redis_port, db=config.redis_db)


def grade_submission(data, _context):
    file_key = data["file_key"]
    # Start the download of the file locally to the temp folder
    _update_job_event(
        _context,
        job_info_template(
            _context, "Validating MIDI file...."))

    # TODO: Add validation of MIDI file here
    post_process_midi(_context, POOL, file_key)

    headers = {
        'Authorization': 'Token token='+config.CROWDAI_TOKEN,
        "Content-Type": "application/vnd.api+json"
        }
    _meta = {}
    _meta["file_key"] = file_key
    _payload = {}
    _payload["meta"] = json.dumps(_meta)
    _payload['challenge_client_name'] = config.challenge_id
    _payload['api_key'] = _context['api_key']
    _payload['grading_status'] = 'submitted'
    print "Making POST request...."

    r = requests.post(
        config.CROWDAI_GRADER_URL,
        params=_payload, headers=headers, verify=False)
    print "Status Code : ", r.status_code
    if r.status_code == 202:
        data = json.loads(r.text)
        submission_id = str(data['submission_id'])
        _context['redis_conn'].set(
            config.challenge_id+"::submissions::"+submission_id,
            json.dumps(_payload))

        _context['redis_conn'].lpush(
            config.challenge_id+"::enqueued_submissions",
            "{}".format(submission_id))

        _update_job_event(
            _context,
            job_info_template(
                _context,
                "MESSAGE HERE {}.".format(submission_id)))
        _meta['submission_id'] = submission_id
        _update_job_event(_context, job_complete_template(_context, _meta))
    else:
        raise Exception(r.text)


def _update_job_event(_context, data):
    """
        Helper function to serialize JSON
        and make sure redis doesnt messup JSON validation
    """
    redis_conn = _context['redis_conn']
    response_channel = _context['response_channel']
    data['data_sequence_no'] = _context['data_sequence_no']

    redis_conn.rpush(response_channel, json.dumps(data))


def job_execution_wrapper(data):
    redis_conn = redis.Redis(connection_pool=POOL)
    job = get_current_job()

    _context = {}
    _context['redis_conn'] = redis_conn
    _context['response_channel'] = data['broker_response_channel']
    _context['job_id'] = job.id
    _context['data_sequence_no'] = data['data_sequence_no']
    _context['api_key'] = data['extra_params']['api_key']

    # Register Job Running event
    _update_job_event(
        _context,
        job_running_template(
            _context['data_sequence_no'], job.id))
    result = {}
    try:
        if data["function_name"] == "grade_submission":
            grade_submission(data["data"], _context)
        else:
            _error_object = job_error_template(
                job.id, "Function not implemented error")
            _update_job_event(
                _context, job_error_template(job.id, result))
            result = _error_object
    except Exception as e:
        _error_object = job_error_template(
                            _context['data_sequence_no'],
                            job.id,
                            str(e))
        _update_job_event(_context, _error_object)
    return result
