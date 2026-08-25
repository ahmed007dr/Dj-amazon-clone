"""
Import contracts.

⚠️  The job serializer sends **counters and percentages, never rows.**

    A progress response is polled every second or two while the browser drives
    the chunks. Attaching even the first hundred error rows to it means the same
    hundred rows crossing the wire fifty times during one import. The errors
    have their own endpoint, and their own file.
"""

from rest_framework import serializers

from imports import spec
from imports.models import ImportJob, ImportRowError


class ImportRowErrorSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportRowError
        fields = ["id", "sheet", "row_number", "column", "value", "message", "identifier"]


class ImportJobSerializer(serializers.ModelSerializer):
    total_rows = serializers.IntegerField(read_only=True)
    processed_rows = serializers.IntegerField(read_only=True)
    progress_percent = serializers.IntegerField(read_only=True)
    is_terminal = serializers.BooleanField(read_only=True)
    #: ⚠️  The loop condition. See `ImportJob.is_running` for why it is not
    #:     simply `not is_terminal`.
    is_running = serializers.BooleanField(read_only=True)
    error_count = serializers.SerializerMethodField()

    class Meta:
        model = ImportJob
        fields = [
            "id",
            "original_filename",
            "mode",
            "status",
            "phase",
            "row_counts",
            "cursor",
            "created_count",
            "updated_count",
            "skipped_count",
            "failed_count",
            "total_rows",
            "processed_rows",
            "progress_percent",
            "is_terminal",
            "is_running",
            "error_count",
            "preview",
            "error_message",
            "created_at",
            "started_at",
            "finished_at",
        ]
        read_only_fields = fields

    def get_error_count(self, obj) -> int:
        # ⚠️  Annotated by the view where the list is paginated; counted here only
        #     for the single-object responses, where one extra query is fine and
        #     an N+1 is impossible by construction.
        cached = getattr(obj, "error_total", None)
        return cached if cached is not None else obj.errors.count()


class CreateImportJobSerializer(serializers.Serializer):
    """
    ⚠️  The upload is `multipart`, and `mode` arrives beside the file rather than
        being chosen later — the dry-run report cannot be written without it.
        "This row already exists" is an error under one mode and the entire
        purpose under another.
    """

    file = serializers.FileField()
    mode = serializers.ChoiceField(
        choices=[
            (spec.ImportMode.CREATE_ONLY, spec.IMPORT_MODE_LABELS[spec.ImportMode.CREATE_ONLY]),
            (spec.ImportMode.UPDATE_ONLY, spec.IMPORT_MODE_LABELS[spec.ImportMode.UPDATE_ONLY]),
            (spec.ImportMode.UPSERT, spec.IMPORT_MODE_LABELS[spec.ImportMode.UPSERT]),
        ],
        default=spec.ImportMode.CREATE_ONLY,
    )
    #: ⚠️  Off by default. A typo under "on" creates «Pfzier» beside «Pfizer»
    #:     rather than failing one row, and nobody notices until a customer
    #:     filters by brand and sees two.
    create_missing_brands = serializers.BooleanField(default=False)

    def validate_file(self, value):
        """
        ⚠️  The extension is checked here and the **content** is checked by
            openpyxl a moment later, in `services.create_job`.

            Neither is sufficient alone: an extension is a claim the client
            makes, and letting a renamed `.exe` reach a zip parser is how a
            parser gets fuzzed for free. Rejecting on the name first costs one
            comparison.
        """
        name = (value.name or "").lower()
        if not name.endswith(".xlsx"):
            raise serializers.ValidationError(
                "الصيغة المدعومة هي xlsx وحدها — احفظ الملف بها من إكسل"
            )
        if value.size > spec.MAX_FILE_BYTES:
            raise serializers.ValidationError(
                f"حجم الملف يتجاوز {spec.MAX_FILE_BYTES // (1024 * 1024)} ميجابايت"
            )
        return value
