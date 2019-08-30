# Generated by Django 2.2.4 on 2019-08-30 16:23

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [("server", "0034_auto_20190730_1633")]

    operations = [
        migrations.AlterModelOptions(name="addmodulecommand", options={}),
        migrations.AlterModelOptions(name="addtabcommand", options={}),
        migrations.AlterModelOptions(name="changedataversioncommand", options={}),
        migrations.AlterModelOptions(name="changeparameterscommand", options={}),
        migrations.AlterModelOptions(name="changewfmodulenotescommand", options={}),
        migrations.AlterModelOptions(name="changeworkflowtitlecommand", options={}),
        migrations.AlterModelOptions(name="deletemodulecommand", options={}),
        migrations.AlterModelOptions(name="deletetabcommand", options={}),
        migrations.AlterModelOptions(name="delta", options={}),
        migrations.AlterModelOptions(name="duplicatetabcommand", options={}),
        migrations.AlterModelOptions(name="initworkflowcommand", options={}),
        migrations.AlterModelOptions(name="reordermodulescommand", options={}),
        migrations.AlterModelOptions(name="reordertabscommand", options={}),
        migrations.AlterModelOptions(name="settabnamecommand", options={}),
        migrations.AlterModelTable(name="aclentry", table="server_aclentry"),
        migrations.AlterModelTable(
            name="addmodulecommand", table="server_addmodulecommand"
        ),
        migrations.AlterModelTable(name="addtabcommand", table="server_addtabcommand"),
        migrations.AlterModelTable(
            name="changedataversioncommand", table="server_changedataversioncommand"
        ),
        migrations.AlterModelTable(
            name="changeparameterscommand", table="server_changeparameterscommand"
        ),
        migrations.AlterModelTable(
            name="changewfmodulenotescommand", table="server_changewfmodulenotescommand"
        ),
        migrations.AlterModelTable(
            name="changeworkflowtitlecommand", table="server_changeworkflowtitlecommand"
        ),
        migrations.AlterModelTable(
            name="deletemodulecommand", table="server_deletemodulecommand"
        ),
        migrations.AlterModelTable(
            name="deletetabcommand", table="server_deletetabcommand"
        ),
        migrations.AlterModelTable(name="delta", table="server_delta"),
        migrations.AlterModelTable(
            name="duplicatetabcommand", table="server_duplicatetabcommand"
        ),
        migrations.AlterModelTable(
            name="initworkflowcommand", table="server_initworkflowcommand"
        ),
        migrations.AlterModelTable(
            name="inprogressupload", table="server_inprogressupload"
        ),
        migrations.AlterModelTable(name="moduleversion", table="server_moduleversion"),
        migrations.AlterModelTable(
            name="reordermodulescommand", table="server_reordermodulescommand"
        ),
        migrations.AlterModelTable(
            name="reordertabscommand", table="server_reordertabscommand"
        ),
        migrations.AlterModelTable(
            name="settabnamecommand", table="server_settabnamecommand"
        ),
        migrations.AlterModelTable(name="storedobject", table="server_storedobject"),
        migrations.AlterModelTable(name="tab", table="server_tab"),
        migrations.AlterModelTable(name="uploadedfile", table="server_uploadedfile"),
        migrations.AlterModelTable(name="wfmodule", table="server_wfmodule"),
        migrations.AlterModelTable(name="workflow", table="server_workflow"),
    ]