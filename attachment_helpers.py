import sys
import boto3
import botocore
from botocore.exceptions import ClientError
from project import settings


def get_all_study_attachments(study_uuid):
    '''
    Get all video responses to a study by fetching all objects in the bucket with
    key name videoStream_<study_uuid>
    '''
    s3 = boto3.resource('s3')
    bucket = s3.Bucket(settings.BUCKET_NAME)
    return bucket.objects.filter(Prefix=f'videoStream_{study_uuid}')


def get_consent_videos(study_uuid):
        '''
        Get all consent videos for a particular study
        '''
        s3 = boto3.resource('s3')
        bucket = s3.Bucket(settings.BUCKET_NAME)
        return [att for att in bucket.objects.filter(Prefix=f'videoStream_{study_uuid}_1-video-consent') if 'PREVIEW_DATA_DISREGARD' not in att.key]


def get_download_url(video_key):
    '''
    Generate a presigned url for the video that expires in 60 seconds.
    '''
    s3Client = boto3.client('s3')
    return s3Client.generate_presigned_url('get_object', Params = {'Bucket': settings.BUCKET_NAME, 'Key': video_key}, ExpiresIn = 60)


def get_study_attachments(study, orderby='key', match=None):
    '''
    Fetches study attachments from s3
    '''
    sort = 'last_modified' if 'date_modified' in orderby else 'key'
    attachments = [att for att in get_all_study_attachments(str(study.uuid)) if 'PREVIEW_DATA_DISREGARD' not in att.key]
    if match:
        attachments = [att for att in attachments if match in att.key]
    return sorted(attachments, key=lambda x: getattr(x, sort), reverse=True if '-' in orderby else False)

def rename_stored_video(old_name, new_name, ext):
	'''
	Renames a stored video on S3. old_name and new_name are both without extension ext.
	Returns 1 if success, 0 if old_name video did not exist. May throw error if 
	other problems encountered.
	
	"url":"https://bucketname.s3.amazonaws.com/vs1457013120534_862.mp4",
	"snapshotUrl":"https://bucketname.s3.amazonaws.com/vs1457013120534_862.jpg",
	'''
	s3 = boto3.resource('s3')
	old_name_full = old_name + '.' + ext
	old_name_thum = old_name + '.jpg'
	new_name_full = new_name + '.' + ext
	
	# No way to directly rename in boto3, so copy and delete original (this is dumb, but let's get it working)
	try: # Create a copy with the correct new name, if the original exists. Could also
	# wait until old_name_full exists using orig_video.wait_until_exists()
		s3.Object(settings.BUCKET_NAME, new_name_full).copy_from(CopySource=(settings.BUCKET_NAME + '/' + old_name_full))
	except ClientError: # old_name_full not found!
		return False
	else: # Go on to remove the originals
		orig_video = s3.Object(settings.BUCKET_NAME, old_name_full)
		orig_video.delete()
		# remove the .jpg thumbnail.
		s3.Object(settings.BUCKET_NAME, old_name_thum).delete()
	
	return True