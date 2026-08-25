"""
Bulk import endpoints.

⚠️  **Two permissions, and the second one depends on the file.**

    `CanManageCatalog` opens the door. But a sheet carrying opening stock writes
    batches, costs and ledger movements — which is `inventory`'s to authorise,
    not the catalogue's. A merchandiser who may add products must not receive a
    million pounds of stock because it rode along in the same upload.

⚠️  And a job is advanced by **its own owner alone**.

    Progress is a shared row, and two browsers driving the same job step on each
    other's cursor: both read 4,000, both process the same five hundred rows,
    and one chunk is imported twice. Ownership is not about secrecy here — it is
    the cheapest possible lock.
"""

from __future__ import annotations

from django.http import HttpResponse
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api.pagination import AdminPageNumberPagination
from core.errors import BusinessError, ErrorCode
from core.permissions import CanManageCatalog, CanManageInventory
from imports import references, report, services, spec, template
from imports import serializers as s
from imports.models import ImportJob

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx_response(payload: bytes, filename: str) -> HttpResponse:
    """
    ⚠️  The filename is ASCII **and** UTF-8, both spellings in one header.

        `filename=` alone mangles an Arabic name in older clients, and
        `filename*=` alone is ignored by some download managers, which then save
        the file with no extension at all — and a `.xlsx` without its extension
        does not open by double-click on Windows.
    """
    response = HttpResponse(payload, content_type=XLSX_CONTENT_TYPE)
    response["Content-Disposition"] = (
        f"attachment; filename=\"{filename}\"; filename*=UTF-8''{filename}"
    )
    response["Content-Length"] = str(len(payload))
    # ⚠️  A template generated from the live catalogue must never be cached by a
    #     proxy: the next admin would download this one's category list.
    response["Cache-Control"] = "no-store"
    return response


class ImportTemplateAPI(APIView):
    """
    `GET` — the template, built from the catalogue as it stands right now.

    ⚠️  Generated per request rather than cached. It is a couple of hundred
        milliseconds of openpyxl against a download that happens a handful of
        times a week, and caching it is how a template goes stale against a
        category added an hour ago — which is the one failure the whole
        single-source rule exists to prevent.
    """

    permission_classes = [CanManageCatalog]

    def get(self, request):
        return _xlsx_response(template.build(), "product-import-template.xlsx")


class ImportSpecAPI(APIView):
    """
    `GET` — the column guide, so the frontend renders it instead of restating it.

    ⚠️  The screen that explains the file and the file itself have exactly one
        source. A column added to `spec.py` appears in the template, in the
        validator and on this screen without anyone remembering the third place.
    """

    permission_classes = [CanManageCatalog]

    def get(self, request):
        data = references.load()
        return Response(
            {
                "max_rows": spec.MAX_ROWS_PER_FILE,
                "max_bytes": spec.MAX_FILE_BYTES,
                "modes": [
                    {"value": value, "label": label}
                    for value, label in spec.IMPORT_MODE_LABELS.items()
                ],
                "sheets": [
                    {
                        "name": name,
                        "title": spec.SHEET_TITLES[name],
                        "required": name in spec.REQUIRED_SHEETS,
                        "columns": [
                            {
                                "key": column.key,
                                "header": column.header,
                                "kind": column.kind,
                                "required": column.required,
                                "conditional": column.required_when is not None,
                                "note": column.note,
                                "example": column.example,
                            }
                            for column in columns
                        ],
                    }
                    for name, columns in spec.SHEETS.items()
                ],
                "reference_counts": {
                    "categories": len(data.categories),
                    "brands": len(data.brands),
                    "manufacturers": len(data.manufacturers),
                    "locations": len(data.locations),
                },
                # ⚠️  Surfaced because an import is impossible without them, and
                #     "why did every row fail?" has exactly this answer more often
                #     than any other.
                "blocking": {
                    "no_categories": not data.categories,
                    "no_default_location": not data.default_location_code,
                },
            }
        )


class ImportJobListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [CanManageCatalog]
    serializer_class = s.ImportJobSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        from django.db.models import Count

        return (
            ImportJob.objects.select_related("started_by")
            .annotate(error_total=Count("errors"))
            .order_by("-created_at")
        )

    def create(self, request, *args, **kwargs):
        form = s.CreateImportJobSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data

        job = services.create_job(
            data["file"],
            mode=data["mode"],
            actor=request.user,
            create_missing_brands=data["create_missing_brands"],
        )

        payload = s.ImportJobSerializer(job).data

        # ⚠️  A previous run of the identical file is **reported, not blocked**.
        #
        #     Re-running is legitimate; doing it unknowingly on `UPSERT` rewrites
        #     rows the admin believed they had already superseded.
        earlier = services.earlier_import_of(job)
        payload["duplicate_of"] = (
            {
                "id": str(earlier.id),
                "created_at": earlier.created_at,
                "created_count": earlier.created_count,
            }
            if earlier
            else None
        )

        # ⚠️  The stock permission is checked **after** the file is read, because
        #     that is when we learn whether it carries stock at all. Demanding it
        #     up front would lock a plain product import behind an inventory
        #     permission it never uses.
        if job.row_counts.get(spec.Sheet.STOCK) and not CanManageInventory().has_permission(
            request, self
        ):
            job.delete()
            raise BusinessError(
                ErrorCode.PERMISSION_DENIED,
                detail="الملف يحوي ورقة رصيد افتتاحي — وهي تحتاج صلاحية إدارة المخزون",
                status_code=403,
            )

        return Response(payload, status=201)


class ImportJobDetailAPI(generics.RetrieveAPIView):
    permission_classes = [CanManageCatalog]
    serializer_class = s.ImportJobSerializer
    queryset = ImportJob.objects.select_related("started_by")


class _JobActionAPI(APIView):
    """Shared lookup and ownership check for every action on one job."""

    permission_classes = [CanManageCatalog]

    def get_job(self, request, pk) -> ImportJob:
        job = ImportJob.objects.filter(pk=pk).first()
        if job is None:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)
        return job

    def owned_job(self, request, pk) -> ImportJob:
        job = self.get_job(request, pk)
        if job.started_by_id and job.started_by_id != request.user.id:
            raise BusinessError(
                ErrorCode.PERMISSION_DENIED,
                detail="هذه الوظيفة يقودها مستخدم آخر",
                status_code=403,
            )
        return job


class ValidateImportAPI(_JobActionAPI):
    """`POST` — start the dry run. Advancing it is the same `advance` loop."""

    def post(self, request, pk):
        job = services.start_validation(self.owned_job(request, pk))
        return Response(s.ImportJobSerializer(job).data)


class ExecuteImportAPI(_JobActionAPI):
    """`POST` — begin writing. Only from `VALIDATED`."""

    def post(self, request, pk):
        job = self.owned_job(request, pk)

        if job.row_counts.get(spec.Sheet.STOCK) and not CanManageInventory().has_permission(
            request, self
        ):
            raise BusinessError(
                ErrorCode.PERMISSION_DENIED,
                detail="تنفيذ ورقة الرصيد الافتتاحي يحتاج صلاحية إدارة المخزون",
                status_code=403,
            )

        job = services.start_execution(job)
        return Response(s.ImportJobSerializer(job).data)


class AdvanceImportAPI(_JobActionAPI):
    """
    `POST` — do one chunk and return the progress.

    ⚠️  The **browser** is the primary driver of this loop, and that is a
        deliberate choice over a server-side background thread.

        A thread on Passenger dies with its worker and takes the job's progress
        with it, silently. A browser loop shows the admin exactly where the
        import is, lets them stop it, and — because every chunk is written down
        — survives being closed: `run_periodic` finishes what the tab started.
    """

    throttle_scope = "import_chunk"

    def post(self, request, pk):
        job = services.advance(self.owned_job(request, pk))
        return Response(s.ImportJobSerializer(job).data)


class CancelImportAPI(_JobActionAPI):
    def post(self, request, pk):
        job = services.cancel(
            self.owned_job(request, pk), reason=str(request.data.get("reason", ""))[:500]
        )
        return Response(s.ImportJobSerializer(job).data)


class PublishImportAPI(_JobActionAPI):
    """
    `POST` — activate what this job created.

    ⚠️  A separate call, and a separate decision. Import writes drafts; this is
        the moment a catalogue becomes a storefront.
    """

    def post(self, request, pk):
        published = services.publish(self.get_job(request, pk), actor=request.user)
        return Response({"published": published})


class ImportErrorListAPI(generics.ListAPIView):
    """
    `GET` — the errors, paginated.

    ⚠️  Paginated even though the frontend shows the first fifty. A job with
        thirty thousand errors would otherwise serialise thirty thousand rows
        into a response nobody reads past the first screen of.
    """

    permission_classes = [CanManageCatalog]
    serializer_class = s.ImportRowErrorSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = ImportJob.objects.filter(pk=self.kwargs["pk"]).first()
        if queryset is None:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        errors = queryset.errors.all()
        if sheet := self.request.query_params.get("sheet"):
            errors = errors.filter(sheet=sheet)
        if search := self.request.query_params.get("search"):
            errors = errors.filter(identifier__icontains=search)
        return errors


class ImportErrorFileAPI(_JobActionAPI):
    """`GET` — the failing rows as a file to correct and upload again."""

    def get(self, request, pk):
        job = self.get_job(request, pk)
        if not job.errors.exists():
            raise BusinessError(
                ErrorCode.NOT_FOUND, detail="لا توجد أخطاء في هذه الوظيفة", status_code=404
            )

        name = (job.original_filename or "import").rsplit(".", 1)[0]
        return _xlsx_response(report.build(job), f"{name}-errors.xlsx")
