import datetime
import uuid as uuidgen

from cjwkernel.util import tempfile_context
from cjwstate import s3
from cjwstate.storedobjects import create_stored_object
from cjwstate.models import Workflow
from cjwstate.tests.utils import DbTestCase, get_s3_object_with_data


# Set up a simple pipeline on test data
class StepTests(DbTestCase):
    def test_list_data_versions(self):
        workflow = Workflow.create_and_init()
        step = workflow.tabs.first().steps.create(order=0, slug="step-1")
        so1 = step.stored_objects.create(read=False)
        so2 = step.stored_objects.create(read=True)

        result = step.list_fetched_data_versions()
        self.assertEqual(result, [(so2.stored_at, True), (so1.stored_at, False)])

    def test_step_duplicate(self):
        workflow = Workflow.create_and_init()
        step1 = workflow.tabs.first().steps.create(order=0, slug="step-1")

        # store data to test that it is duplicated
        with tempfile_context() as path1:
            path1.write_bytes(b"12345")
            create_stored_object(workflow.id, step1.id, path1)
        with tempfile_context() as path2:
            path1.write_bytes(b"23456")
            so2 = create_stored_object(workflow.id, step1.id, path2)
        step1.secrets = {"do not copy": {"name": "evil", "secret": "evil"}}
        step1.stored_data_version = so2.stored_at
        step1.save(update_fields=["stored_data_version"])

        # duplicate into another workflow, as we would do when duplicating a workflow
        workflow2 = Workflow.create_and_init()
        tab2 = workflow2.tabs.first()
        step1d = step1.duplicate_into_new_workflow(tab2)
        step1d.refresh_from_db()  # test what we actually have in the db

        self.assertEqual(step1d.slug, "step-1")
        self.assertEqual(step1d.workflow, workflow2)
        self.assertEqual(step1d.module_id_name, step1.module_id_name)
        self.assertEqual(step1d.order, step1.order)
        self.assertEqual(step1d.notes, step1.notes)
        self.assertEqual(step1d.last_update_check, step1.last_update_check)
        self.assertEqual(step1d.is_collapsed, step1.is_collapsed)
        self.assertEqual(step1d.params, step1.params)
        self.assertEqual(step1d.secrets, {})

        # Stored data should contain a clone of content only, not complete version history
        self.assertEqual(step1d.stored_objects.count(), 1)
        self.assertEqual(step1d.stored_data_version, step1.stored_data_version)
        so2d = step1d.stored_objects.first()
        # The StoredObject was copied byte for byte into a different file
        self.assertNotEqual(so2d.key, so2.key)
        self.assertEqual(
            get_s3_object_with_data(s3.StoredObjectsBucket, so2d.key)["Body"],
            get_s3_object_with_data(s3.StoredObjectsBucket, so2.key)["Body"],
        )

    def test_step_duplicate_disable_auto_update(self):
        # Duplicates should be lightweight by default: no auto-updating.
        workflow = Workflow.create_and_init()
        tab = workflow.tabs.first()
        step = tab.steps.create(
            order=0,
            slug="step-1",
            auto_update_data=True,
            next_update=datetime.datetime.now(),
            update_interval=600,
        )

        workflow2 = Workflow.create_and_init()
        tab2 = workflow2.tabs.create(position=0)
        step2 = step.duplicate_into_new_workflow(tab2)

        self.assertEqual(step2.auto_update_data, False)
        self.assertIsNone(step2.next_update)
        self.assertEqual(step2.update_interval, 600)

    def test_step_duplicate_clear_secrets(self):
        # Duplicates get new owners, so they should not copy secrets.
        workflow = Workflow.create_and_init()
        tab = workflow.tabs.first()
        step = tab.steps.create(
            order=0, slug="step-1", secrets={"auth": {"name": "x", "secret": "y"}}
        )

        workflow2 = Workflow.create_and_init()
        tab2 = workflow2.tabs.first()
        step2 = step.duplicate_into_new_workflow(tab2)

        self.assertEqual(step2.secrets, {})

    def test_step_duplicate_copy_uploaded_file(self):
        workflow = Workflow.create_and_init()
        tab = workflow.tabs.first()
        step = tab.steps.create(order=0, slug="step-1", module_id_name="upload")
        uuid = str(uuidgen.uuid4())
        key = f"{step.uploaded_file_prefix}{uuid}.csv"
        s3.put_bytes(s3.UserFilesBucket, key, b"1234567")
        # Write the uuid to the old module -- we'll check the new module points
        # to a valid file
        step.params = {"file": uuid, "has_header": True}
        step.save(update_fields=["params"])
        uploaded_file = step.uploaded_files.create(
            name="t.csv", uuid=uuid, key=key, size=7
        )

        workflow2 = Workflow.create_and_init()
        tab2 = workflow2.tabs.first()
        step2 = step.duplicate_into_new_workflow(tab2)

        uploaded_file2 = step2.uploaded_files.first()
        self.assertIsNotNone(uploaded_file2)
        # New file gets same uuid -- because it's the same file and we don't
        # want to edit params during copy
        self.assertEqual(uploaded_file2.uuid, uuid)
        self.assertEqual(step2.params["file"], uuid)
        self.assertTrue(
            # The new file should be in a different path
            uploaded_file2.key.startswith(step2.uploaded_file_prefix)
        )
        self.assertEqual(uploaded_file2.name, "t.csv")
        self.assertEqual(uploaded_file2.size, 7)
        self.assertEqual(uploaded_file2.created_at, uploaded_file.created_at)
        self.assertEqual(
            get_s3_object_with_data(s3.UserFilesBucket, uploaded_file2.key)["Body"],
            b"1234567",
        )

    def test_step_duplicate_copy_only_selected_uploaded_file(self):
        workflow = Workflow.create_and_init()
        tab = workflow.tabs.first()
        step = tab.steps.create(order=0, slug="step-1", module_id_name="upload")
        uuid1 = str(uuidgen.uuid4())
        key1 = f"{step.uploaded_file_prefix}{uuid1}.csv"
        s3.put_bytes(s3.UserFilesBucket, key1, b"1234567")
        uuid2 = str(uuidgen.uuid4())
        key2 = f"{step.uploaded_file_prefix}{uuid2}.csv"
        s3.put_bytes(s3.UserFilesBucket, key2, b"7654321")
        uuid3 = str(uuidgen.uuid4())
        key3 = f"{step.uploaded_file_prefix}{uuid3}.csv"
        s3.put_bytes(s3.UserFilesBucket, key3, b"9999999")
        step.uploaded_files.create(name="t1.csv", uuid=uuid1, key=key1, size=7)
        step.uploaded_files.create(name="t2.csv", uuid=uuid2, key=key2, size=7)
        step.uploaded_files.create(name="t3.csv", uuid=uuid3, key=key3, size=7)
        # Write the _middle_ uuid to the old module -- proving that we aren't
        # selecting by ordering
        step.params = {"file": uuid2, "has_header": True}
        step.save(update_fields=["params"])

        workflow2 = Workflow.create_and_init()
        tab2 = workflow2.tabs.first()
        step2 = step.duplicate_into_new_workflow(tab2)

        self.assertEqual(step2.uploaded_files.count(), 1)
        new_uf = step2.uploaded_files.first()
        self.assertEqual(new_uf.uuid, uuid2)

    def test_delete_remove_uploaded_data_by_prefix_in_case_model_missing(self):
        workflow = Workflow.create_and_init()
        step = workflow.tabs.first().steps.create(order=0, slug="step-1")
        uuid = str(uuidgen.uuid4())
        key = step.uploaded_file_prefix + uuid
        s3.put_bytes(s3.UserFilesBucket, key, b"A\n1")
        # Don't create the UploadedFile. Simulates races during upload/delete
        # that could write a file on S3 but not in our database.
        # step.uploaded_files.create(name='t.csv', size=3, uuid=uuid, key=key)
        step.delete()  # do not crash
        self.assertFalse(s3.exists(s3.UserFilesBucket, key))
