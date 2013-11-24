# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import DataMigration
from django.db import models

class Migration(DataMigration):

    def forwards(self, orm):
        "Write your forwards methods here."
        # Note: Remember to use orm['appname.ModelName'] rather than "from appname.models..."
        from django.core.management import call_command
        from os.path import dirname, join
        fixture_path = join(dirname(__file__), "payment.sourcetype.json")
        print "Loading fixture from %s" % fixture_path
        call_command("loaddata", fixture_path)

    def backwards(self, orm):
        "Write your backwards methods here."

    models = {
        u'robokassa.successnotification': {
            'InvId': ('django.db.models.fields.IntegerField', [], {'db_index': 'True'}),
            'Meta': {'object_name': 'SuccessNotification'},
            'OutSum': ('django.db.models.fields.CharField', [], {'max_length': '15'}),
            'created_at': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'})
        }
    }

    complete_apps = ['robokassa']
    symmetrical = True
