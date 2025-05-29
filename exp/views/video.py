import base64
import hashlib
import hmac
import json

from botocore.exceptions import ClientError
from django.conf import settings
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    HttpResponseNotFound,
)
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

        key = settings.PIPE_WEBHOOK_KEY

        try:
            # Authenticate the webhook (see https://addpipe.com/docs#authenticating-webhooks)
            # Append the JSON POST data received via webhook to the URL string.
            thisURL = request.scheme + "://" + request.headers["host"] + request.path
            payload = request.POST.get("payload")
            message = thisURL + payload
            # Hash the resulting string with HMAC-SHA1, using the webhook authentication key; generate binary signature.
            keyBytes = bytes(key, "UTF-8")
            messageBytes = bytes(message, "UTF-8")
            digester = hmac.new(keyBytes, messageBytes, hashlib.sha1)
            signatureBinary = digester.digest()
            # Base64 encode the binary signature.
            signatureComputed = base64.b64encode(signatureBinary)
            # Compare to the one in the header
            signatureSent = bytes(request.headers["x-pipe-signature"], "UTF-8")
            authenticated = signatureComputed == signatureSent

            # Convert data from string representation of dict to dict
            payload_data = json.loads(payload)

            if authenticated and (
                payload_data["data"]["s3UploadStatus"] == "upload success"
            ):  # Go ahead and move the file
                new_name = payload_data["data"]["payload"]

                if not new_name:  # Make sure we don't have an empty payload string
                    return HttpResponseForbidden()

                try:
                    video_obj = Video.from_pipe_payload(payload_data)
                    return HttpResponse(
                        (
                            payload_data["data"]["videoName"]
                            + " --> "
                            + video_obj.filename
                        )
                        if video_obj
                        else "Preview video not saved"
                    )
                except ClientError as e:
                    return HttpResponseNotFound(e)

            else:  # Not authenticated
                return HttpResponseForbidden()

        except KeyError as e:
            return HttpResponseBadRequest(f"Missing expected header or field: {str(e)}")
