# Generated by Django 3.1.5 on 2021-01-14 14:42

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("server", "0027_auto_20210113_1624"),
    ]

    operations = [
        migrations.DeleteModel(
            name="InProgressUpload",
        ),
    ]
