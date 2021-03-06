from flask import Flask, request
from flask.json import jsonify
from flask_cors import CORS
import redis
import random
import json
import uuid
import trueskill
import requests
from trueskill.backends import cdf
import math
import time

from config import Config as config

app = Flask(__name__)
CORS(app)

if config.redis_password:
        POOL = redis.ConnectionPool(
            host=config.redis_host, port=config.redis_port, db=config.redis_db, password=config.redis_password)
else:
        POOL = redis.ConnectionPool(
            host=config.redis_host, port=config.redis_port, db=config.redis_db)

def _query(s):
    return "{}::{}".format(config.redis_namespace, s)

def get_two_random_submissions(redis_conn, excluded_submissions=[]):
    submission_ids = redis_conn.hkeys(
        _query("submission_to_key_map"
        ))
    assert len(submission_ids) >= 2

    """
    Do a random sampling of all submissions
    to obtain two submissions
    """
    random.shuffle(submission_ids)
    def get_random_submission(submission_ids, _excluded_submissions):
        while True:
            _i = random.randint(0, len(submission_ids)-1)
            if str(submission_ids[_i]) in _excluded_submissions:
                continue
            else:
                return submission_ids[_i]

    sub_1 = get_random_submission(submission_ids, excluded_submissions)
    sub_2 = get_random_submission(submission_ids, excluded_submissions+[sub_1])
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

def anonymize_response_candidate(candidate):
    redis_conn = redis.Redis(connection_pool=POOL)
    new_internal_id = str(uuid.uuid4())+".json"
    r = requests.get(candidate)
    payload = json.loads(r.text)
    payload["key"] = str(uuid.uuid4())

    redis_conn.set(
        _query("candidate::"+new_internal_id),
            json.dumps(
                payload
            ),
        config.MATCH_EXPIRY
        )

    return "https://grader.crowdai.org/music_candidate/"+new_internal_id


@app.route('/music_candidate/<internal_id>')
def music_candidate(internal_id):
    redis_conn = redis.Redis(connection_pool=POOL)
    candidate = redis_conn.get(
        _query("candidate::"+internal_id)
    )
    redis_conn.delete(_query("candidate::"+internal_id))
    print json.loads(candidate)
    return jsonify(json.loads(candidate))

@app.route('/match')
def match():
    redis_conn = redis.Redis(connection_pool=POOL)
    #Obtain list of submission_ids
    sub_1, sub_2 = get_two_random_submissions(redis_conn, excluded_submissions=config.BANNED_SUBMISSIONS)
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
    _response['candidate_1'] = anonymize_response_candidate(split_1)
    _response['candidate_2'] = anonymize_response_candidate(split_2)
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

def get_submission_score(submission_id, _idx=False):
    _key = "submission_scores"
    if _idx:
        """
            Granular mode. Where we also try to compute the true skill of
            all individual clips
        """
        _key += "___granular"
        submission_id += "___" + str(_idx)
    redis_conn = redis.Redis(connection_pool=POOL)
    score = redis_conn.hget(
        _query(_key),
        submission_id
    )
    return parse_rating(score)

def report(submission_id, _payload=False):
    print("Reporting payload for submission_id {}".format(submission_id))
    print(_payload)
    headers = {'Authorization' : 'Token token='+config.CROWDAI_TOKEN , "Content-Type":"application/vnd.api+json"}
    r = requests.patch("{}/{}".format(
                            config.CROWDAI_GRADER_URL,
                            submission_id
                        ),
                        params=_payload,
                        headers=headers,
                        verify=False)
    if r.status_code != 202:
        print "ERROR :("
        print(r.text)
        print(r.status_code)
        #raise Exception("Unusual behaviour in crowdAI API")

def update_submission_score(submission_id, score, _idx=False):
    submission_score_key = "submission_scores"
    submission_count_key = "submission_match_counts"
    if _idx:
        """
            Granular mode. Where we also try to compute the true skill of
            all individual clips
        """
        submission_score_key += "___granular"
        submission_count_key += "___granular"
        submission_id += "___" + str(_idx)

    redis_conn = redis.Redis(connection_pool=POOL)
    _score = {}
    _score['mu'] = score.mu
    _score['sigma'] = score.sigma
    score_string = json.dumps(_score)

    redis_conn.hset(
        _query(submission_score_key),
        submission_id,
        score_string
    )

    # Increase submission_id match count
    updated_count = redis_conn.hincrby(
        _query(submission_count_key),
        submission_id,
        1
    )

    env = trueskill.global_env()
    if not _idx:
        _payload = {}
        _payload['score'] = env.expose(score)
        _payload['score_secondary'] = score.mu
        _payload['grading_status'] = 'graded'
        _payload['challenge_client_name'] = config.challenge_id
        _message = "mu: {} ; sigma: {}; comparisons: {}".format(
                        score.mu,
                        score.sigma,
                        updated_count
                        )
        _payload['grading_message'] = _message
        if not config.DEBUG_MODE:
            report(submission_id, _payload)


@app.route('/match/<match_id>', methods=['POST'])
def match_result(match_id):
    content = request.get_json(silent=True)
    redis_conn = redis.Redis(connection_pool=POOL)

    winner = content["winner"]
    assert winner in [0, 1]

    match = redis_conn.get(
                    _query("match::"+match_id))

    def Pwin(rA=trueskill.Rating(), rB=trueskill.Rating()):
        deltaMu = rA.mu - rB.mu
        rsss = math.sqrt(rA.sigma**2 + rB.sigma**2)
        _prob = cdf(deltaMu/rsss)
        return _prob

    if match:
        match = json.loads(match)
        submission_1 = match['submission_1']
        submission_2 = match['submission_2']
        submission_1_idx = match['candidate_1_idx']
        submission_2_idx = match['candidate_2_idx']

        submission_1_score = get_submission_score(submission_1)
        submission_2_score = get_submission_score(submission_2)

        if winner == 0:
            n_sub_1_score, n_sub_2_score = \
                        trueskill.rate_1vs1(
                            submission_1_score,
                            submission_2_score
                            )
            probability_of_win = Pwin(
                                submission_1_score,
                                submission_2_score
                                )
        else:
            n_sub_2_score, n_sub_1_score = \
                        trueskill.rate_1vs1(
                            submission_2_score,
                            submission_1_score
                            )
            probability_of_win = Pwin(
                                submission_1_score,
                                submission_2_score
                                )

        update_submission_score(submission_1, n_sub_1_score)
        update_submission_score(submission_2, n_sub_2_score)


        """
            Also compute the individual score for individual snippets
        """
        granular_submission_1_score = get_submission_score(submission_1, _idx=submission_1_idx)
        granular_submission_2_score = get_submission_score(submission_2, _idx=submission_2_idx)

        if winner == 0:
            n_sub_1_granular_score, n_sub_2_granular_score = \
                        trueskill.rate_1vs1(
                            granular_submission_1_score,
                            granular_submission_2_score
                            )
        else:
            n_sub_2_granular_score, n_sub_1_granular_score = \
                        trueskill.rate_1vs1(
                            granular_submission_2_score,
                            granular_submission_1_score
                            )

        update_submission_score(submission_1, n_sub_1_score, _idx=submission_1_idx)
        update_submission_score(submission_2, n_sub_2_score, _idx=submission_2_idx)

        # Delete match_hash
        match = redis_conn.delete(
            _query("match::"+match_id)
            )

        ip = False
        if request.headers.getlist("X-Forwarded-For"):
            ip = request.headers.getlist("X-Forwarded-For")[0]
        else:
            ip = request.remote_addr
        # Add log entry
        _log_entry = {}
        _log_entry['timestamp'] = time.time()
        _log_entry['remote_addr'] = ip
        _log_entry['submission_1'] = submission_1
        _log_entry['submission_2'] = submission_2
        _log_entry['submission_1_idx'] = submission_1_idx
        _log_entry['submission_2_idx'] = submission_2_idx
        _log_entry['winner'] = winner

        redis_conn.lpush(
            _query("match_report_logs"),
            json.dumps(_log_entry)
        )
        return jsonify(
                    {
                        'result':'SUCCESS',
                        'message': 'Scores updated',
                        'prob_win': "{0:.2f}% ".format(probability_of_win*100)
                    })
    else:
        return jsonify({'result': 'ERROR', 'message':'invalid match_id'})
    print match
    print content
    return jsonify({'match_id': match_id})

def reset_all_scores():
    redis_conn = redis.Redis(connection_pool=POOL)
    submission_ids = redis_conn.hkeys(
        _query("submission_to_key_map"
        ))

    for sid in submission_ids:
        print sid
        score = trueskill.Rating()
        update_submission_score(sid, score)
        for k in range(120):
            print sid, k
            update_submission_score(sid, score, _idx=k)



application = app
if __name__ == '__main__':
    app.run(host='0.0.0.0',
            port=config.api_service_port,
            debug=config.DEBUG_MODE
            )
