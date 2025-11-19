import os
import re

from drf_spectacular.generators import SchemaGenerator as BaseSchemaGenerator, AutoSchema
from drf_spectacular.plumbing import (
    add_trace_message,
    camelize_operation,
    error,
    get_override,
    modify_for_versioning,
    operation_matches_version,
    warn,
)
from drf_spectacular.settings import spectacular_settings


class CustomSchemaGenerator(BaseSchemaGenerator):
    """
    Wrapper around drf-spectacular's SchemaGenerator that is tolerant of
    incompatible/legacy AutoSchema configurations. Instead of raising an
    AssertionError, problematic views are skipped from the schema so that
    /api/schema/ still renders successfully.
    """

    def parse(self, input_request, public):
        result = {}
        self._initialise_endpoints()
        endpoints = self._get_paths_and_endpoints()

        if spectacular_settings.SCHEMA_PATH_PREFIX is None:
            non_trivial_prefix = len({view.__class__ for _, _, _, view in endpoints}) > 1
            if non_trivial_prefix:
                path_prefix = os.path.commonpath([path for path, _, _, _ in endpoints])
                path_prefix = re.escape(path_prefix)
            else:
                path_prefix = "/"
        else:
            path_prefix = spectacular_settings.SCHEMA_PATH_PREFIX
        if not path_prefix.startswith("^"):
            path_prefix = "^" + path_prefix

        for path, path_regex, method, view in endpoints:
            for w in get_override(view, "warnings", []):
                warn(w)
            for e in get_override(view, "errors", []):
                error(e)

            view.request = spectacular_settings.GET_MOCK_REQUEST(method, path, view, input_request)

            if not (public or self.has_view_permissions(path, method, view)):
                continue

            if view.versioning_class and not self.is_versioning_supported(view.versioning_class):
                warn(
                    f'using unsupported versioning class "{view.versioning_class}". view will be '
                    f"processed as unversioned view."
                )
            elif view.versioning_class:
                version = self.api_version or view.versioning_class.default_version
                if not version:
                    continue
                path = modify_for_versioning(self.inspector.patterns, method, path, view, version)
                if not operation_matches_version(view, version):
                    continue

            # Relaxed: instead of asserting, skip incompatible views from schema
            if not isinstance(view.schema, AutoSchema):
                warn(
                    f"Skipping view {view.__class__} from schema because it uses an "
                    f"incompatible AutoSchema ({type(view.schema)})."
                )
                continue

            with add_trace_message(getattr(view, "__class__", view)):
                operation = view.schema.get_operation(
                    path, path_regex, path_prefix, method, self.registry
                )

            if not operation:
                continue

            if spectacular_settings.SCHEMA_PATH_PREFIX_TRIM:
                path = re.sub(pattern=path_prefix, repl="", string=path, flags=re.IGNORECASE)

            if spectacular_settings.SCHEMA_PATH_PREFIX_INSERT:
                path = spectacular_settings.SCHEMA_PATH_PREFIX_INSERT + path

            if not path.startswith("/"):
                path = "/" + path

            if spectacular_settings.CAMELIZE_NAMES:
                path, operation = camelize_operation(path, operation)

            result.setdefault(path, {})
            result[path][method.lower()] = operation

        return result

