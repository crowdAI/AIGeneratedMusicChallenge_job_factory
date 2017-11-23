import boto3
import mido
from config import Config as config
import os
import uuid
import json
import base64
import glob
import shutil

"""
Constants
"""
DEFAULT_MIDI_TEMPO = 500000  # 120 beats per minute


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


def load_and_validate_midi(filepath):
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


def split_midi_into_chunks(midifile, track_length, target_directory):
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
        print "Processed {}%".format(cumulative_time*1.0/track_length * 100)

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

    print "Saving Split midi files...."
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
        print "Saved split midi file : ", target_file_path
        split_file_paths.append(target_file_path)

    print "Total length : ", track_length, " Split lenght sum : ", split_length_sum
    return split_file_paths

def convert_midi_files_to_json(filelist, pruned_filekey):
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
        print "Writing JSON file....", _file
        print "Cleaning up old file..."
        os.remove(_file)


def upload_processed_files_to_s3(_context, local_directory_path, pruned_filekey):
    directory_key = config.S3_UPLOAD_PATH + "/" + pruned_filekey + "/"

    s3 = get_boto_client()

    # Create directory
    s3.put_object(
        ACL='public-read',
        Bucket=config.AWS_S3_BUCKET,
        Key=directory_key
    )

    for _file in glob.glob(local_directory_path+"/*"):
        filename = _file.split("/")[-1]
        file_key = directory_key + filename
        resp = s3.put_object(
            ACL='public-read',
            Bucket=config.AWS_S3_BUCKET,
            Key=file_key,
            Body=open(_file).read()
        )
        print resp
        print "Uploaded ", _file


def post_process_midi(_context, redis_pool, filekey):
    """
        Helper file to post process midi file
    """

    local_directory_path, local_filepath = download_midi(_context, filekey)
    # Load and validate midi file
    midi, track_length = load_and_validate_midi(local_filepath)
    # Split midi file into NUMBER_OF_PARTS (180)
    split_file_paths = split_midi_into_chunks(
        midi,
        track_length,
        local_directory_path
        )
    # Convert midi files to dataURI
    pruned_filekey = filekey.split("/")[-1]
    convert_midi_files_to_json([local_filepath]+split_file_paths, pruned_filekey)
    # Upload to target directory on S3
    upload_processed_files_to_s3(_context, local_directory_path, pruned_filekey)
    # Clean up
    shutil.rmtree(local_directory_path)
    # Add relevant entries in redis queues
    # TODO
