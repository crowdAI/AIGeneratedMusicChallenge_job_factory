import json
from events import CrowdAIEvents

def response_template(data_sequence_no, job_id):
    _message = {}
    _message["job_id"] = job_id
    _message["data_sequence_no"] = data_sequence_no
    _message["response_type"] = None
    _message["data"] = {}
    _message["message"] = ""

    return _message

def job_enqueud_template(data_sequence_no, job_id):
    response = response_template(data_sequence_no, job_id)
    response["response_type"] = CrowdAIEvents.Job["ENQUEUED"]
    return response

def job_running_template(data_sequence_no, job_id):
    response = response_template(data_sequence_no, job_id)
    response["response_type"] = CrowdAIEvents.Job["RUNNING"]
    return response

def job_error_template(data_sequence_no, job_id, message=""):
    response = response_template(data_sequence_no, job_id)
    response["response_type"] = CrowdAIEvents.Job["ERROR"]
    response["message"] = message
    return response

def job_progress_update(context, progress_object, message=""):
    response = response_template(context['data_sequence_no'], context['job_id'])
    response["response_type"] = CrowdAIEvents.Job["PROGRESS_UPDATE"]
    response["data"] = progress_object
    response["message"] = message
    return response

def job_complete_template(context, result, message=""):
    response = response_template(context['data_sequence_no'], context['job_id'])
    response["response_type"] = CrowdAIEvents.Job["COMPLETE"]
    response["data"] = result
    response["message"] = message
    return response

def job_info_template(context, message=""):
    response = response_template(context['data_sequence_no'], context['job_id'])
    response["response_type"] = CrowdAIEvents.Job["INFO"]
    response["message"] = message
    return response

# TODO: Refactor all job events to use context instead
def update_progress(context, percent_complete, message=""):
        #Register Progress
        _progress_update = {}
        _progress_update["percent_complete"] = percent_complete
        _progress_update["message"] = message
        _progress_update["data_sequence_no"] = context["data_sequence_no"]
        context['redis_conn'].rpush(context['response_channel'], json.dumps(job_progress_update(context, _progress_update, _progress_update["message"])))
