from django.db import models


class InstitutionSection(models.Model):
    name = models.TextField(unique=True)
    order = models.IntegerField()


class Institution(models.Model):
    name = models.TextField()
    section = models.ForeignKey(InstitutionSection, on_delete=models.CASCADE)
