# Generated manually 2026-06-26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('upload', '0002_rename_upload_cxrs_workpla_61ddfd_idx_upload_cxrs_workpla_3fc2cb_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='processingtask',
            name='task_type',
            field=models.CharField(
                choices=[('upload', 'Upload'), ('backfill', 'Backfill')],
                default='upload',
                max_length=20,
                verbose_name='Task Type',
            ),
        ),
    ]
