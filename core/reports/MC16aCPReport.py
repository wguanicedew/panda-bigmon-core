from django.db import connection
import time
from django.shortcuts import render_to_response, render, redirect
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from django.http import HttpResponse
from reportlab.pdfgen import canvas
from django.template import RequestContext, loader
import StringIO
import humanize
from django.utils.cache import patch_cache_control, patch_response_headers
import json
import hashlib
from django.conf import settings as djangosettings
from django.core.cache import cache
from django.utils import encoding
from datetime import datetime

notcachedRemoteAddress = ['188.184.185.129']

class MC16aCPReport:
    def __init__(self):
        pass


    def getDEFTSummary(self, condition):
        sqlRequest = '''
            SELECT sum(TOTAL_EVENTS),STATUS, 'merge' as STEP  FROM ATLAS_DEFT.T_PRODUCTION_TASK WHERE CAMPAIGN LIKE 'MC16%' and TASKNAME LIKE '%.merge.%' and not TASKNAME LIKE '%valid%' and TASKNAME LIKE 'mc16_%'
            and substr(substr(TASKNAME,instr(TASKNAME,'.',-1) + 1),instr(substr(TASKNAME,instr(TASKNAME,'.',-1) + 1),'_',-1) + 1) like 'r%' {0}
            group by STATUS
            UNION ALL
            SELECT sum(TOTAL_EVENTS),STATUS, 'recon' as STEP  FROM ATLAS_DEFT.T_PRODUCTION_TASK WHERE CAMPAIGN LIKE 'MC16%' and TASKNAME LIKE '%.recon.%' and not TASKNAME LIKE '%valid%' and TASKNAME LIKE 'mc16_%' {1}
            group by STATUS
            UNION ALL
            SELECT sum(TOTAL_EVENTS),STATUS, 'simul' as STEP  FROM ATLAS_DEFT.T_PRODUCTION_TASK WHERE CAMPAIGN LIKE 'MC16%' and TASKNAME LIKE '%.simul.%' and not TASKNAME LIKE '%valid%' and TASKNAME LIKE 'mc16_%' {2}
            group by STATUS
            UNION ALL
            SELECT sum(TOTAL_EVENTS),STATUS, 'evgen' as STEP  FROM ATLAS_DEFT.T_PRODUCTION_TASK WHERE CAMPAIGN LIKE 'MC16%' and TASKNAME LIKE '%.evgen.%' and not TASKNAME LIKE '%valid%' and TASKNAME LIKE 'mc16_%' {3}
            group by STATUS
        '''

        sqlRequestFull = sqlRequest.format(condition, condition, condition, condition)

        cur = connection.cursor()
        cur.execute(sqlRequestFull)
        campaignsummary = cur.fetchall()
        summaryDictFinished = {}
        summaryDictRunning = {}
        summaryDictWaiting = {}
        summaryDictObsolete = {}
        summaryDictFailed = {}

        for summaryRow in campaignsummary:
            if summaryRow[1] == 'finished' or summaryRow[1] == 'done':
                if summaryRow[2] in summaryDictFinished:
                    summaryDictFinished[summaryRow[2]] += summaryRow[0] if summaryRow[0] >= 0 else 0
                else:
                    summaryDictFinished[summaryRow[2]] = summaryRow[0] if summaryRow[0] >= 0 else 0

            if summaryRow[1] == 'running':
                summaryDictRunning[summaryRow[2]] = summaryRow[0] if summaryRow[0] >= 0 else 0

            if summaryRow[1] == 'obsolete':
                summaryDictObsolete[summaryRow[2]] = summaryRow[0] if summaryRow[0] >= 0 else 0

            if summaryRow[1] == 'failed':
                summaryDictFailed[summaryRow[2]] = summaryRow[0] if summaryRow[0] >= 0 else 0


            if summaryRow[1] == 'submitting' or summaryRow[1] == 'registered' or summaryRow[1] == 'waiting':
                if summaryRow[2] in summaryDictWaiting:
                    summaryDictWaiting[summaryRow[2]] += summaryRow[0] if summaryRow[0] >= 0 else 0
                else:
                    summaryDictWaiting[summaryRow[2]] = summaryRow[0] if summaryRow[0] >= 0 else 0

        return {'summaryDictFinished':summaryDictFinished, 'summaryDictRunning':summaryDictRunning, 'summaryDictWaiting':summaryDictWaiting, 'summaryDictObsolete':summaryDictObsolete, 'summaryDictFailed':summaryDictFailed}


    def getTasksJEDISummary(self, condition):
        sqlRequest = '''

            SELECT count(t1.SUPERSTATUS), t1.SUPERSTATUS, 'merge' as STEP FROM ATLAS_PANDA.JEDI_TASKS t1 WHERE campaign like 'MC16%' and TASKNAME LIKE '%.merge.%' and substr(substr(TASKNAME,instr(TASKNAME,'.',-1) + 1),instr(substr(TASKNAME,instr(TASKNAME,'.',-1) + 1),'_',-1) + 1) like 'r%' {0} group by t1.SUPERSTATUS
            UNION ALL
            SELECT count(t1.SUPERSTATUS), t1.SUPERSTATUS, 'recon' as STEP FROM ATLAS_PANDA.JEDI_TASKS t1 WHERE campaign like 'MC16%' and TASKNAME LIKE '%.recon.%' {0} group by t1.SUPERSTATUS
            UNION ALL
            SELECT count(t1.SUPERSTATUS), t1.SUPERSTATUS, 'simul' as STEP FROM ATLAS_PANDA.JEDI_TASKS t1 WHERE campaign like 'MC16%' and TASKNAME LIKE '%.simul.%' {0}  group by t1.SUPERSTATUS
            UNION ALL
            SELECT count(t1.SUPERSTATUS), t1.SUPERSTATUS, 'evgen' as STEP FROM ATLAS_PANDA.JEDI_TASKS t1 WHERE campaign like 'MC16%' and TASKNAME LIKE '%.evgen.%' {0} group by t1.SUPERSTATUS

        '''

        sqlRequestFull = sqlRequest.format(condition)

        cur = connection.cursor()
        cur.execute(sqlRequestFull)
        campaignsummary = cur.fetchall()

        fullSummary = {}
        for summaryRow in campaignsummary:
            if summaryRow[1] not in fullSummary:
                fullSummary[summaryRow[1]] = {}
            if summaryRow[2] not in fullSummary[summaryRow[1]]:
                fullSummary[summaryRow[1]][summaryRow[2]] = 0
            fullSummary[summaryRow[1]][summaryRow[2]] += summaryRow[0]

        for status, stepdict in fullSummary.items():
            for step, val in stepdict.items():
                if 'total' not in fullSummary[status]:
                    fullSummary[status]['total'] = 0
                fullSummary[status]['total'] += val

        return fullSummary

    def getJobsJEDISummary(self, condition):

        sqlRequest = '''
        SELECT COUNT(JOBSTATUS), JOBSTATUS, STEP FROM
            (
            WITH selectedTasks AS (
            SELECT JEDITASKID, 'recon' as STEP FROM ATLAS_PANDA.JEDI_TASKS t1 WHERE campaign like 'MC16%' and TASKNAME LIKE '%.recon.%'
            UNION ALL
            SELECT JEDITASKID, 'simul' as STEP FROM ATLAS_PANDA.JEDI_TASKS t1 WHERE campaign like 'MC16%' and TASKNAME LIKE '%.simul.%'
            UNION ALL
            SELECT JEDITASKID, 'evgen' as STEP FROM ATLAS_PANDA.JEDI_TASKS t1 WHERE campaign like 'MC16%' and TASKNAME LIKE '%.evgen.%'
            UNION ALL
            SELECT JEDITASKID, 'merge' as STEP FROM ATLAS_PANDA.JEDI_TASKS t1 WHERE campaign like 'MC16%' and TASKNAME LIKE '%.merge.%' and substr(substr(TASKNAME,instr(TASKNAME,'.',-1) + 1),instr(substr(TASKNAME,instr(TASKNAME,'.',-1) + 1),'_',-1) + 1) like 'r%'
            )
            SELECT PANDAID, JOBSTATUS, selectedTasks.STEP FROM ATLAS_PANDA.JOBSACTIVE4 t2, selectedTasks WHERE selectedTasks.JEDITASKID=t2.JEDITASKID
            UNION ALL
            SELECT PANDAID, JOBSTATUS, selectedTasks.STEP as STEP FROM ATLAS_PANDA.JOBSARCHIVED4 t2, selectedTasks WHERE selectedTasks.JEDITASKID=t2.JEDITASKID
            UNION ALL
            SELECT PANDAID, JOBSTATUS, selectedTasks.STEP as STEP FROM ATLAS_PANDAARCH.JOBSARCHIVED t2, selectedTasks WHERE selectedTasks.JEDITASKID=t2.JEDITASKID
            UNION ALL
            SELECT PANDAID, JOBSTATUS, selectedTasks.STEP as STEP FROM ATLAS_PANDA.JOBSDEFINED4 t2, selectedTasks WHERE selectedTasks.JEDITASKID=t2.JEDITASKID
            UNION ALL
            SELECT PANDAID, JOBSTATUS, selectedTasks.STEP as STEP FROM ATLAS_PANDA.JOBSWAITING4 t2, selectedTasks WHERE selectedTasks.JEDITASKID=t2.JEDITASKID
            ) tb group by JOBSTATUS, STEP
        '''

        sqlRequestFull = sqlRequest.format(condition)
        cur = connection.cursor()
        cur.execute(sqlRequestFull)
        campaignsummary = cur.fetchall()
        fullSummary = {}
        for summaryRow in campaignsummary:
            if summaryRow[1] not in fullSummary:
                fullSummary[summaryRow[1]] = {}
            if summaryRow[2] not in fullSummary[summaryRow[1]]:
                fullSummary[summaryRow[1]][summaryRow[2]] = 0
            fullSummary[summaryRow[1]][summaryRow[2]] += summaryRow[0]

        for status, stepdict in fullSummary.items():
            for step, val in stepdict.items():
                if 'total' not in fullSummary[status]:
                    fullSummary[status]['total'] = 0
                fullSummary[status]['total'] += val

        return fullSummary


    def getEventsJEDISummary(self, condition):
        sqlRequest = '''

            SELECT sum(decode(t3.startevent,NULL,t3.nevents,t3.endevent-t3.startevent+1)), t3.STATUS, 'merge' as STEP FROM ATLAS_PANDA.JEDI_TASKS t1, ATLAS_PANDA.JEDI_DATASETS t2, ATLAS_PANDA.JEDI_DATASET_CONTENTS t3 WHERE campaign like 'MC16%' AND
            t1.JEDITASKID=t2.JEDITASKID AND t3.DATASETID=t2.DATASETID AND t2.MASTERID IS NULL AND t3.JEDITASKID=t1.JEDITASKID and TASKNAME LIKE '%.merge.%' and t3.TYPE IN ('input', 'pseudo_input') and substr(substr(TASKNAME,instr(TASKNAME,'.',-1) + 1),instr(substr(TASKNAME,instr(TASKNAME,'.',-1) + 1),'_',-1) + 1) like 'r%' {0} group by t3.STATUS
            UNION ALL
            SELECT sum(decode(t3.startevent,NULL,t3.nevents,t3.endevent-t3.startevent+1)), t3.STATUS, 'recon' as STEP FROM ATLAS_PANDA.JEDI_TASKS t1, ATLAS_PANDA.JEDI_DATASETS t2, ATLAS_PANDA.JEDI_DATASET_CONTENTS t3 WHERE campaign like 'MC16%' AND
            t1.JEDITASKID=t2.JEDITASKID AND t3.DATASETID=t2.DATASETID AND t2.MASTERID IS NULL AND t3.JEDITASKID=t1.JEDITASKID and TASKNAME LIKE '%.recon.%' and t3.TYPE IN ('input', 'pseudo_input') {0} group by t3.STATUS
            UNION ALL
            SELECT sum(decode(t3.startevent,NULL,t3.nevents,t3.endevent-t3.startevent+1)), t3.STATUS, 'simul' as STEP FROM ATLAS_PANDA.JEDI_TASKS t1, ATLAS_PANDA.JEDI_DATASETS t2, ATLAS_PANDA.JEDI_DATASET_CONTENTS t3 WHERE campaign like 'MC16%' AND
            t1.JEDITASKID=t2.JEDITASKID AND t3.DATASETID=t2.DATASETID AND t2.MASTERID IS NULL AND t3.JEDITASKID=t1.JEDITASKID and TASKNAME LIKE '%.simul.%' and t3.TYPE IN ('input', 'pseudo_input') {0} group by t3.STATUS
            UNION ALL
            SELECT sum(decode(t3.startevent,NULL,t3.nevents,t3.endevent-t3.startevent+1)), t3.STATUS, 'evgen' as STEP FROM ATLAS_PANDA.JEDI_TASKS t1, ATLAS_PANDA.JEDI_DATASETS t2, ATLAS_PANDA.JEDI_DATASET_CONTENTS t3 WHERE campaign like 'MC16%' AND
            t1.JEDITASKID=t2.JEDITASKID AND t3.DATASETID=t2.DATASETID AND t2.MASTERID IS NULL AND t3.JEDITASKID=t1.JEDITASKID and TASKNAME LIKE '%.evgen.%' and t3.TYPE IN ('input', 'pseudo_input') {0} group by t3.STATUS
        '''

        sqlRequestFull = sqlRequest.format(condition)
        cur = connection.cursor()
        cur.execute(sqlRequestFull)
        campaignsummary = cur.fetchall()
        fullSummary = {}
        for summaryRow in campaignsummary:
            if summaryRow[1] not in fullSummary:
                fullSummary[summaryRow[1]] = {}
            if summaryRow[2] not in fullSummary[summaryRow[1]]:
                fullSummary[summaryRow[1]][summaryRow[2]] = 0
            fullSummary[summaryRow[1]][summaryRow[2]] += summaryRow[0]

        for status, stepdict in fullSummary.items():
            for step, val in stepdict.items():
                if 'total' not in fullSummary[status]:
                    fullSummary[status]['total'] = 0
                fullSummary[status]['total'] += val

        return fullSummary


    def prepareReportJEDI(self, request):

        data = self.getCacheEntry(request, "prepareReportMC16")
        if data is not None:
            data = json.loads(data)
            data['request'] = request
            response = render_to_response('reportCampaign.html', data, RequestContext(request))
            patch_response_headers(response, cache_timeout=request.session['max_age_minutes'] * 60)
            return response

        totalEvents = self.getEventsJEDISummary('')
        totalEvents['title'] = 'Overall input events processing summary'

        totalTasks = self.getTasksJEDISummary('')
        totalTasks['title'] = 'Overall tasks processing summary'

        totalJobs = self.getJobsJEDISummary('')
        totalJobs['title'] = 'Overall Jobs processing summary'

        data = {"totalEvents": [totalEvents], "totalTasks":[totalTasks], "totalJobs":[totalJobs],  'built': datetime.now().strftime("%H:%M:%S")}
        self.setCacheEntry(request, "prepareReportMC16", json.dumps(data, cls=self.DateEncoder), 60 * 20)

        return render_to_response('reportCampaign.html', data, RequestContext(request))




    def prepareReportDEFT(self, request):

        data = self.getCacheEntry(request, "prepareReportDEFT")
        if data is not None:
            data = json.loads(data)
            data['request'] = request
            response = render_to_response('reportCampaign.html', data, RequestContext(request))
            patch_response_headers(response, cache_timeout=request.session['max_age_minutes'] * 60)
            return response

        total = self.getDEFTSummary('')
        total['title'] = 'Overall campaign summary'

        SingleTop = self.getDEFTSummary("and (TASKNAME LIKE '%singletop%' OR TASKNAME LIKE '%\\_wt%' ESCAPE '\\' OR TASKNAME LIKE '%\\_wwbb%' ESCAPE '\\') ")
        SingleTop['title'] = 'SingleTop'

        TTbar = self.getDEFTSummary("and (TASKNAME LIKE '%ttbar%' OR TASKNAME LIKE '%\\_tt\\_%' ESCAPE '\\')")
        TTbar['title'] = 'TTbar'

        Multijet = self.getDEFTSummary("and TASKNAME LIKE '%jets%' ")
        Multijet['title'] = 'Multijet'

        Higgs = self.getDEFTSummary("and TASKNAME LIKE '%h125%' ")
        Higgs['title'] = 'Higgs'

        TTbarX = self.getDEFTSummary("and (TASKNAME LIKE '%ttbb%' OR TASKNAME LIKE '%ttgamma%' OR TASKNAME LIKE '%3top%') ")
        TTbarX['title'] = 'TTbarX'

        BPhysics = self.getDEFTSummary("and TASKNAME LIKE '%upsilon%' ")
        BPhysics['title'] = 'BPhysics'

        SUSY = self.getDEFTSummary("and TASKNAME LIKE '%tanb%' ")
        SUSY['title'] = 'SUSY'

        Exotic = self.getDEFTSummary("and TASKNAME LIKE '%4topci%' ")
        Exotic['title'] = 'Exotic'

        Higgs = self.getDEFTSummary("and TASKNAME LIKE '%xhh%' ")
        Higgs['title'] = 'Higgs'

        Wjets = self.getDEFTSummary("and TASKNAME LIKE '%\\_wenu\\_%' ESCAPE '\\'")
        Wjets['title'] = 'Wjets'

        data = {"tables": [total, SingleTop, TTbar, Multijet, Higgs, TTbarX, BPhysics, SUSY, Exotic, Higgs, Wjets]}
        self.setCacheEntry(request, "prepareReportDEFT", json.dumps(data, cls=self.DateEncoder), 60 * 20)

        return render_to_response('reportCampaign.html', data, RequestContext(request))




    def prepareReport(self):

        requestList = [11034,11048,11049,11050,11051,11052,11198,11197,11222,11359]
        requestList = '(' + ','.join(map(str, requestList)) + ')'

        tasksCondition = "tasktype = 'prod' and WORKINGGROUP NOT IN('AP_REPR', 'AP_VALI', 'GP_PHYS', 'GP_THLT') and " \
                         "processingtype in ('evgen', 'pile', 'simul', 'recon') and REQID in %s" % requestList


        sqlRequest = '''
        select sum(enev), STATUS from (
        select SUM(NEVENTS) as enev, STATUS FROM (
        select NEVENTS, STATUS, t1.JEDITASKID from (
        select sum(decode(c.startevent,NULL,c.nevents,endevent-startevent+1)) nevents,c.status, d.jeditaskid  from atlas_panda.jedi_datasets d,atlas_panda.jedi_dataset_contents c where d.jeditaskid=c.jeditaskid and d.datasetid=c.datasetid and d.type in ('input','pseudo_input') and d.masterid is null group by c.status, d.jeditaskid) t1
        join
        (SELECT JEDITASKID FROM JEDI_TASKS where %s)t2 ON t1.JEDITASKID = t2.JEDITASKID
        ) group by JEDITASKID, STATUS)t3 group by STATUS
        ''' % tasksCondition

        cur = connection.cursor()
        cur.execute(sqlRequest)
        campaignsummary = cur.fetchall()

        finished = 0
        running = 0
        ready = 0

        for row in campaignsummary:
            if row[1] == 'finished':
                finished = row[0]
            if row[1] == 'running':
                running = row[0]
            if row[1] == 'ready':
                ready = row[0]

        data = {
            'finished':finished,
            'running':running,
            'ready':ready,
        }
        return self.renderPDF(data)

    def renderPDF(self, data):
        buff = StringIO.StringIO()
        doc = SimpleDocTemplate(buff, pagesize=letter,
                                rightMargin=72, leftMargin=72,
                                topMargin=72, bottomMargin=18)
        finished = data['finished']
        running = data['running']
        ready = data['ready']

        Report = []
        styles = getSampleStyleSheet()
        style = getSampleStyleSheet()['Normal']
        style.leading = 24

        Report.append(Paragraph('Report on Campaign: ' + "MC16a", styles["Heading1"]))
        Report.append(Paragraph('Build on ' + time.ctime() + " by BigPanDA", styles["Bullet"]))
        Report.append(Paragraph('Progress and loads', styles["Heading2"]))
        Report.append(Paragraph('Done events: ' + humanize.intcomma(int(finished/1000000)) +' M', styles["Normal"]))
        Report.append(Paragraph('Running events: ' + humanize.intcomma(int(running)/1000000) +' M', styles["Normal"]))
        Report.append(Paragraph('Ready for processing events: ' + humanize.intcomma(int(ready)/1000000)  +' M', styles["Normal"]))

        doc.build(Report)
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="report.pdf"'
        response.write(buff.getvalue())
        buff.close()
        return response

    def getName(self):
        return 'Simple campaign report'

    def getParameters(self):
        return {'Request List': ['11034,11048,11049,11050,11051,11052,11198,11197,11222,11359']}

    def getCacheEntry(self,request, viewType, skipCentralRefresh = False):
        is_json = False

        # We do this check to always rebuild cache for the page when it called from the crawler
        if (('REMOTE_ADDR' in request.META) and (request.META['REMOTE_ADDR'] in notcachedRemoteAddress) and
                    skipCentralRefresh == False):
            return None

        request._cache_update_cache = False
        if ((('HTTP_ACCEPT' in request.META) and (request.META.get('HTTP_ACCEPT') in ('application/json'))) or (
                    'json' in request.GET)):
            is_json = True
        key_prefix = "%s_%s_%s_" % (is_json, djangosettings.CACHE_MIDDLEWARE_KEY_PREFIX, viewType)
        path = hashlib.md5(encoding.force_bytes(encoding.iri_to_uri(request.get_full_path())))
        cache_key = '%s.%s' % (key_prefix, path.hexdigest())
        return cache.get(cache_key, None)

    def setCacheEntry(self,request, viewType, data, timeout):
        is_json = False
        request._cache_update_cache = False
        if ((('HTTP_ACCEPT' in request.META) and (request.META.get('HTTP_ACCEPT') in ('application/json'))) or (
                    'json' in request.GET)):
            is_json = True
        key_prefix = "%s_%s_%s_" % (is_json, djangosettings.CACHE_MIDDLEWARE_KEY_PREFIX, viewType)
        path = hashlib.md5(encoding.force_bytes(encoding.iri_to_uri(request.get_full_path())))
        cache_key = '%s.%s' % (key_prefix, path.hexdigest())
        cache.set(cache_key, data, timeout)

    class DateEncoder(json.JSONEncoder):
        def default(self, obj):
            if hasattr(obj, 'isoformat'):
                return obj.isoformat()
            else:
                return str(obj)
            return json.JSONEncoder.default(self, obj)