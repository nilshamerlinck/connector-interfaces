# Author: Simone Orsi
# Copyright 2018 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import odoo.tests.common as common
from odoo import exceptions


class TestBackend(common.SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.backend_model = cls.env["import.backend"]

    def test_backend_create(self):
        bknd = self.backend_model.create({"name": "Foo", "version": "1.0"})
        self.assertTrue(bknd)

    def create_backend_with_recordsets(self):
        # create a backend
        self.bknd = self.backend_model.create(
            {"name": "Foo", "version": "1.0", "cron_cleanup_keep": 3}
        )
        itype = self.env["import.type"].create({"name": "Fake", "key": "fake"})
        # and 5 recorsets
        for x in range(5):
            rec = self.env["import.recordset"].create(
                {"backend_id": self.bknd.id, "import_type_id": itype.id}
            )
            # make sure create date is increased
            rec.create_date = "2018-01-01 00:00:0" + str(x)
        return self.bknd

    def test_backend_cron_cleanup_recordsets(self):
        bknd = self.create_backend_with_recordsets()
        self.assertEqual(len(bknd.recordset_ids), 5)
        # clean them up
        bknd.cron_cleanup_recordsets()
        recsets = bknd.recordset_ids.mapped("name")
        # we should find only 3 records and #1 and #2 gone
        self.assertEqual(len(recsets), 3)
        self.assertNotIn("Foo #1", recsets)
        self.assertNotIn("Foo #2", recsets)

    def test_backend_run_cron(self):
        bknd = self.create_backend_with_recordsets()
        bknd.run_cron(bknd.id)

    def test_job_running_unlink_lock(self):
        bknd = self.create_backend_with_recordsets()
        job = bknd.recordset_ids[0]
        QueueJob = self.env["queue.job"]
        qjob = QueueJob.with_context(
            {
                "_job_edit_sentinel": QueueJob.EDIT_SENTINEL,
            }
        ).create(
            {
                "name": "test queue job",
                "uuid": "test uuid",
                "state": "pending",
            }
        )
        job.job_id = qjob
        self.assertTrue(job.has_job())
        self.assertFalse(job.job_done())
        message = "You must complete the job first!"
        with self.assertRaisesRegex(exceptions.Warning, message):
            job.unlink()
