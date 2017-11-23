import boto3
import mido
from config import Config as config
import os
import uuid
import json
import base64
import glob
import shutil
import redis
from utils import job_info_template, job_complete_template
from utils import job_error_template, job_running_template
from utils import update_progress
import random

"""
Constants
"""
DEFAULT_MIDI_TEMPO = 500000  # 120 beats per minute

def _update_job_event(_context, data):
    """
        Helper function to serialize JSON
        and make sure redis doesnt messup JSON validation
    """
    redis_conn = _context['redis_conn']
    response_channel = _context['response_channel']
    data['data_sequence_no'] = _context['data_sequence_no']

    redis_conn.rpush(response_channel, json.dumps(data))


def get_boto_client():
    s3 = boto3.client(
            's3',
            aws_access_key_id=config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY
            )
    return s3


def download_midi(_context, filekey):
    filename = filekey.split("/")[-1]
    # Create a directory for the said submission
    local_directory_path = "{}/{}".format(
                                            config.TEMP_STORAGE_DIRECTORY_PATH,
                                            filename
                                            )
    local_filepath = "{}/submission.midi".format(local_directory_path)

    try:
        os.mkdir(local_directory_path)
    except OSError:
        # directory exists
        pass

    # Download MIDI to tempfolder
    s3 = get_boto_client()

    s3.download_file(
                    config.AWS_S3_BUCKET,
                    filekey,
                    local_filepath
                    )
    return local_directory_path, local_filepath


def load_and_validate_midi(_context, filepath):
    midi = mido.MidiFile(filepath)
    length = midi.length
    ticks_per_beat = midi.ticks_per_beat

    # Assert midi length +/- 10 seconds of MIDI_MAX_LENGTH (3600)
    if abs(config.MIDI_MAX_LENGTH - length) > 10:
        _error = """ The submitted midi file has {} ticks per beat, and at
        120 bpm its length is {} seconds. The grader accepts midi files of
        a total length of 3600 seconds at 120 bpm.
        """.format(ticks_per_beat, length)
        raise Exception(_error)

    if len(midi.tracks) != 1:
        _error = """ The submitted midi file has {} tracks. While the grader
        accepts only Type 0 midi files with a single track. Please submit
        single track midi files, or merge all the tracks into a single track.
        """.format(len(midi.tracks))

        raise Exception(_error)

    return midi, length


def split_midi_into_chunks(_context, midifile, track_length, target_directory):
    cumulative_ticks = 0
    cumulative_time = 0
    relative_time = 0
    track_index = 0
    SPLITS = []
    for _ in range(config.MIDI_NUM_SPLITS):
        SPLITS.append(mido.MidiTrack())

    for _message in midifile.tracks[0]:
        cumulative_ticks += _message.time
        delta_s = mido.tick2second(
                    _message.time,
                    midifile.ticks_per_beat,
                    DEFAULT_MIDI_TEMPO
                    )

        if random.randint(0, 100) < 5:
            """
                Report progress with a probability of 5%
            """
            progress_step_offset = 0
            progress_step_weight = 0.33
            percent_complete = (cumulative_time * 1.0 / track_length) * 100
            update_progress(
                _context,
                (progress_step_offset + (progress_step_weight * percent_complete))
                )

        cumulative_time += delta_s
        relative_time += delta_s
        if not _message.is_meta:
            SPLITS[track_index].append(_message.copy())
        else:
            """
            Ignore all meta messages
            """
            pass

        if relative_time >= (track_length*1.0/config.MIDI_NUM_SPLITS):
            relative_time = 0
            track_index += 1

    _update_job_event(
        _context,
        job_info_template(
            _context, "Saving split chunks..."))

    split_file_paths = []
    split_length_sum = 0
    # Write split files into target_directory
    for _idx, _track in enumerate(SPLITS):
        _m = mido.MidiFile()
        _m.ticks_per_beat = midifile.ticks_per_beat
        _m.tracks.append(_track)
        split_length_sum += _m.length
        target_file_path = "{}/{}.midi".format(
            target_directory,
            str(uuid.uuid4())
            )
        _m.save(target_file_path)
        split_file_paths.append(target_file_path)
        progress_step_offset = 33
        progress_step_weight = 0.25
        percent_complete = (_idx * 1.0 / len(SPLITS)) * 100
        update_progress(
            _context,
            (progress_step_offset + (progress_step_weight * percent_complete))
            )


    return split_file_paths

def convert_midi_files_to_json(_context, filelist, pruned_filekey):
    converted_files = []
    for _idx, _file in enumerate(filelist):
        f = open(_file, "r")
        data = f.read()
        f.close()
        encoded_data = base64.b64encode(data)
        _d = {}
        _d['dataUri'] = "data:audio/midi;base64,"+encoded_data
        _d['_idx'] = _idx
        _d['key'] = pruned_filekey
        new_filepath = _file.replace(".midi", ".json")
        f = open(new_filepath, "w")
        f.write(json.dumps(_d))
        f.close()
        os.remove(_file)
        if not new_filepath.endswith("submission.json"):
            converted_files.append(
                new_filepath.replace(
                    config.TEMP_STORAGE_DIRECTORY_PATH, "")
                    )

        progress_step_offset = 33 + 25
        progress_step_weight = 0.12
        percent_complete = (_idx * 1.0 / len(filelist)) * 100
        update_progress(
            _context,
            (progress_step_offset + (progress_step_weight * percent_complete))
            )

    """
    These filekeys are relative to the `S3_UPLOAD_PATH` in the bucket
    and the first item of the returned array is the main submission file.
    """
    return [pruned_filekey+'/submission.json'] + converted_files


def upload_processed_files_to_s3(_context, local_directory_path, pruned_filekey):
    directory_key = config.S3_UPLOAD_PATH + "/" + pruned_filekey + "/"

    s3 = get_boto_client()

    # Create directory
    s3.put_object(
        ACL='public-read',
        Bucket=config.AWS_S3_BUCKET,
        Key=directory_key
    )

    files = glob.glob(local_directory_path+"/*")
    for _idx, _file in enumerate(files):
        filename = _file.split("/")[-1]
        file_key = directory_key + filename
        resp = s3.put_object(
            ACL='public-read',
            Bucket=config.AWS_S3_BUCKET,
            Key=file_key,
            Body=open(_file).read()
        )
        progress_step_offset = 33 + 25 + 12
        progress_step_weight = (100 - (33 + 25 + 12))/100.0
        percent_complete = (_idx * 1.0 / len(files)) * 100
        update_progress(
            _context,
            (progress_step_offset + (progress_step_weight * percent_complete))
            )


def register_submission_on_redis(
                _context,
                redis_pool,
                submission_id,
                pruned_filekey,
                split_file_keys
                ):
    redis_conn = redis.Redis(connection_pool=redis_pool)
    def _query(s):
        return "{}::{}".format(config.redis_namespace, s)
    # Map submission_id to pruned_filekey
    redis_conn.hset(
        _query("submission_to_key_map"),
        submission_id,
        pruned_filekey)

    # Map pruned_filekey to submission_id
    redis_conn.hset(
        _query("key_to_submission_map"),
        pruned_filekey,
        submission_id)

    # Store submission to filekey mappings
    redis_conn.set(
        _query(
            "split_files::{}".format(submission_id)
            ),
        json.dumps(split_file_keys))



def post_process_midi(_context, redis_pool, filekey):
    """
        Helper file to post process midi file
    """
    local_directory_path, local_filepath = download_midi(_context, filekey)

    """
    # Load and validate midi file
    """
    _update_job_event(
        _context,
        job_info_template(
            _context, "Validating MIDI file..."))

    midi, track_length = load_and_validate_midi(_context, local_filepath)

    _update_job_event(
        _context,
        job_info_template(
            _context, "MIDI file validated..."))

    """
    # Split midi file into NUMBER_OF_PARTS (180)
    """
    _update_job_event(
        _context,
        job_info_template(
            _context, "Splitting file into 120 chunks of ~30 seconds each..."))

    split_file_paths = split_midi_into_chunks(
        _context,
        midi,
        track_length,
        local_directory_path
        )

    """
    # Convert midi files to dataURI
    """
    _update_job_event(
        _context,
        job_info_template(
            _context, "Encoding individual chunks..."))
    pruned_filekey = filekey.split("/")[-1]
    converted_filekeys = convert_midi_files_to_json(
                    _context,
                    [local_filepath]+split_file_paths,
                    pruned_filekey
                    )

    """
    # Upload to target directory on S3
    """
    _update_job_event(
        _context,
        job_info_template(
            _context, "Saving encoded chunks..."))
    upload_processed_files_to_s3(_context, local_directory_path, pruned_filekey)

    """
    # Clean up
    """
    _update_job_event(
        _context,
        job_info_template(
            _context, "Cleaning up..."))

    shutil.rmtree(local_directory_path)
    # Add relevant entries in redis queues

    return pruned_filekey, converted_filekeys
