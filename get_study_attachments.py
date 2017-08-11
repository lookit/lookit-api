import sys
import boto3
import botocore

BUCKET_NAME = 'mitLookit'

def get_all_study_attachments(study_uuid):
    """
    Get all video responses to a study by fetching all objects in the bucket with
    key name videoStream_<study_uuid>
    """
    s3 = boto3.resource('s3')
    bucket = s3.Bucket(BUCKET_NAME)
    return bucket.objects.filter(Prefix=f'videoStream_{study_uuid}')

def get_download_url(video_key):
    """
    Generate a presigned url for the video that expires in 60 seconds.
    """
    s3Client = boto3.client('s3')
    return s3Client.generate_presigned_url('get_object', Params = {'Bucket': BUCKET_NAME, 'Key': video_key}, ExpiresIn = 60)

if __name__ == '__main__':
    study_uuid = sys.argv[1]
    get_study_keys(study_uuid)
