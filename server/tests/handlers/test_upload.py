from base64 import b64encode
import hashlib
from unittest.mock import patch
from django.contrib.auth.models import User
from django.utils import timezone
from server.handlers.upload import create_upload, finish_upload, abort_upload
from server.models import Workflow
from server import minio
from .util import HandlerTestCase


def _base64_md5sum(b: bytes) -> str:
    h = hashlib.md5()
    h.update(b)
    md5sum = h.digest()
    return b64encode(md5sum).decode("ascii")


async def async_noop(*args, **kwargs):
    pass


class UploadTest(HandlerTestCase):
    def test_create_upload(self):
        user = User.objects.create(username="a", email="a@example.org")
        workflow = Workflow.create_and_init(owner=user)
        wf_module = workflow.tabs.first().wf_modules.create(order=0, module_id_name="x")
        response = self.run_handler(
            create_upload, user=user, workflow=workflow, wfModuleId=wf_module.id
        )
        self.assertEqual(response.error, "")
        # Test that wf_module is aware of the upload
        wf_module.refresh_from_db()
        self.assertIsNotNone(wf_module.inprogress_file_upload_key)
        self.assertRegex(
            wf_module.inprogress_file_upload_key,
            "wf-%d/wfm-%d/upload_[-0-9a-f]{36}" % (workflow.id, wf_module.id),
        )
        self.assertLessEqual(
            wf_module.inprogress_file_upload_last_accessed_at, timezone.now()
        )
        # Test that response has bucket+key+credentials
        self.assertEqual(response.data["bucket"], minio.UserFilesBucket)
        self.assertEqual(response.data["key"], wf_module.inprogress_file_upload_key)
        self.assertIn("credentials", response.data)

    @patch("server.websockets.ws_client_send_delta_async")
    def test_finish_upload_happy_path(self, send_delta):
        user = User.objects.create(username="a", email="a@example.org")
        workflow = Workflow.create_and_init(owner=user)
        wf_module = workflow.tabs.first().wf_modules.create(order=0, module_id_name="x")
        key = f"wf-{workflow.id}/wfm-{wf_module.id}/upload_147a9f5d-5b3e-41c3-a968-a84a5a9d587f"
        wf_module.inprogress_file_upload_key = key
        wf_module.inprogress_file_upload_last_accessed_at = timezone.now()
        wf_module.save()
        minio.put_bytes(minio.UserFilesBucket, key, b"1234567")
        send_delta.side_effect = async_noop
        response = self.run_handler(
            finish_upload,
            user=user,
            workflow=workflow,
            wfModuleId=wf_module.id,
            key=key,
            filename="test sheet.csv",
        )
        self.assertResponse(
            response, data={"uuid": "147a9f5d-5b3e-41c3-a968-a84a5a9d587f"}
        )
        # The uploaded file is deleted
        self.assertFalse(minio.exists(minio.UserFilesBucket, key))
        # A new upload is created
        uploaded_file = wf_module.uploaded_files.first()
        self.assertEqual(uploaded_file.name, "test sheet.csv")
        self.assertEqual(uploaded_file.size, 7)
        self.assertEqual(uploaded_file.uuid, "147a9f5d-5b3e-41c3-a968-a84a5a9d587f")
        self.assertEqual(uploaded_file.bucket, minio.UserFilesBucket)
        final_key = f"wf-{workflow.id}/wfm-{wf_module.id}/147a9f5d-5b3e-41c3-a968-a84a5a9d587f.csv"
        self.assertEqual(uploaded_file.key, final_key)
        # The file has the right bytes and metadata
        self.assertEqual(
            minio.get_object_with_data(minio.UserFilesBucket, final_key)["Body"],
            b"1234567",
        )
        self.assertEqual(
            minio.client.head_object(Bucket=minio.UserFilesBucket, Key=final_key)[
                "ContentDisposition"
            ],
            "attachment; filename*=UTF-8''test%20sheet.csv",
        )
        # wf_module is updated
        wf_module.refresh_from_db()
        self.assertIsNone(wf_module.inprogress_file_upload_key)
        self.assertIsNone(wf_module.inprogress_file_upload_last_accessed_at)

        send_delta.assert_called()

    def test_finish_upload_error_not_started(self):
        user = User.objects.create(username="a", email="a@example.org")
        workflow = Workflow.create_and_init(owner=user)
        wf_module = workflow.tabs.first().wf_modules.create(order=0, module_id_name="x")
        key = f"wf-{workflow.id}/wfm-{wf_module.id}/upload_147a9f5d-5b3e-41c3-a968-a84a5a9d587f"
        response = self.run_handler(
            finish_upload,
            user=user,
            workflow=workflow,
            wfModuleId=wf_module.id,
            key=key,
            filename="test.csv",
        )
        self.assertResponse(
            response,
            error=(
                "BadRequest: key is not being uploaded for this WfModule right now. "
                "(Even a valid key becomes invalid after you create, finish or abort "
                "an upload on its WfModule.)"
            ),
        )

    def test_finish_upload_error_file_missing(self):
        user = User.objects.create(username="a", email="a@example.org")
        workflow = Workflow.create_and_init(owner=user)
        wf_module = workflow.tabs.first().wf_modules.create(order=0, module_id_name="x")
        key = f"wf-{workflow.id}/wfm-{wf_module.id}/upload_147a9f5d-5b3e-41c3-a968-a84a5a9d587f"
        wf_module.inprogress_file_upload_key = key
        wf_module.inprogress_file_upload_last_accessed_at = timezone.now()
        wf_module.save()
        response = self.run_handler(
            finish_upload,
            user=user,
            workflow=workflow,
            wfModuleId=wf_module.id,
            key=key,
            filename="test.csv",
        )
        self.assertResponse(
            response,
            error=(
                "BadRequest: file not found. "
                "You must upload the file before calling finish_upload."
            ),
        )
        wf_module.refresh_from_db()
        self.assertEqual(wf_module.inprogress_file_upload_key, key)

    def test_abort_upload_happy_path_before_complete(self):
        user = User.objects.create(username="a", email="a@example.org")
        workflow = Workflow.create_and_init(owner=user)
        wf_module = workflow.tabs.first().wf_modules.create(order=0, module_id_name="x")
        key = f"wf-{workflow.id}/wfm-{wf_module.id}/upload_147a9f5d-5b3e-41c3-a968-a84a5a9d587f"

        # precondition: there's an incomplete multipart upload. minio is a bit
        # different from S3 here, so we add a .assertIn to verify that the data
        # is there _before_ we abort.
        minio.client.create_multipart_upload(Bucket=minio.UserFilesBucket, Key=key)
        response = minio.client.list_multipart_uploads(
            Bucket=minio.UserFilesBucket, Prefix=key
        )
        self.assertIn("Uploads", response)

        wf_module.inprogress_file_upload_key = key
        wf_module.inprogress_file_upload_last_accessed_at = timezone.now()
        wf_module.save()
        response = self.run_handler(
            abort_upload, user=user, workflow=workflow, wfModuleId=wf_module.id, key=key
        )
        self.assertResponse(response, data=None)
        response = minio.client.list_multipart_uploads(
            Bucket=minio.UserFilesBucket, Prefix=key
        )
        self.assertNotIn("Uploads", response)

    def test_abort_upload_happy_path_after_complete(self):
        user = User.objects.create(username="a", email="a@example.org")
        workflow = Workflow.create_and_init(owner=user)
        wf_module = workflow.tabs.first().wf_modules.create(order=0, module_id_name="x")
        key = f"wf-{workflow.id}/wfm-{wf_module.id}/upload_147a9f5d-5b3e-41c3-a968-a84a5a9d587f"
        minio.put_bytes(minio.UserFilesBucket, key, b"1234567")
        wf_module.inprogress_file_upload_key = key
        wf_module.inprogress_file_upload_last_accessed_at = timezone.now()
        wf_module.save()
        response = self.run_handler(
            abort_upload, user=user, workflow=workflow, wfModuleId=wf_module.id, key=key
        )
        self.assertResponse(response, data=None)
        wf_module.refresh_from_db()
        self.assertIsNone(wf_module.inprogress_file_upload_key)
        self.assertIsNone(wf_module.inprogress_file_upload_last_accessed_at)
        self.assertFalse(minio.exists(minio.UserFilesBucket, key))
