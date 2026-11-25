#!/usr/bin/env python3
"""Acceptance regressions: HTTP cookies and active versus deferred storage."""
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

import yaml

BUNDLE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BUNDLE/'lib'))


class ValidationTests(unittest.TestCase):
    def setUp(self):
        with patch.dict(os.environ, {'STATE':'/tmp/hmsec-test-unused', 'URL':'http://127.0.0.1:8088',
                                    'HMSEC_CLUSTER':'hm-sec-local', 'HMSEC_SOURCE_DIR':'/tmp/hmsec-test-unused'}):
            spec=importlib.util.spec_from_file_location('hmsec_validation_test', BUNDLE/'lib/validate.py')
            self.v=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.v)
        self.resources={}
        local=BUNDLE/'manifests/local'
        scripts=next(yaml.safe_load_all((local/'base/13-init-scripts-configmap.yaml').read_text()))['data']
        self.kafka_script=scripts['kafka-init.sh']
        self.kafka_topics=re.search(r"^topics='([^']+)'",self.kafka_script,re.M).group(1).splitlines()
        deployments=[d for p in [local/'apps/30-apps.yaml',local/'apps/31-edge.yaml']
                     for d in yaml.safe_load_all(p.read_text()) if d['kind']=='Deployment']
        for d in deployments:
            d['metadata']['generation']=1
            d['status']={'readyReplicas':1,'updatedReplicas':1,'observedGeneration':1}
        self.resources['deployments']=deployments
        sets=[d for d in yaml.safe_load_all((local/'base/11-stateful-data.yaml').read_text())
              if d['kind']=='StatefulSet']
        pvcs=[{'metadata':{'name':'hm-sec-media'},'status':{'phase':'Bound'}}]
        for d in sets:
            d['status']={'readyReplicas':1}
            for claim in d['spec']['volumeClaimTemplates']:
                pvcs.append({'metadata':{'name':claim['metadata']['name']+'-'+d['metadata']['name']+'-0'},
                             'status':{'phase':'Bound'}})
        pvcs.append({'metadata':{'name':'hm-sec-backups'},'spec':{'storageClassName':'local-path'},
                     'status':{'phase':'Pending'}})
        self.resources['statefulsets']=sets
        self.resources['persistentvolumeclaims']=pvcs
        self.resources['jobs']=[{'metadata':{'name':name},'status':{'succeeded':1}}
                                for name in 'postgres-init mongodb-init kafka-init user-db-init reward-db-init user-seed reward-score-init media-init'.split()]
        self.resources['horizontalpodautoscalers']=[]
        self.resources['cronjobs']=[d for d in yaml.safe_load_all((local/'ops/60-backups.yaml').read_text())
                                    if d['kind']=='CronJob']
        self.resources['networkpolicies']=[{} for _ in range(8)]
        self.storageclasses=[{'metadata':{'name':'local-path'},'volumeBindingMode':'WaitForFirstConsumer'}]
        self.http_calls=[]

    def kube(self, *args):
        if args[:2]==('get','nodes'):return json.dumps({'items':[{}]})
        if args[:2]==('get','storageclass'):return json.dumps({'items':self.storageclasses})
        if args[:4]==('-n','hm-sec','get','configmap'):return json.dumps({'data':{'kafka-init.sh':self.kafka_script}})
        if 'postgres-0' in args:return 'reward_service\nuser_service\n'
        if 'mongodb-0' in args:return 'true\n'
        if 'kafka-0' in args:
            if 'sh' in args:return 'persistent\n'
            return '\n'.join(self.kafka_topics)+'\n'
        self.fail('Unexpected Kubernetes request: '+str(args))

    def request(self, opener, path, *args):
        self.http_calls.append(path)
        if '/socket.io/' in path:return 200,b'0{"sid":"fixture"}'
        if path.endswith('/refresh'):return 200,b'{"data":{"token":"fixture"}}'
        if '/auth/login' in path:return 200,b'{"data":{"accessToken":"fixture"}}'
        return 200,b'OK'

    def validate(self):
        self.v.FAILURES.clear()
        output=io.StringIO()
        # CookieJar and build_opener are intentionally real: the previous
        # function/module collision crashed here even when every pod was Ready.
        with patch.object(self.v,'inventory',side_effect=lambda r:copy.deepcopy(self.resources[r])), \
             patch.object(self.v,'k',side_effect=self.kube), \
             patch.object(self.v,'http_request',side_effect=self.request), \
             patch.object(self.v,'read_env',return_value={'HMSEC_SEED_EMAIL':'fixture@example.test','HMSEC_SEED_PASSWORD':'fixture'}), \
             patch.dict(os.environ,{'HMSEC_SOURCE_DIR':'/tmp/hmsec-test-unused'}), \
             patch.object(sys,'argv',['validate.py']), contextlib.redirect_stdout(output):
            result=self.v.main()
        return result,output.getvalue()

    def test_reaches_login_and_refresh_with_deferred_unused_backup_pvc(self):
        result,output=self.validate()
        self.assertEqual(result,0,output)
        self.assertIn('/api/v1/user/auth/login/email',self.http_calls)
        self.assertIn('/api/v1/global/auth/refresh',self.http_calls)
        self.assertIn('PASS: local HM_SEC acceptance checks',output)

    def test_pending_active_database_pvc_still_fails(self):
        self.resources['persistentvolumeclaims'][1]['status']['phase']='Pending'
        self.assertEqual(self.validate()[0],1)
        self.assertIn('All active data/media PVCs are Bound',self.v.FAILURES)

    def test_unrelated_bound_claim_cannot_replace_missing_media_storage(self):
        self.resources['persistentvolumeclaims'][0]['metadata']['name']='unrelated-claim'
        self.assertEqual(self.validate()[0],1)

    def test_pending_backup_requires_wait_for_first_consumer(self):
        self.storageclasses[0]['volumeBindingMode']='Immediate'
        self.assertEqual(self.validate()[0],1)
        self.assertIn('Backup PVC is Bound or awaiting its suspended first consumer',self.v.FAILURES)

    def test_pending_backup_is_not_accepted_when_schedules_are_enabled(self):
        self.resources['cronjobs'][0]['spec']['suspend']=False
        self.assertEqual(self.validate()[0],1)
        self.assertIn('Backup PVC is Bound or awaiting its suspended first consumer',self.v.FAILURES)

    def test_requires_every_baseline_topic_not_only_the_original_five(self):
        self.kafka_topics.remove('comment.unlike.request')
        self.assertEqual(self.validate()[0],1)
        self.assertIn('All baseline Kafka application topics',self.v.FAILURES)


if __name__=='__main__':unittest.main(verbosity=2)
