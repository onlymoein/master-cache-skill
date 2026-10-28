from django.db import models


class Organization(models.Model):
    name = models.CharField(max_length=200)


class Invoice(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
