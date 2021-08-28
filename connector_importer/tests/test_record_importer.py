# Author: Simone Orsi
# Copyright 2018 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo.tools import mute_logger

from .common import TestImporterBase
from .fake_components import PartnerMapper

MOD_PATH = "odoo.addons.connector_importer"
RECORD_MODEL = MOD_PATH + ".models.record.ImportRecord"


class TestRecordImporter(TestImporterBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # generate 10 records
        cls.fake_lines = cls._fake_lines(cls, 10, keys=("id", "fullname"))

    def setUp(self):
        super().setUp()
        # The components registry will be handled by the
        # `import.record.import_record()' method when initializing its
        # WorkContext
        self.record = self.env["import.record"].create(
            {"recordset_id": self.recordset.id}
        )

    def _get_components(self):
        from .fake_components import PartnerMapper, UserBinder, PartnerRecordImporter
        from ..components.mapper import ImportMapper

        return [PartnerRecordImporter, UserBinder, PartnerMapper, ImportMapper]

    @mute_logger("[importer]")
    def test_importer_create(self):
        # set them on record
        self.record.set_data(self.fake_lines)
        res = self.record.run_import()
        report = self.recordset.get_report()
        # in any case we'll get this per each model if the import is not broken
        model = "res.partner"
        expected = {
            model: {"created": 10, "errored": 0, "updated": 0, "skipped": 0},
        }
        self.assertEqual(res, expected)
        for k, v in expected[model].items():
            self.assertEqual(len(report[model][k]), v)
        self.assertEqual(self.env[model].search_count([("ref", "like", "id_%")]), 10)

    @mute_logger("[importer]")
    def test_importer_with_options(self):
        PartnerMapper = self._get_components()[2]
        saved_direct = PartnerMapper.direct
        PartnerMapper.direct = saved_direct.copy()
        PartnerMapper.direct.extend([
            ("create_uid", "create_uid"),
            ("create_date", "create_date"),
            ("write_uid", "write_uid"),
            ("write_date", "write_date"),
        ])
        lines = self._fake_lines(10, keys=("id", "fullname"))
        self.record.set_data(lines)
        for line in lines:
            line["create_uid"] = 1
            line["create_date"] = "2021-09-03"
            line["write_uid"] = 1
            line["write_date"] = "2021-09-03"
        saved_options = self.import_type.options
        self.import_type.options = saved_options + """
  options:
    record_handler:
      override_create_date: 1
      override_create_uid: 1"""
        model = "res.partner"
        res = self.record.run_import()
        report = self.recordset.get_report()
        expected = {
            model: {"created": 10, "errored": 0, "updated": 0, "skipped": 0},
        }
        self.assertEqual(res, expected)

        self.import_type.options = saved_options + """
  options:
    mapper: fake.partner.mapper_error"""
        res = self.record.run_import()
        report = self.recordset.get_report()
        expected = {
            model: {"created": 0, "errored": 10, "updated": 0, "skipped": 0},
        }
        self.assertEqual(res, expected)

        self.import_type.options = saved_options + """
  options:
    record_handler:
      skip_fields_unchanged: 1
      override_write_date: 1
      override_write_uid: 1"""
        res = self.record.run_import()
        expected = {
            model: {"created": 0, "errored": 0, "updated": 10, "skipped": 0},
        }
        self.assertEqual(res, expected)
        self.import_type.options = saved_options
        PartnerMapper.direct = saved_direct

    @mute_logger("[importer]")
    def test_importer_skip(self):
        # generate 10 records
        lines = self._fake_lines(10, keys=("id", "fullname"))
        # make a line skip
        lines[0].pop("fullname")
        lines[1].pop("id")
        # set them on record
        self.record.set_data(lines)
        res = self.record.run_import()
        report = self.recordset.get_report()
        model = "res.partner"
        expected = {model: {"created": 8, "errored": 0, "updated": 0, "skipped": 2}}
        self.assertEqual(res, expected)
        for k, v in expected[model].items():
            self.assertEqual(len(report[model][k]), v)
        skipped_msg1 = report[model]["skipped"][0]["message"]
        skipped_msg2 = report[model]["skipped"][1]["message"]
        self.assertEqual(skipped_msg1, "MISSING REQUIRED SOURCE KEY=fullname: ref=id_1")
        # `id` missing, so the destination key `ref` is missing
        # so we don't see it in the message
        self.assertEqual(skipped_msg2, "MISSING REQUIRED SOURCE KEY=id")
        self.assertEqual(self.env[model].search_count([("ref", "like", "id_%")]), 8)

    @mute_logger("[importer]")
    def test_importer_update(self):
        # generate 10 records
        lines = self._fake_lines(10, keys=("id", "fullname"))
        self.record.set_data(lines)
        res = self.record.run_import()
        report = self.recordset.get_report()
        model = "res.partner"
        expected = {model: {"created": 10, "errored": 0, "updated": 0, "skipped": 0}}
        self.assertEqual(res, expected)
        for k, v in expected[model].items():
            self.assertEqual(len(report[model][k]), v)
        # now run it a second time
        # but we must flush the old report which is usually done
        # by the recordset importer
        self.recordset.set_report({}, reset=True)
        res = self.record.run_import()
        report = self.recordset.get_report()
        expected = {model: {"created": 0, "errored": 0, "updated": 10, "skipped": 0}}
        self.assertEqual(res, expected)
        for k, v in expected[model].items():
            self.assertEqual(len(report[model][k]), v)
        # now run it a second time
        # but we set `override existing` false
        self.recordset.set_report({}, reset=True)
        report = self.recordset.override_existing = False
        res = self.record.run_import()
        report = self.recordset.get_report()
        expected = {model: {"created": 0, "errored": 0, "updated": 0, "skipped": 10}}
        self.assertEqual(res, expected)
        for k, v in expected[model].items():
            self.assertEqual(len(report[model][k]), v)
        skipped_msg1 = report[model]["skipped"][0]["message"]
        self.assertEqual(skipped_msg1, "ALREADY EXISTS: ref=id_1")

    @mute_logger("[importer]")
    def test_importer_translatable(self):
        fr_lang = self.env["res.lang"]._activate_lang("fr_FR")
        assert fr_lang
        IrTranslation = self.env["ir.translation"]
        trans = IrTranslation.search([("name", "=", "city")])
        count_trans = len(trans)
        lines = self._fake_lines(10, keys=("id", "fullname", "city", "city:fr_FR"))
        self.record.set_data(lines)
        res = self.record.run_import()
        model = "res.partner"
        expected = {
            model: {"created": 10, "errored": 0, "updated": 0, "skipped": 0},
        }
        self.assertEqual(res, expected)
        self.assertEqual(len(IrTranslation.search([("name", "=", "city")])), count_trans + 10)
