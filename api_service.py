from flask import Flask
from flask_restful import Resource, Api
import redis
import random
import json
import uuid

from config import Config as config

app = Flask(__name__)
api = Api(app)

POOL = redis.ConnectionPool(
    host=config.redis_host, port=config.redis_port, db=config.redis_db)

def _query(s):
    return "{}::{}".format(config.redis_namespace, s)

def get_two_random_submissions(redis_conn):
    submission_ids = redis_conn.hkeys(
        _query("submission_to_key_map"
        ))
    assert len(submission_ids) >= 2

    """
    Do a random sampling of all submissions
    to obtain two submissions
    """
    random.shuffle(submission_ids)
    sub_1 = submission_ids[0]
    sub_2 = submission_ids[1]

    return sub_1, sub_2

def get_random_split_for_submission(redis_conn, submission_id):
    splits = redis_conn.get(
                        _query(
                            "split_files::{}".format(submission_id)
                        ))
    # Ignore the first split (submission.json)
    splits = json.loads(splits)[1:]
    random_split_index = random.randint(0, len(splits)-1)
    random_split = splits[random_split_index]
    return random_split

def get_url_for_split(split_rel_path):
    return "{}{}".format(config.S3_BASE_URL, split_rel_path)

class Match(Resource):
    def get(self):
        redis_conn = redis.Redis(connection_pool=POOL)
        #Obtain list of submission_ids
        sub_1, sub_2 = get_two_random_submissions(redis_conn)
        split_1 = get_random_split_for_submission(redis_conn, sub_1)
        split_2 = get_random_split_for_submission(redis_conn, sub_2)

        print split_1, split_2
        split_1 = get_url_for_split(split_1)
        split_2 = get_url_for_split(split_2)

        match_id = str(uuid.uuid4())

        _response = {}
        _response['match_id'] = match_id
        _response['candidate_1'] = split_1
        _response['candidate_2'] = split_2

        return _response

    def put(self, match_id):
        return {'match_id': match_id}


api.add_resource(Match, '/match')
if __name__ == '__main__':
    app.run(host='0.0.0.0',
            port=config.api_service_port,
            debug=config.DEBUG_MODE
            )
