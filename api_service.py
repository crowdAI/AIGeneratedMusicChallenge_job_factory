from flask import Flask, request
from flask.json import jsonify
from flask_cors import CORS
import redis
import random
import json
import uuid
import trueskill

from config import Config as config

app = Flask(__name__)
CORS(app)

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
    return random_split, random_split_index

def get_url_for_split(split_rel_path):
    return "{}{}".format(config.S3_BASE_URL, split_rel_path)

@app.route('/match')
def match():
    redis_conn = redis.Redis(connection_pool=POOL)
    #Obtain list of submission_ids
    sub_1, sub_2 = get_two_random_submissions(redis_conn)
    split_1, split_1_idx = get_random_split_for_submission(redis_conn, sub_1)
    split_2, split_2_idx = get_random_split_for_submission(redis_conn, sub_2)

    print split_1, split_2
    split_1 = get_url_for_split(split_1)
    split_2 = get_url_for_split(split_2)

    match_id = str(uuid.uuid4())

    redis_conn.set(
        _query("match::"+match_id),
        json.dumps({
            "submission_1": sub_1,
            "candidate_1": split_1,
            "candidate_1_idx": split_1_idx,
            "submission_2": sub_2,
            "candidate_2": split_2,
            "candidate_2_idx": split_2_idx
        }),
        config.MATCH_EXPIRY)
    _response = {}
    _response['match_id'] = match_id
    _response['candidate_1'] = split_1
    _response['candidate_2'] = split_2

    return jsonify(_response)

def parse_rating(score):
    if not score :
        score = trueskill.Rating()
    else:
        score = json.loads(score)
        _ = trueskill.Rating(
            mu=score['mu'],
            sigma=score['sigma'])

        score = _
    return score

def get_submission_score(submission_id):
    redis_conn = redis.Redis(connection_pool=POOL)
    score = redis_conn.hget(
        _query("submission_scores"),
        submission_id
    )
    return parse_rating(score)


def update_submission_score(submission_id, score):
    redis_conn = redis.Redis(connection_pool=POOL)
    _score = {}
    _score['mu'] = score.mu
    _score['sigma'] = score.sigma
    score_string = json.dumps(_score)
    score = redis_conn.hset(
        _query("submission_scores"),
        submission_id,
        score_string
    )

    # Increase submission_id match count
    redis_conn.hincrby(
        _query("submission_match_counts"),
        submission_id,
        1
    )

    # TODO Add interaction with crowdAI here

@app.route('/match/<match_id>', methods=['POST'])
def match_result(match_id):
    content = request.get_json(silent=True)
    redis_conn = redis.Redis(connection_pool=POOL)

    winner = content["winner"]
    assert winner in [0, 1]

    match = redis_conn.get(
                    _query("match::"+match_id))
    if match:
        match = json.loads(match)
        submission_1 = match['submission_1']
        submission_2 = match['submission_2']

        submission_1_score = get_submission_score(submission_1)
        submission_2_score = get_submission_score(submission_2)

        if winner == 0:
            n_sub_1_score, n_sub_2_score = \
                        trueskill.rate_1vs1(
                            submission_1_score,
                            submission_2_score
                            )
        else:
            n_sub_2_score, n_sub_1_score = \
                        trueskill.rate_1vs1(
                            submission_2_score,
                            submission_1_score
                            )

        update_submission_score(submission_1, n_sub_1_score)
        update_submission_score(submission_2, n_sub_2_score)
        return jsonify({'result':'SUCCESS', 'message': 'Scores updated'})
    else:
        return jsonify({'result': 'ERROR', 'message':'invalid match_id'})
    print match
    print content
    return jsonify({'match_id': match_id})


if __name__ == '__main__':
    app.run(host='0.0.0.0',
            port=config.api_service_port,
            debug=config.DEBUG_MODE
            )
