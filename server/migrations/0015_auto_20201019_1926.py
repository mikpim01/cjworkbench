# Generated by Django 2.2.16 on 2020-10-19 19:26

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("server", "0014_auto_20201001_1918"),
    ]

    operations = [
        migrations.DeleteModel(
            name="InitWorkflowCommand",
        ),
        migrations.CreateModel(
            name="InitWorkflowCommand",
            fields=[],
            options={
                "proxy": True,
                "indexes": [],
                "constraints": [],
            },
            bases=("server.delta",),
        ),
    ]