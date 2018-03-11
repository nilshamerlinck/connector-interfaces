# Author: Simone Orsi
# Copyright 2018 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import json
import os

from odoo import models, fields, api
from odoo.addons.queue_job.job import job

from .job_mixin import JobRelatedMixin
from ..log import logger


class ImportRecord(models.Model, JobRelatedMixin):
    """Data to be imported.

    An import record contains what you are actually importing.

    Depending on backend settings you gonna have one or more source records
    stored as JSON data into `jsondata` field.

    No matter where you are importing from (CSV, SQL, etc)
    the importer machinery will:

    * retrieve the models to import and their importer
    * process all records and import them
    * update recordset info

    When the importer will run, it will read all the records,
    convert them using connector mappers and do the import.
    """
    _name = 'import.record'
    _description = 'Import record'
    _order = 'id'
    _backend_type = 'import_backend'

    date = fields.Datetime(
        'Import date',
        default=fields.Date.context_today,
    )
    # TODO: use Serialize field?
    jsondata = fields.Text('JSON Data')
    recordset_id = fields.Many2one(
        'import.recordset',
        string='Recordset'
    )
    backend_id = fields.Many2one(
        'import.backend',
        string='Backend',
        related='recordset_id.backend_id',
        readonly=True,
    )

    @api.multi
    def unlink(self):
        # inheritance of non-model mixin does not work w/out this
        return super(ImportRecord, self).unlink()

    @api.multi
    @api.depends('date')
    def _compute_name(self):
        for item in self:
            names = [
                item.date,
            ]
            item.name = ' / '.join([_f for _f in names if _f])

    @api.multi
    def set_data(self, adict):
        self.ensure_one()
        self.jsondata = json.dumps(adict)

    @api.multi
    def get_data(self):
        self.ensure_one()
        return json.loads(self.jsondata or '{}')

    @api.multi
    def debug_mode(self):
        self.ensure_one()
        return self.backend_id.debug_mode or \
            os.environ.get('IMPORTER_DEBUG_MODE')

    @api.multi
    @job
    def import_record(self, component_name, model_name):
        """This job will import a record."""
        with self.backend_id.work_on(self._name) as work:
            importer = work.component_by_name(
                component_name, model_name=model_name)
            return importer.run(self)

    @api.multi
    def run_import(self):
        """ queue a job for importing data stored in to self
        """
        job_method = self.with_delay().import_record
        if self.debug_mode():
            logger.warn('### DEBUG MODE ACTIVE: WILL NOT USE QUEUE ###')
            job_method = self.import_record
        _result = {}
        for item in self:
            # we create a record and a job for each model name
            # that needs to be imported
            for model, importer in item.recordset_id.available_models():
                # TODO: grab component from config
                result = job_method(importer, model)
                _result[model] = result
                if self.debug_mode():
                    # debug mode, no job here: reset it!
                    item.write({'job_id': False})
                else:
                    item.write({'job_id': result.db_record().id})
        return _result