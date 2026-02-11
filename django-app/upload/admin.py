from django.contrib import admin
from .models import CXRStudy, ProcessingTask, UploadedFile


@admin.register(CXRStudy)
class CXRStudyAdmin(admin.ModelAdmin):
    list_display = ('accession_no', 'patient_name', 'workplace', 'procedure_start_date', 
                    'gt_llm', 'lunit_binarised', 'created_at')
    list_filter = ('workplace', 'gt_llm', 'lunit_binarised', 'ai_priority')
    search_fields = ('accession_no', 'patient_name', 'patient_id')
    date_hierarchy = 'procedure_start_date'
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Identifiers', {
            'fields': ('accession_no', 'study_id', 'study_id_anonymized')
        }),
        ('Patient Information', {
            'fields': ('patient_name', 'patient_id', 'patient_age', 'patient_gender')
        }),
        ('Study Details', {
            'fields': ('study_description', 'instances', 'workplace', 'medical_location_name')
        }),
        ('Lunit AI Scores', {
            'fields': ('abnormal', 'atelectasis', 'calcification', 'cardiomegaly', 
                      'consolidation', 'fibrosis', 'mediastinal_widening', 'nodule',
                      'pleural_effusion', 'pneumoperitoneum', 'pneumothorax', 'tuberculosis'),
            'classes': ('collapse',)
        }),
        ('Grading', {
            'fields': ('gt_manual', 'gt_llm', 'lunit_binarised', 'llm_grade')
        }),
        ('Reports', {
            'fields': ('text_report', 'ai_report'),
            'classes': ('collapse',)
        }),
        ('Timing', {
            'fields': ('procedure_start_date', 'procedure_end_date', 'ai_flag_received_date',
                      'time_end_to_end_seconds', 'time_to_clinical_decision_seconds')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'processing_batch_id')
        }),
    )


@admin.register(ProcessingTask)
class ProcessingTaskAdmin(admin.ModelAdmin):
    list_display = ('task_id', 'status', 'progress_percent', 'total_records_processed', 
                    'new_records_added', 'created_at', 'completed_at')
    list_filter = ('status', 'supplemental_steps')
    search_fields = ('task_id',)
    readonly_fields = ('task_id', 'created_at', 'completed_at')
    
    fieldsets = (
        ('Task Info', {
            'fields': ('task_id', 'status', 'supplemental_steps')
        }),
        ('Progress', {
            'fields': ('progress_message', 'progress_percent', 'progress_step',
                      'progress_current', 'progress_total')
        }),
        ('Results', {
            'fields': ('total_records_processed', 'new_records_added', 'existing_records_skipped')
        }),
        ('Reports', {
            'fields': ('txt_report', 'csv_data', 'false_negatives_json'),
            'classes': ('collapse',)
        }),
        ('Errors', {
            'fields': ('error_message',),
            'classes': ('collapse',)
        }),
        ('Timing', {
            'fields': ('created_at', 'completed_at')
        }),
    )


@admin.register(UploadedFile)
class UploadedFileAdmin(admin.ModelAdmin):
    list_display = ('original_filename', 'file_type', 'task', 'file_size', 'uploaded_at')
    list_filter = ('file_type',)
    search_fields = ('original_filename', 'task__task_id')
