# Generated by Django 2.2.16 on 2020-10-01 17:32

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("server", "0010_auto_20201001_1535"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="WfModule",
            new_name="Step",
        ),
        migrations.AlterModelTable(
            name="step",
            table="step",
        ),
    ]