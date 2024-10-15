import logging

import boto3
from botocore.exceptions import ClientError
from django.conf import settings

logger = logging.getLogger(__name__)

S3_CLIENT = boto3.client("s3")


def get_all_study_attachments(study_uuid):
    """
    Get all video responses to a study by fetching all objects in the bucket with
    key name videoStream_<study_uuid>
    """
    s3 = boto3.resource("s3")
    bucket = s3.Bucket(settings.BUCKET_NAME)
    return bucket.objects.filter(Prefix=f"videoStream_{study_uuid}")


def get_url(
    video_key, recording_method_is_pipe, study_type_is_jspsych, set_attachment_header
):
    """
    Generate a presigned url for the video that expires in 10 minutes.
    """
    url = None
    if study_type_is_jspsych:
        # jsPsych bucket
        bucket = settings.JSPSYCH_S3_BUCKET
    else:
        # EFP
        if recording_method_is_pipe:
            # Pipe bucket
            bucket = settings.BUCKET_NAME
        else:
            # RecordRTC bucket
            bucket = settings.S3_BUCKET_NAME

    params = {"Bucket": bucket, "Key": video_key}
    if set_attachment_header:
        params["ResponseContentDisposition"] = "attachment"

    try:
        url = S3_CLIENT.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=600,
        )
    except ClientError as e:
        logger.warning(f"Video {video_key} not found in bucket. {e}")
        return None

    return url


def get_study_attachments(study, orderby="key", match=None):
    """
    Fetches study attachments from s3
    """
    sort = "created_at" if "created_at" in orderby else "key"
    attachments = [
        att
        for att in get_all_study_attachments(str(study.uuid))
        if "PREVIEW_DATA_DISREGARD" not in att.key
    ]
    if match:
        attachments = [att for att in attachments if match in att.key]
    return sorted(
        attachments,
        key=lambda x: getattr(x, sort),
        reverse=True if "-" in orderby else False,
    )


def rename_stored_video(old_name, new_name, ext):
    """
    Renames a stored video on S3. old_name and new_name are both without extension ext.
    Returns 1 if success, 0 if old_name video did not exist. May throw error if
    other problems encountered.

    "url":"https://bucketname.s3.amazonaws.com/vs1457013120534_862.mp4",
    "snapshotUrl":"https://bucketname.s3.amazonaws.com/vs1457013120534_862.jpg",
    """
    s3 = boto3.resource("s3")
    old_name_full = old_name + "." + ext
    old_name_thum = old_name + ".jpg"
    new_name_full = new_name + "." + ext

    # No way to directly rename in boto3, so copy and delete original (this is dumb, but let's get it working)
    try:  # Create a copy with the correct new name, if the original exists. Could also
        # wait until old_name_full exists using orig_video.wait_until_exists()
        s3.Object(settings.BUCKET_NAME, new_name_full).copy_from(
            CopySource=(settings.BUCKET_NAME + "/" + old_name_full)
        )
    except ClientError:  # old_name_full not found!
        return False
    else:  # Go on to remove the originals
        orig_video = s3.Object(settings.BUCKET_NAME, old_name_full)
        orig_video.delete()
        # remove the .jpg thumbnail.
        s3.Object(settings.BUCKET_NAME, old_name_thum).delete()

    return True
