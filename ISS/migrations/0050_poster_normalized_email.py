# -*- coding: utf-8 -*-
# Generated by Django 1.10 on 2019-02-10 09:18
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ISS', '0049_auto_20190209_2212'),
    ]

    operations = [
        migrations.AddField(
            model_name='poster',
            name='normalized_email',
            field=models.EmailField(max_length=254, null=True),
        ),
    ]