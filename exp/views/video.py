import ast
import base64
import hashlib
import hmac
import urllib.parse

from botocore.exceptions import ClientError
from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseNotFound
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from studies.models import Video


class RenameVideoView(View):
    """
    Webhook handler for Pipe webhook that fires upon uploading to S3, so we can rename
    video to the intended permanent name instead of the random string assigned by Pipe.
    """

    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super(RenameVideoView, self).dispatch(request, *args, **kwargs)

    def post(self, request):
        # Parse the POST body ourselves to allow flexibility for using for other types
        # of events in the future; some of the Pipe event data includes semicolons which
        # throw the automatic parsing for a loop.
        rawbody = list(request.body)  # bytes to ints
        # rawbody = [45 if i==59 else i for i in rawbody] # semicolons -> dashes
        postbody = urllib.parse.parse_qs(
            bytes(rawbody).decode("utf-8")
        )  # NOW parse the request string

        # Authenticate the webhook (see https://addpipe.com/docs#authenticating-webhooks)
        key = settings.PIPE_WEBHOOK_KEY
        # Append the JSON POST data received via webhook to the URL string.
        thisURL = request.scheme + "://" + request.META["HTTP_HOST"] + request.path
        message = thisURL + postbody["payload"][0]  # TODO
        key = bytes(key, "UTF-8")
        message = bytes(message, "UTF-8")
        # Hash the resulting string with HMAC-SHA1, using the webhook authentication key; generate binary signature.
        digester = hmac.new(key, message, hashlib.sha1)
        signatureBinary = digester.digest()
        # Base64 encode the binary signature.
        signatureComputed = base64.b64encode(signatureBinary)
        # Compare to the one in the header
        signatureSent = bytes(request.META["HTTP_X_PIPE_SIGNATURE"], "UTF-8")
        authenticated = signatureComputed == signatureSent

        d = ast.literal_eval(
            postbody["payload"][0]
        )  # convert from string representation of dict

        if authenticated and (
            d["data"]["s3UploadStatus"] == "upload success"
        ):  # Go ahead and move the file
            new_name = d["data"]["payload"]

            if not new_name:  # Make sure we don't have an empty payload string
                return HttpResponseForbidden()

            try:
                video_obj = Video.from_pipe_payload(d)
                return HttpResponse(
                    (d["data"]["videoName"] + " --> " + video_obj.filename)
                    if video_obj
                    else "Preview video not saved"
                )
            except ClientError as e:
                return HttpResponseNotFound(e)

        else:  # Not authenticated
            return HttpResponseForbidden()
