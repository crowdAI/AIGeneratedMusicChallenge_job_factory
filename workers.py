from config import Config as config
from utils import job_info_template, job_complete_template
from utils import job_error_template, job_running_template

import redis
from rq import get_current_job
import json
import requests
from midi_helpers import post_process_midi, _update_job_event
from midi_helpers import register_submission_on_redis

import uuid

if config.redis_password:
	POOL = redis.ConnectionPool(
	    host=config.redis_host, port=config.redis_port, db=config.redis_db, password=config.redis_password)
else:
	POOL = redis.ConnectionPool(
	    host=config.redis_host, port=config.redis_port, db=config.redis_db)

def report_to_crowdai(_context, status, _payload):
    if config.DEBUG_MODE:
        return str(uuid.uuid4())

    headers = {
        'Authorization': 'Token token='+config.CROWDAI_TOKEN,
        "Content-Type": "application/vnd.api+json"
        }
    _payload['challenge_client_name'] = config.challenge_id
    _payload['api_key'] = _context['api_key']
    _payload['grading_status'] = status
    print "Making POST request...."
    r = requests.post(
        config.CROWDAI_GRADER_URL,
        params=_payload, headers=headers, verify=False)

    if r.status_code == 202:
        data = json.loads(r.text)
        submission_id = str(data['submission_id'])
        return submission_id
    else:
		_message = """
            Unable to register submission on crowdAI.
            Please contact the admins."""
		try:
			response = json.loads(r.text)
			_message = response['message']
		except:
			pass
		raise Exception(_message)

def grade_submission(data, _context):
    file_key = data["file_key"]

    _update_job_event(
        _context,
        job_info_template(
            _context, "Post Processing  MIDI file...."))

    pruned_filekey, converted_filekeys = post_process_midi(
                                            _context,
                                            POOL,
                                            file_key
                                            )
    _payload = {}
    _meta = {}
    _meta['file_key'] = file_key
    processed_filekeys = converted_filekeys
    _meta['processed_filekeys'] = json.dumps(processed_filekeys)
    _payload['meta'] = json.dumps(_meta)
    _payload['score'] = config.SCORE_DEFAULT
    _payload['score_secondary'] = config.SCORE_SECONDARY_DEFAULT

    submission_id = report_to_crowdai(
                    _context,
                    'graded',
                    _payload
                    )
    register_submission_on_redis(
        _context,
        POOL,
        submission_id,
        pruned_filekey,
        processed_filekeys
        )

    message_for_participants = """
    Score (mu) : {}
    Secondary_score (sigma) : {}
    Please note that these scores are only the initial scores,
    and they will change over time as your submission is
    evaluated by the human volunteers.
    """.format(_payload['score'], _payload['score_secondary'])

    _update_job_event(
        _context,
        job_info_template(
            _context, message_for_participants))

    result = {'result': 'submission recorded'}
    result['score_mu'] = _payload['score']
    result['score_sigma'] = _payload['score_secondary']
    _update_job_event(
        _context,
        job_complete_template(
            _context,
            result
            )
        )

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
