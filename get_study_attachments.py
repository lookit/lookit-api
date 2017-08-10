import sys
import boto3

BUCKET_NAME = 'mitLookit'

def get_all_study_attachments(study_uuid):
    s3 = boto3.resource('s3')

    bucket = s3.Bucket(BUCKET_NAME)
    study_files = []
    for key in bucket.objects.filter(Prefix=f'videoStream_{study_uuid}'):
        study_files.append(key.key)
    return study_files

if __name__ == '__main__':
    study_uuid = sys.argv[1]
    get_study_keys(study_uuid)
