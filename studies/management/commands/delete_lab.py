from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from guardian.models import GroupObjectPermission, UserObjectPermission

from studies.models import Lab

EXPECTED_RELS = {
    ("Study", "lab"),
    ("LabUserObjectPermission", "content_object"),
    ("LabGroupObjectPermission", "content_object"),
}


class Command(BaseCommand):
    help = "Safely delete a Lab and its associated permissions and groups."

    def add_arguments(self, parser):
        parser.add_argument(
            "--uuid", type=str, required=True, help="UUID of the Lab to delete."
        )
        parser.add_argument(
            "--keep-groups",
            action="store_true",
            help="Preserve the Lab's auth Groups after deletion.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview deletion without deleting.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Actually perform deletion.",
        )

    def handle(self, *args, **options):
        uuid = options["uuid"]
        keep_groups = options["keep_groups"]
        dry_run = options["dry_run"]
        force = options["force"]

        if not dry_run and not force:
            raise CommandError(
                "Refusing to delete without --force. Use --dry-run to preview."
            )

        self.stdout.write("Inspecting relations pointing to Lab...\n")
        found_rels = set()
        for rel in Lab._meta.related_objects:
            model_name = rel.related_model.__name__
            field_name = rel.field.name
            on_delete = rel.field.remote_field.on_delete.__name__
            nullable = rel.field.null
            found_rels.add((model_name, field_name))
            self.stdout.write(
                f"- {model_name}.{field_name} (on_delete={on_delete}, nullable={nullable})"
            )

        unexpected = found_rels - EXPECTED_RELS
        if unexpected:
            raise CommandError(
                f"Refusing to delete Lab. Unexpected relations detected: {unexpected}"
            )

        try:
            lab = Lab.objects.get(uuid=uuid)
        except (Lab.DoesNotExist, ValidationError):
            raise CommandError(f"Lab with UUID {uuid} is invalid or not found.")

        self.stdout.write(self.style.WARNING(f"\nLab: {lab.name} ({lab.uuid})"))

        study_count = lab.studies.count()
        if study_count > 0:
            raise CommandError(
                f"Refusing to delete lab: {study_count} studies are still attached."
            )

        lab_ct = ContentType.objects.get_for_model(Lab)
        user_perm_count = UserObjectPermission.objects.filter(
            content_type=lab_ct, object_pk=str(lab.pk)
        ).count()
        group_perm_count = GroupObjectPermission.objects.filter(
            content_type=lab_ct, object_pk=str(lab.pk)
        ).count()
        researcher_count = lab.researchers.count()
        requested_count = lab.requested_researchers.count()
        groups = [
            g
            for g in [
                lab.guest_group,
                lab.readonly_group,
                lab.member_group,
                lab.admin_group,
            ]
            if g is not None
        ]

        self.stdout.write(f"  User object permissions to delete: {user_perm_count}")
        self.stdout.write(f"  Group object permissions to delete: {group_perm_count}")
        self.stdout.write(f"  Researchers to remove: {researcher_count}")
        self.stdout.write(f"  Pending join requests to remove: {requested_count}")
        self.stdout.write(
            f"  Auth groups to {'preserve' if keep_groups else 'delete'}: {len(groups)}"
        )
        self.stdout.write(f"  Badge image to delete: {lab.badge.name or 'none'}")
        self.stdout.write(f"  Banner image to delete: {lab.banner.name or 'none'}")

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS("\nDry run complete. No deletion performed.")
            )
            return

        with transaction.atomic():
            lab = Lab.objects.select_for_update().get(uuid=uuid)

            UserObjectPermission.objects.filter(
                content_type=lab_ct, object_pk=str(lab.pk)
            ).delete()
            GroupObjectPermission.objects.filter(
                content_type=lab_ct, object_pk=str(lab.pk)
            ).delete()

            lab.researchers.clear()
            lab.requested_researchers.clear()

            if lab.badge:
                lab.badge.delete(save=False)
            if lab.banner:
                lab.banner.delete(save=False)

            groups = [
                g
                for g in [
                    lab.guest_group,
                    lab.readonly_group,
                    lab.member_group,
                    lab.admin_group,
                ]
                if g is not None
            ]
            lab.delete()
            self.stdout.write("Lab deleted.")

            if not keep_groups:
                for group in groups:
                    self.stdout.write(f"Deleting group: {group.name}")
                    group.delete()

        self.stdout.write(self.style.SUCCESS("Done."))
