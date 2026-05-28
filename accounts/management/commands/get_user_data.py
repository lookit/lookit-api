import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import connection

# This query generates the following:
# User
#  ├ Child
#  │  └ Response
#  │      ├ Feedback
#  │      ├ Video
#  │      └ ConsentRuling
#  │  └ MessageChildrenOfInterest
#  │      └ Message
#  ├ MessageRecipients
#  │   └ Message
#  └ DemographicData

SQL_QUERY = """
WITH target_user AS (
    SELECT * FROM accounts_user WHERE id = %(user_id)s
),

children AS (
    SELECT * FROM accounts_child WHERE user_id = %(user_id)s
),

responses AS (
    SELECT * FROM studies_response
    WHERE child_id IN (SELECT id FROM children)
),

feedback AS (
    SELECT * FROM studies_feedback
    WHERE response_id IN (SELECT id FROM responses)
),

videos AS (
    SELECT * FROM studies_video
    WHERE response_id IN (SELECT id FROM responses)
),

consent_rulings AS (
    SELECT * FROM studies_consentruling
    WHERE response_id IN (SELECT id FROM responses)
),

demographics AS (
    SELECT * FROM accounts_demographicdata
    WHERE user_id = %(user_id)s
),

messages_to_user AS (
    SELECT m.*
    FROM accounts_message m
    JOIN accounts_message_recipients r
      ON m.id = r.message_id
    WHERE r.user_id = %(user_id)s
),

messages_about_children AS (
    SELECT m.*
    FROM accounts_message m
    JOIN accounts_message_children_of_interest c
      ON m.id = c.message_id
    WHERE c.child_id IN (SELECT id FROM children)
),

messages AS (
    SELECT * FROM messages_to_user
    UNION
    SELECT * FROM messages_about_children
)

SELECT json_build_object(
    'User', (SELECT json_agg(t) FROM target_user t),
    'Child', (SELECT json_agg(c) FROM children c),
    'DemographicData', (SELECT json_agg(d) FROM demographics d),
    'Response', (SELECT json_agg(r) FROM responses r),
    'Feedback', (SELECT json_agg(f) FROM feedback f),
    'Video', (SELECT json_agg(v) FROM videos v),
    'ConsentRuling', (SELECT json_agg(c) FROM consent_rulings c),
    'Message', (SELECT json_agg(m) FROM messages m)
);
"""


class Command(BaseCommand):
    help = "Export objects related to a User and their Children"

    def add_arguments(self, parser):
        parser.add_argument("user_id", type=int)
        parser.add_argument(
            "--summary",
            action="store_true",
            help="Print counts of related objects instead of full export",
        )
        parser.add_argument(
            "--output",
            type=str,
            help="Write export JSON to a file",
        )

    def handle(self, *args, **options):
        user_id = options["user_id"]
        summary = options["summary"]
        output_file = options.get("output")

        with connection.cursor() as cursor:
            cursor.execute(SQL_QUERY, {"user_id": user_id})
            result = cursor.fetchone()[0]

        # normalize nulls
        result = {k: (v or []) for k, v in result.items()}

        if summary:
            self.stdout.write("\nObject counts:\n")
            for table, rows in result.items():
                self.stdout.write(f"{table}: {len(rows)}")
            return

        json_output = json.dumps(result, indent=2, default=str)

        if output_file:
            path = Path(output_file)
            path.write_text(json_output)
            self.stdout.write(f"\nExport written to {path.resolve()}")
        else:
            print(json_output)
