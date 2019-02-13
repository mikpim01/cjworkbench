# -*- coding: utf-8 -*-
# Generated by Django 1.11.17 on 2019-02-09 18:49
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):
    """
    Nix ModuleVersions from the database that refer to internal modules.

    We've recently changed internal modules to be loaded only from disk. There
    were also a few module renames. Old-named modules (like "duplicate-column")
    were left in the database without any associated code.
    """

    dependencies = [
        ('server', '0044_rename_module_id_names'),
    ]

    operations = [
        migrations.RunSQL([
            """
            DELETE FROM server_moduleversion
            WHERE source_version_hash = '1.0';
            """
        ], elidable=True),
    ]