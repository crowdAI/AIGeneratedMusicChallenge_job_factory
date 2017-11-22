import boto3
import mido


def post_process_midi(_context, redis_pool, filekey):
    """
        Helper file to post process midi file
    """
    filename = filekey.split("/")[-1]
    # Download MIDI to tempfolder
    

    # Split midi file into NUMBER_OF_PARTS (180)

    # Convert midi files to dataURI
    ## Prepare relevant json file

    # Upload to target directory on S3

    # Clean up

    # Add relevant entries in redis queues



foo = mido
foo = boto3
