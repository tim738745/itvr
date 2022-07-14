# Generated by Django 4.0.1 on 2022-07-14 17:08

import api.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0007_alter_goelectricrebate_options_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='goelectricrebateapplication',
            name='doc1',
            field=models.ImageField(blank=True, null=True, upload_to='docs', validators=[api.validators.validate_file_size, api.validators.validate_file_safe]),
        ),
        migrations.AlterField(
            model_name='goelectricrebateapplication',
            name='doc2',
            field=models.ImageField(blank=True, null=True, upload_to='docs', validators=[api.validators.validate_file_size, api.validators.validate_file_safe]),
        ),
        migrations.AlterField(
            model_name='householdmember',
            name='doc1',
            field=models.ImageField(blank=True, null=True, upload_to='docs', validators=[api.validators.validate_file_size, api.validators.validate_file_safe]),
        ),
        migrations.AlterField(
            model_name='householdmember',
            name='doc2',
            field=models.ImageField(blank=True, null=True, upload_to='docs', validators=[api.validators.validate_file_size, api.validators.validate_file_safe]),
        ),
    ]
