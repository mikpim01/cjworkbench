import datetime
import json
import logging
from pathlib import Path
import threading
from typing import Any, Dict, NamedTuple
import zipfile
from django.db.models import F, OuterRef, Subquery
from cjwstate import s3
from cjwstate.models.module_version import ModuleVersion as DbModuleVersion
import cjwstate.modules
from cjwstate.modules.types import ModuleId, ModuleVersion, ModuleZipfile


_CacheEntry = NamedTuple(
    "_CacheEntry",
    [
        ("version", ModuleVersion),
        ("updated_at", datetime.datetime),
        ("module_zipfile", ModuleZipfile),
    ],
)


logger = logging.getLogger(__name__)


class ModuleRegistry:
    """Cache and find the most recent modules, by tracking versions.

    Rules:

    * `develop` modules are _not_ immutable. We consider them updated if the
      database's `last_update_time` field has a new value.
    * Otherwise, modules at a given version are immutable. We test the database
      for a newer `version`.
    """

    def __init__(self, tempdir: Path):
        self.tempdir = tempdir
        self._cache: Dict[ModuleId, _CacheEntry] = {}
        self._load_lock = threading.Lock()

    def latest(self, module_id: ModuleId) -> ModuleZipfile:
        """
        Return a ModuleZipfile for the given module ID.

        Raise `KeyError` if the module was deleted or never existed.

        Raise `RuntimeError` the module exists but cannot be loaded:

        * `RuntimeError from FileNotFoundError` if the module is not in s3.
        * `RuntimeError from KeyError` if the module zipfile is missing a .py
          file or a .yaml spec file.
        * ... and so on. `RuntimeError` is considered unrecoverable.
        """
        db_module = (
            DbModuleVersion.objects.filter(id_name=module_id)
            .order_by("-last_update_time")
            .first()
        )
        if db_module is None:
            raise KeyError("No such module '%s'" % module_id)
        else:
            return self._download_or_reuse_zipfile(db_module)

    def all_latest(self) -> Dict[str, ModuleZipfile]:
        """Return all modules, unordered, indexed by ID."""
        # https://docs.djangoproject.com/en/2.2/ref/models/expressions/#subquery-expressions
        latest = Subquery(
            (
                DbModuleVersion.objects.filter(id_name=OuterRef("id_name"))
                .order_by("-last_update_time")
                .values("id")
            )[:1]
        )
        db_modules = list(
            DbModuleVersion.objects.annotate(_latest=latest).filter(id=F("_latest"))
        )

        return {m.id_name: self._download_or_reuse_zipfile(m) for m in db_modules}

    def _download_or_reuse_zipfile(self, db_module: DbModuleVersion) -> ModuleZipfile:
        """Ensure `self._cache` contains a `ModuleZipfile` for `db_module`, and return it.

        Raise `KeyError` if the module does not exist in s3.
        """
        module_id = db_module.id_name
        version = ModuleVersion(db_module.source_version_hash)

        # 1. Get without locking.
        try:
            cache_entry = self._cache[module_id]
            if (
                cache_entry.version == version
                # check updated_at because special version "develop" changes.
                and cache_entry.updated_at == db_module.last_update_time
            ):
                return cache_entry.module_zipfile
            # fall through
        except KeyError:
            pass  # fall through

        # 2. Lock, and try again. (This prevents a race.)
        with self._load_lock:
            try:
                cache_entry = self._cache[module_id]
                if (
                    cache_entry.version == version
                    # check updated_at because special version "develop" changes.
                    and cache_entry.updated_at == db_module.last_update_time
                ):
                    return cache_entry.module_zipfile
                # else we'll download it now
            except KeyError:
                pass  # we'll download it now

            # 3. Update the cache, still holding the lock.
            module_zipfile = download_module_zipfile(
                self.tempdir,
                module_id,
                version,
                deprecated_spec=db_module.spec,
                deprecated_js_module=db_module.source_version_hash,
            )
            cache_entry = _CacheEntry(
                version, db_module.last_update_time, module_zipfile
            )
            self._cache[module_id] = cache_entry
            return module_zipfile
            # Release the lock. If another caller is waiting for us to release
            # the lock, now it should check self._cache again.

    def clear(self):
        """Empty the cache.

        This is great for unit tests. It isn't production-ready.
        """
        self._cache.clear()
        for path in self.tempdir.glob("*.zip"):
            path.unlink()


def _is_basename_python_code(key: str) -> bool:
    """True iff the given filename is a module's Python code file.

    >>> _is_basename_python_code('filter.py')
    True
    >>> _is_basename_python_code('filter.json')  # not Python
    True
    >>> _is_basename_python_code('setup.py')  # setup.py is an exception
    False
    >>> _is_basename_python_code('test_filter.py')  # tests are exceptions
    False
    """
    if key == "setup.py":
        return False
    if key.startswith("test_"):
        return False
    return key.endswith(".py")


def download_module_zipfile(
    tempdir: Path,
    module_id: ModuleId,
    version: ModuleVersion,
    *,
    deprecated_spec: Dict[str, Any],
    deprecated_js_module: str,
) -> ModuleZipfile:
    """Produce a local-path ModuleZipfile by downloading from s3.

    Raise `RuntimeError` (_from_ another kind of error -- `FileNotFoundError`,
    `KeyError`, `ValueError`, `SyntaxError`, `BadZipFile`,
    `UnicodeDecodeError` or more) if the zipfile is not a valid Workbench
    module. We spend the time testing the zipfile for validity because A) it's
    good to catch errors quickly; and B) fetcher, renderer and server all need
    to execute code on each module, so they're destined to validate the module
    anyway.

    The zipfile is always written to "{tempdir}/{module_id}.{version}.zip".
    This function is not re-entrant when called with the same parameters.
    Callers may use locks to avoid trying to download the same data multiple
    times.
    """
    logger.info("download_module_zipfile(%s.%s.zip)", module_id, version)

    tempdir.mkdir(parents=True, exist_ok=True)

    zippath = tempdir / ("%s.%s.zip" % (module_id, version))
    try:
        # raise FileNotFoundError
        s3.download(
            s3.ExternalModulesBucket,
            "%s/%s.%s.zip" % (module_id, module_id, version),
            zippath,
        )
    except FileNotFoundError as original_error:
        raise RuntimeError from original_error

    ret = ModuleZipfile(zippath)  # raise ZipfileError
    try:
        # raise KeyError or SyntaxError
        compiled_module = ret.compile_code_without_executing()
        ret.get_spec()  # raise KeyError or ValueError
        cjwstate.modules.kernel.validate(compiled_module)  # raise ModuleError
    except Exception as err:
        raise RuntimeError from err
    return ret


MODULE_TEMPDIR = Path("/var/tmp/cjwkernel-modules")
MODULE_REGISTRY = ModuleRegistry(MODULE_TEMPDIR)
