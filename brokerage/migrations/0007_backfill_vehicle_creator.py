from django.db import migrations


def backfill(apps, schema_editor):
    Vehicle = apps.get_model('brokerage', 'Vehicle')
    AuditEvent = apps.get_model('brokerage', 'AuditEvent')
    alias = schema_editor.connection.alias
    for vehicle in Vehicle.objects.using(alias).filter(created_by__isnull=True).iterator():
        event = AuditEvent.objects.using(alias).filter(action='vehicle_created', target=f'vehicle:{vehicle.pk}', actor__isnull=False).order_by('created_at', 'pk').first()
        if event:
            Vehicle.objects.using(alias).filter(pk=vehicle.pk).update(created_by_id=event.actor_id)


class Migration(migrations.Migration):
    dependencies = [('brokerage', '0006_vehicle_created_by')]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
