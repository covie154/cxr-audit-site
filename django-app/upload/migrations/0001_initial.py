# Generated migration for upload app models

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="CXRStudy",
            fields=[
                (
                    "accession_no",
                    models.BigIntegerField(
                        primary_key=True, serialize=False, verbose_name="Accession Number"
                    ),
                ),
                (
                    "study_id_anonymized",
                    models.CharField(
                        blank=True, max_length=255, null=True, verbose_name="Anonymized Study ID"
                    ),
                ),
                (
                    "study_id",
                    models.CharField(
                        blank=True, max_length=255, null=True, verbose_name="Study ID"
                    ),
                ),
                (
                    "patient_name",
                    models.CharField(
                        blank=True, max_length=255, null=True, verbose_name="Patient Name"
                    ),
                ),
                (
                    "patient_id",
                    models.CharField(
                        blank=True, max_length=255, null=True, verbose_name="Patient ID"
                    ),
                ),
                (
                    "patient_age",
                    models.IntegerField(blank=True, null=True, verbose_name="Patient Age"),
                ),
                (
                    "patient_gender",
                    models.CharField(
                        blank=True, max_length=10, null=True, verbose_name="Patient Gender"
                    ),
                ),
                (
                    "instances",
                    models.IntegerField(
                        blank=True, null=True, verbose_name="Number of Instances"
                    ),
                ),
                (
                    "study_description",
                    models.CharField(
                        blank=True, max_length=500, null=True, verbose_name="Study Description"
                    ),
                ),
                (
                    "upload_date",
                    models.DateTimeField(blank=True, null=True, verbose_name="Upload Date"),
                ),
                (
                    "inference_date",
                    models.DateTimeField(blank=True, null=True, verbose_name="Inference Date"),
                ),
                (
                    "workplace",
                    models.CharField(
                        blank=True, max_length=50, null=True, verbose_name="Workplace Code"
                    ),
                ),
                (
                    "medical_location_name",
                    models.CharField(
                        blank=True, max_length=255, null=True, verbose_name="Medical Location"
                    ),
                ),
                (
                    "abnormal",
                    models.FloatField(blank=True, null=True, verbose_name="Abnormal Score"),
                ),
                (
                    "atelectasis",
                    models.FloatField(blank=True, null=True, verbose_name="Atelectasis Score"),
                ),
                (
                    "calcification",
                    models.FloatField(blank=True, null=True, verbose_name="Calcification Score"),
                ),
                (
                    "cardiomegaly",
                    models.FloatField(blank=True, null=True, verbose_name="Cardiomegaly Score"),
                ),
                (
                    "consolidation",
                    models.FloatField(blank=True, null=True, verbose_name="Consolidation Score"),
                ),
                (
                    "fibrosis",
                    models.FloatField(blank=True, null=True, verbose_name="Fibrosis Score"),
                ),
                (
                    "mediastinal_widening",
                    models.FloatField(
                        blank=True, null=True, verbose_name="Mediastinal Widening Score"
                    ),
                ),
                (
                    "nodule",
                    models.FloatField(blank=True, null=True, verbose_name="Nodule Score"),
                ),
                (
                    "pleural_effusion",
                    models.FloatField(
                        blank=True, null=True, verbose_name="Pleural Effusion Score"
                    ),
                ),
                (
                    "pneumoperitoneum",
                    models.FloatField(
                        blank=True, null=True, verbose_name="Pneumoperitoneum Score"
                    ),
                ),
                (
                    "pneumothorax",
                    models.FloatField(blank=True, null=True, verbose_name="Pneumothorax Score"),
                ),
                (
                    "tuberculosis",
                    models.FloatField(blank=True, null=True, verbose_name="Tuberculosis Score"),
                ),
                (
                    "ai_report",
                    models.TextField(blank=True, null=True, verbose_name="AI Report"),
                ),
                (
                    "ai_priority",
                    models.CharField(
                        blank=True, max_length=50, null=True, verbose_name="AI Priority"
                    ),
                ),
                (
                    "ai_flag_received_date",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="AI Flag Received Date"
                    ),
                ),
                ("feedback", models.TextField(blank=True, null=True, verbose_name="Feedback")),
                ("comments", models.TextField(blank=True, null=True, verbose_name="Comments")),
                (
                    "status",
                    models.CharField(blank=True, max_length=50, null=True, verbose_name="Status"),
                ),
                (
                    "procedure_start_date",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Procedure Start Date"
                    ),
                ),
                (
                    "procedure_end_date",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Procedure End Date"
                    ),
                ),
                (
                    "time_end_to_end_seconds",
                    models.FloatField(
                        blank=True, null=True, verbose_name="End-to-End Time (seconds)"
                    ),
                ),
                (
                    "time_to_clinical_decision_seconds",
                    models.FloatField(
                        blank=True, null=True, verbose_name="Time to Clinical Decision (seconds)"
                    ),
                ),
                (
                    "text_report",
                    models.TextField(
                        blank=True, null=True, verbose_name="Radiologist Text Report (RIS)"
                    ),
                ),
                (
                    "gt_manual",
                    models.SmallIntegerField(
                        blank=True, null=True, verbose_name="Manual Ground Truth (0/1)"
                    ),
                ),
                (
                    "gt_llm",
                    models.SmallIntegerField(
                        blank=True, null=True, verbose_name="LLM Ground Truth (0/1)"
                    ),
                ),
                (
                    "lunit_binarised",
                    models.SmallIntegerField(
                        blank=True, null=True, verbose_name="Lunit Binarised (0/1)"
                    ),
                ),
                (
                    "llm_grade",
                    models.SmallIntegerField(
                        blank=True, null=True, verbose_name="LLM Grade (1-5)"
                    ),
                ),
                (
                    "atelectasis_llm",
                    models.SmallIntegerField(
                        blank=True, null=True, verbose_name="Atelectasis LLM"
                    ),
                ),
                (
                    "calcification_llm",
                    models.SmallIntegerField(
                        blank=True, null=True, verbose_name="Calcification LLM"
                    ),
                ),
                (
                    "cardiomegaly_llm",
                    models.SmallIntegerField(
                        blank=True, null=True, verbose_name="Cardiomegaly LLM"
                    ),
                ),
                (
                    "consolidation_llm",
                    models.SmallIntegerField(
                        blank=True, null=True, verbose_name="Consolidation LLM"
                    ),
                ),
                (
                    "fibrosis_llm",
                    models.SmallIntegerField(blank=True, null=True, verbose_name="Fibrosis LLM"),
                ),
                (
                    "mediastinal_widening_llm",
                    models.SmallIntegerField(
                        blank=True, null=True, verbose_name="Mediastinal Widening LLM"
                    ),
                ),
                (
                    "nodule_llm",
                    models.SmallIntegerField(blank=True, null=True, verbose_name="Nodule LLM"),
                ),
                (
                    "pleural_effusion_llm",
                    models.SmallIntegerField(
                        blank=True, null=True, verbose_name="Pleural Effusion LLM"
                    ),
                ),
                (
                    "pneumoperitoneum_llm",
                    models.SmallIntegerField(
                        blank=True, null=True, verbose_name="Pneumoperitoneum LLM"
                    ),
                ),
                (
                    "pneumothorax_llm",
                    models.SmallIntegerField(
                        blank=True, null=True, verbose_name="Pneumothorax LLM"
                    ),
                ),
                (
                    "tb_llm",
                    models.SmallIntegerField(blank=True, null=True, verbose_name="TB LLM"),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Record Created At"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="Record Updated At"),
                ),
                (
                    "processing_batch_id",
                    models.CharField(
                        blank=True, max_length=36, null=True, verbose_name="Processing Batch ID"
                    ),
                ),
            ],
            options={
                "verbose_name": "CXR Study",
                "verbose_name_plural": "CXR Studies",
                "ordering": ["-procedure_start_date"],
            },
        ),
        migrations.CreateModel(
            name="ProcessingTask",
            fields=[
                (
                    "task_id",
                    models.CharField(
                        max_length=36, primary_key=True, serialize=False, verbose_name="Task ID"
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "Queued"),
                            ("processing", "Processing"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        default="queued",
                        max_length=20,
                        verbose_name="Status",
                    ),
                ),
                (
                    "progress_message",
                    models.CharField(
                        blank=True, max_length=500, null=True, verbose_name="Progress Message"
                    ),
                ),
                (
                    "progress_percent",
                    models.FloatField(default=0, verbose_name="Progress Percentage"),
                ),
                (
                    "progress_current",
                    models.IntegerField(default=0, verbose_name="Current Progress"),
                ),
                (
                    "progress_total",
                    models.IntegerField(default=0, verbose_name="Total Items"),
                ),
                (
                    "progress_step",
                    models.CharField(
                        blank=True, max_length=50, null=True, verbose_name="Current Step"
                    ),
                ),
                (
                    "txt_report",
                    models.TextField(blank=True, null=True, verbose_name="Text Report"),
                ),
                (
                    "csv_data",
                    models.TextField(blank=True, null=True, verbose_name="CSV Data"),
                ),
                (
                    "error_message",
                    models.TextField(blank=True, null=True, verbose_name="Error Message"),
                ),
                (
                    "total_records_processed",
                    models.IntegerField(default=0, verbose_name="Total Records Processed"),
                ),
                (
                    "new_records_added",
                    models.IntegerField(default=0, verbose_name="New Records Added"),
                ),
                (
                    "existing_records_skipped",
                    models.IntegerField(default=0, verbose_name="Existing Records Skipped"),
                ),
                (
                    "false_negatives_json",
                    models.TextField(
                        blank=True, null=True, verbose_name="False Negatives JSON"
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Created At"),
                ),
                (
                    "completed_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="Completed At"),
                ),
                (
                    "supplemental_steps",
                    models.BooleanField(default=False, verbose_name="Supplemental Steps Enabled"),
                ),
            ],
            options={
                "verbose_name": "Processing Task",
                "verbose_name_plural": "Processing Tasks",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="UploadedFile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "file_type",
                    models.CharField(
                        choices=[("carpl", "CARPL/Lunit File"), ("ge", "GE/RIS File")],
                        max_length=10,
                        verbose_name="File Type",
                    ),
                ),
                (
                    "original_filename",
                    models.CharField(max_length=255, verbose_name="Original Filename"),
                ),
                (
                    "file_path",
                    models.CharField(max_length=500, verbose_name="Stored File Path"),
                ),
                ("file_size", models.BigIntegerField(verbose_name="File Size (bytes)")),
                (
                    "uploaded_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Uploaded At"),
                ),
                (
                    "task",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="files",
                        to="upload.processingtask",
                    ),
                ),
            ],
            options={
                "verbose_name": "Uploaded File",
                "verbose_name_plural": "Uploaded Files",
            },
        ),
        migrations.AddIndex(
            model_name="cxrstudy",
            index=models.Index(fields=["workplace"], name="upload_cxrs_workpla_61ddfd_idx"),
        ),
        migrations.AddIndex(
            model_name="cxrstudy",
            index=models.Index(
                fields=["procedure_start_date"], name="upload_cxrs_procedu_d8e6d2_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="cxrstudy",
            index=models.Index(fields=["gt_llm"], name="upload_cxrs_gt_llm_7f42c0_idx"),
        ),
        migrations.AddIndex(
            model_name="cxrstudy",
            index=models.Index(
                fields=["lunit_binarised"], name="upload_cxrs_lunit_b_e6c7db_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="cxrstudy",
            index=models.Index(
                fields=["processing_batch_id"], name="upload_cxrs_process_d1d88f_idx"
            ),
        ),
    ]
